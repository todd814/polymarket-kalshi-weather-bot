"""Signal generator for weather temperature markets using ensemble forecasts."""
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional

from backend.config import settings
from backend.core.seasonal_physics import CLIMATOLOGICAL_NORMALS_F, get_season_name
from backend.core.signals import calculate_edge, calculate_kelly_size
from backend.data.weather import fetch_ensemble_forecast, fetch_nws_observed_temperature, EnsembleForecast, CITY_CONFIG
from backend.data.weather_markets import WeatherMarket, fetch_polymarket_weather_markets
from backend.models.database import SessionLocal, PaperSessionLocal, Signal

logger = logging.getLogger("trading_bot")


@dataclass
class WeatherTradingSignal:
    """A trading signal for a weather temperature market."""
    market: WeatherMarket

    # Core signal data
    model_probability: float = 0.5   # Ensemble probability of YES outcome
    market_probability: float = 0.5  # Market's implied YES probability
    edge: float = 0.0
    direction: str = "yes"           # "yes" or "no"

    # Confidence and sizing
    confidence: float = 0.5
    kelly_fraction: float = 0.0
    suggested_size: float = 0.0

    # Metadata
    sources: List[str] = field(default_factory=list)
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Forecast context
    ensemble_mean: float = 0.0
    ensemble_std: float = 0.0
    ensemble_members: int = 0

    @property
    def passes_threshold(self) -> bool:
        """Check if signal passes minimum edge threshold (stricter 10% hurdle for LAX coastal & DEN mountain)."""
        min_hurdle = 0.10 if self.market.city_key in ("los_angeles", "denver") else settings.WEATHER_MIN_EDGE_THRESHOLD
        return self.edge >= min_hurdle and self.suggested_size > 0


async def generate_weather_signal(
    market: WeatherMarket,
    bankroll: Optional[float] = None,
) -> Optional[WeatherTradingSignal]:
    """
    Generate a trading signal for a weather temperature market.

    Uses ensemble forecast to estimate probability:
    - Count fraction of ensemble members above/below/between the threshold
    - Compare to actual market ask price (yes_price / no_price) to find edge
    - Size using Kelly criterion
    """
    forecast = await fetch_ensemble_forecast(market.city_key, market.target_date)
    if not forecast or not forecast.member_highs:
        return None

    # Calculate model probability based on market's question
    if market.metric == "high":
        if market.direction in ("above", "greater"):
            model_yes_prob = forecast.probability_high_above(market.threshold_f)
        elif market.direction in ("below", "less"):
            model_yes_prob = forecast.probability_high_below(market.threshold_f)
        elif market.direction == "between":
            cap = getattr(market, "cap_f", None) or (market.threshold_f + 1.0)
            model_yes_prob = forecast.probability_high_between(market.threshold_f, cap)
        else:
            model_yes_prob = 0.50
    else:  # "low"
        if market.direction in ("above", "greater"):
            model_yes_prob = forecast.probability_low_above(market.threshold_f)
        elif market.direction == "between":
            cap = getattr(market, "cap_f", None) or (market.threshold_f + 1.0)
            model_yes_prob = forecast.probability_low_between(market.threshold_f, cap)
        else:
            model_yes_prob = forecast.probability_low_below(market.threshold_f)

    # --- C-137 High-Water Mark Ratchet (Live ASOS surface observations) ---
    is_same_day = (market.target_date == date.today())
    ratchet_applied = False
    if is_same_day and market.metric == "high":
        try:
            obs = await fetch_nws_observed_temperature(market.city_key, date.today())
            if obs and obs.get("high") is not None:
                observed_high = obs["high"]
                if market.direction in ("above", "greater"):
                    if observed_high >= market.threshold_f + 0.5:
                        ratchet_applied = True
                        model_yes_prob = 0.999  # Threshold already exceeded today! YES guaranteed!
                        logger.info(f"[C-137 RATCHET WIN] {market.slug}: High so far {observed_high:.1f}F >= {market.threshold_f + 0.5:.1f}F -> YES LOCKED")
                elif market.direction in ("below", "less"):
                    if observed_high >= market.threshold_f - 0.5:
                        ratchet_applied = True
                        model_yes_prob = 0.001  # Threshold already reached today! Cannot be below!
                        logger.info(f"[C-137 RATCHET LOSS] {market.slug}: High so far {observed_high:.1f}F >= {market.threshold_f - 0.5:.1f}F -> NO LOCKED")
                elif market.direction == "between":
                    cap = getattr(market, "cap_f", None) or (market.threshold_f + 1.0)
                    if observed_high >= cap + 0.5:
                        ratchet_applied = True
                        model_yes_prob = 0.001  # High already exceeded cap! Cannot land in between bracket!
                        logger.info(f"[C-137 RATCHET LOSS] {market.slug}: High so far {observed_high:.1f}F >= cap {cap + 0.5:.1f}F -> NO LOCKED")
        except Exception as e:
            logger.debug(f"Failed to check ASOS ratchet for {market.city_key}: {e}")

    # Agreement on the contract's specific event (before probability clipping)
    agreement_frac = max(model_yes_prob, 1.0 - model_yes_prob)
    confidence = min(0.9, agreement_frac)

    # Cap directional win probability at 0.85 when ratchet wasn't applied so we
    # never overestimate confidence on our chosen side or invent a 15% YES floor on 0/82 longshots
    raw_yes_prob = model_yes_prob
    if not ratchet_applied:
        yes_win_prob = min(0.85, raw_yes_prob)
        no_win_prob = min(0.85, 1.0 - raw_yes_prob)
    else:
        yes_win_prob = raw_yes_prob
        no_win_prob = 1.0 - raw_yes_prob

    market_yes_prob = market.yes_price
    market_no_prob = market.no_price if (market.no_price and market.no_price > 0) else (1.0 - market_yes_prob)

    # Compute true directional edge against the actual ask price of each side
    yes_edge = yes_win_prob - market_yes_prob
    no_edge = no_win_prob - market_no_prob

    if yes_edge >= no_edge:
        direction = "yes"
        direction_raw = "up"
        edge = max(0.0, yes_edge)
        entry_price = market_yes_prob
        model_yes_prob = yes_win_prob
    else:
        direction = "no"
        direction_raw = "down"
        edge = max(0.0, no_edge)
        entry_price = market_no_prob
        model_yes_prob = 1.0 - no_win_prob

    # Pre-flight calibration check & orderbook spread / entry price filters
    from backend.analytics.calibration import calibration_harness
    is_permitted, lockout_reason = calibration_harness.is_category_permitted("weather")
    if market_yes_prob >= 1.0 or market_no_prob >= 1.0:
        # Kalshi empty-book convention: 1.0000 indicates no resting bid on the opposite side;
        # do not penalize the liquid side with a synthetic two-sided spread.
        spread = 0.0
    else:
        spread = max(0.0, (market_yes_prob + market_no_prob) - 1.0)
    max_spread = 0.10

    filter_notes = []
    if not is_permitted:
        edge = 0.0
        filter_notes.append(lockout_reason or "category locked")

    min_entry_price = (
        getattr(settings, "WEATHER_BRACKET_YES_MIN_PRICE", 0.12)
        if (market.direction == "between" and direction == "yes")
        else getattr(settings, "WEATHER_MIN_ENTRY_PRICE", 0.06)
    )
    if entry_price < min_entry_price:
        edge = 0.0
        filter_notes.append(f"entry {entry_price:.0%} < {min_entry_price:.0%} floor")
    if entry_price > settings.WEATHER_MAX_ENTRY_PRICE:
        edge = 0.0  # Zero out but still return for UI visibility
        filter_notes.append(f"entry {entry_price:.0%} > {settings.WEATHER_MAX_ENTRY_PRICE:.0%}")
    if spread > max_spread:
        edge = 0.0
        filter_notes.append(f"spread {spread:.0%} > {max_spread:.0%}")

    # Kelly sizing using true entry price and current live bankroll
    if bankroll is None:
        bankroll = settings.INITIAL_BANKROLL
        _db = None
        try:
            from backend.models.database import BotState
            _db = SessionLocal()
            _state = _db.query(BotState).first()
            if _state and _state.bankroll:
                bankroll = _state.bankroll
        except Exception:
            pass
        finally:
            if _db is not None:
                _db.close()

    # Clamp effective edge at 25% for Kelly sizing (data science audit: 8-12% edge Brier=0.1795; >35% overconfident)
    effective_edge = min(abs(edge), 0.25)
    suggested_size = calculate_kelly_size(
        edge=effective_edge,
        probability=model_yes_prob,
        market_price=market_yes_prob,
        direction=direction_raw,  # calculate_kelly_size expects "up"/"down"
        bankroll=bankroll,
        actual_entry_price=entry_price,
    ) if edge > 0 else 0.0
    suggested_size = min(suggested_size, settings.WEATHER_MAX_TRADE_SIZE)

    # Ensemble stats & seasonal climatological context for display
    mean_val = forecast.mean_high if market.metric == "high" else forecast.mean_low
    std_val = forecast.std_high if market.metric == "high" else forecast.std_low

    season = get_season_name(market.target_date.month, market.target_date.day)
    normals_table = CLIMATOLOGICAL_NORMALS_F.get(market.city_key, CLIMATOLOGICAL_NORMALS_F["nyc"])
    norm_high, norm_low = normals_table.get(market.target_date.month, (65.0, 48.0))
    clim_norm = norm_high if market.metric == "high" else norm_low
    clim_anomaly = mean_val - clim_norm

    # Build reasoning
    min_hurdle = 0.10 if market.city_key in ("los_angeles", "denver") else settings.WEATHER_MIN_EDGE_THRESHOLD
    filter_status = "ACTIONABLE" if (edge >= min_hurdle and suggested_size > 0) else "FILTERED"
    filter_note = f" [{', '.join(filter_notes)}]" if filter_notes else ""
    if market.direction == "between":
        cap_val = getattr(market, "cap_f", None) or (market.threshold_f + 1.0)
        strike_label = f"{market.threshold_f:.0f}-{cap_val:.0f}F"
    else:
        strike_label = f"{market.threshold_f:.0f}F"

    reasoning = (
        f"[{filter_status}]{filter_note} "
        f"{market.city_name} {market.metric} {market.direction} {strike_label} on {market.target_date} ({season.upper()}) | "
        f"Ensemble: {mean_val:.1f}F +/- {std_val:.1f}F ({forecast.num_members}m, Clim: {clim_norm:.1f}F {clim_anomaly:+.1f}F) | "
        f"Model YES: {model_yes_prob:.0%} vs Market: {market_yes_prob:.0%} | "
        f"Edge: {edge:+.1%} -> {direction.upper()} @ {entry_price:.0%} | "
        f"Agreement: {agreement_frac:.0%}"
    )

    return WeatherTradingSignal(
        market=market,
        model_probability=model_yes_prob,
        market_probability=market_yes_prob,
        edge=edge,
        direction=direction,
        confidence=confidence,
        kelly_fraction=suggested_size / bankroll if bankroll > 0 else 0,
        suggested_size=suggested_size,
        sources=[f"open_meteo_ensemble_{forecast.num_members}m", "noaa_30yr_normals"],
        reasoning=reasoning,
        ensemble_mean=mean_val,
        ensemble_std=std_val,
        ensemble_members=forecast.num_members,
    )


async def scan_for_weather_signals() -> List[WeatherTradingSignal]:
    """
    Scan weather markets and generate ensemble-based signals.
    """
    signals = []

    city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]

    logger.info("=" * 50)
    logger.info("WEATHER SCAN: Fetching temperature markets...")

    markets = []

    # Polymarket
    try:
        poly_markets = await fetch_polymarket_weather_markets(city_keys)
        markets.extend(poly_markets)
        logger.info(f"Polymarket: {len(poly_markets)} weather markets")
    except Exception as e:
        logger.error(f"Failed to fetch Polymarket weather markets: {e}")

    # Kalshi
    if settings.KALSHI_ENABLED:
        try:
            from backend.data.kalshi_markets import fetch_kalshi_weather_markets
            kalshi_markets = await fetch_kalshi_weather_markets(city_keys)
            markets.extend(kalshi_markets)
            logger.info(f"Kalshi: {len(kalshi_markets)} weather markets")
        except Exception as e:
            logger.error(f"Failed to fetch Kalshi weather markets: {e}")

    logger.info(f"Found {len(markets)} total weather temperature markets")

    # --- C-137 Monotonicity & No-Arbitrage Ladder Check ---
    try:
        from backend.analytics.monotonicity import monotonicity_scanner
        arbs = monotonicity_scanner.check_ladder_monotonicity(markets)
        if arbs:
            logger.info(f"[C-137 ARBITRAGE] Found {len(arbs)} cross-strike monotonicity opportunities!")
            for a in arbs[:3]:
                logger.info(f"  • {a.description} (Spread: +${a.profit_margin:.2f})")
    except Exception as e:
        logger.debug(f"Monotonicity scan skipped: {e}")

    # Query live bankroll once before the per-market loop to avoid opening/closing DB sessions repeatedly
    bankroll = settings.INITIAL_BANKROLL
    _db = None
    try:
        from backend.models.database import BotState
        _db = SessionLocal()
        _state = _db.query(BotState).first()
        if _state and _state.bankroll:
            bankroll = _state.bankroll
    except Exception:
        pass
    finally:
        if _db is not None:
            _db.close()

    for market in markets:
        try:
            signal = await generate_weather_signal(market, bankroll=bankroll)
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.debug(f"Weather signal generation failed for {market.title}: {e}")

    # Sort by absolute edge
    signals.sort(key=lambda s: abs(s.edge), reverse=True)

    actionable = [s for s in signals if s.passes_threshold]
    logger.info(f"WEATHER SCAN COMPLETE: {len(signals)} signals, {len(actionable)} actionable")

    for signal in actionable[:5]:
        logger.info(f"  {signal.market.city_name}: {signal.market.metric} {signal.market.direction} "
                     f"{signal.market.threshold_f:.0f}F | Edge: {signal.edge:+.1%}")

    # Persist signals to DB
    _persist_weather_signals(signals)

    return signals


def _persist_weather_signals(signals: list):
    """Save weather signals to DB for calibration tracking (Paper Training DB when in simulation mode)."""
    to_save = [s for s in signals if abs(s.edge) > 0]
    if not to_save:
        return

    db = PaperSessionLocal() if settings.SIMULATION_MODE else SessionLocal()
    try:
        for signal in to_save:
            # Dedup: skip if already logged for this market
            existing = db.query(Signal).filter(
                Signal.market_ticker == signal.market.market_id,
                Signal.timestamp >= signal.timestamp.replace(second=0, microsecond=0),
            ).first()
            if existing:
                continue

            db_signal = Signal(
                market_ticker=signal.market.market_id,
                platform=signal.market.platform,
                market_type="weather",
                timestamp=signal.timestamp,
                direction=signal.direction,
                model_probability=signal.model_probability,
                market_price=signal.market_probability,
                edge=signal.edge,
                confidence=signal.confidence,
                kelly_fraction=signal.kelly_fraction,
                suggested_size=signal.suggested_size,
                sources=signal.sources,
                reasoning=signal.reasoning,
                executed=False,
            )
            db.add(db_signal)

        db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist weather signals: {e}")
        db.rollback()
    finally:
        db.close()
