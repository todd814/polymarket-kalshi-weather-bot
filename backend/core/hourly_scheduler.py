"""Autonomous background job for Hourly Weather Paper Trading and Settlement."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from backend.config import settings
from backend.core.hourly_signals import scan_for_hourly_signals, HourlySignal
from backend.data.metar import fetch_metar_observations, CITY_STATIONS
from backend.models.database import SessionLocal, Trade, Signal, BotState

logger = logging.getLogger("trading_bot")


async def hourly_scan_and_trade_job():
    """
    Background job: Scan Kalshi hourly temperature markets using real-time METAR nowcasts.
    Executes 100% paper trades into the database (zero capital risk).
    """
    if not getattr(settings, "HOURLY_WEATHER_ENABLED", True):
        return

    try:
        signals = await scan_for_hourly_signals()
        actionable = [s for s in signals if s.passes_threshold]

        if not signals:
            return

        logger.info(f"HOURLY WEATHER SCAN: {len(signals)} signals, {len(actionable)} actionable")

        if not actionable:
            return

        db = SessionLocal()
        try:
            state = db.query(BotState).first()
            if state and not state.is_running:
                return

            for sig in actionable:
                # Check for existing open trade on this exact hourly contract
                existing = db.query(Trade).filter(
                    Trade.market_ticker == sig.market.ticker,
                    Trade.settled == False
                ).first()
                if existing:
                    continue

                trade_size = sig.suggested_size
                entry_price = sig.market_price

                # Store into database as paper trade
                trade = Trade(
                    market_ticker=sig.market.ticker,
                    platform="kalshi",
                    event_slug=sig.market.series_ticker,
                    market_type="weather_hourly",
                    direction=sig.direction,
                    entry_price=entry_price,
                    size=trade_size,
                    model_probability=sig.model_probability,
                    market_price_at_entry=sig.market_price,
                    edge_at_entry=sig.edge,
                    is_paper=True,
                    settled=False
                )
                db.add(trade)
                db.flush()

                # Record signal log
                db_signal = Signal(
                    market_ticker=sig.market.ticker,
                    platform="kalshi",
                    market_type="weather_hourly",
                    direction=sig.direction,
                    model_probability=sig.model_probability,
                    market_price=sig.market_price,
                    edge=sig.edge,
                    confidence=sig.confidence,
                    kelly_fraction=0.15,
                    suggested_size=trade_size,
                    sources=["aviationweather_metar", "kalshi_hourly"],
                    reasoning=sig.reasoning,
                    executed=True,
                    is_paper=True
                )
                db.add(db_signal)
                db.flush()
                trade.signal_id = db_signal.id

                logger.info(
                    f"[HOURLY PAPER TRADE] {sig.direction.upper()} ${trade_size:.2f} @ {entry_price:.0%} | "
                    f"{sig.market.ticker} (Edge: {sig.edge:+.1%})"
                )

            db.commit()
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error in hourly_scan_and_trade_job: {e}", exc_info=True)


async def hourly_settlement_job():
    """
    Background job: Settle completed hourly weather contracts using official METAR reports.
    """
    if not getattr(settings, "HOURLY_WEATHER_ENABLED", True):
        return

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Query unsettled hourly paper trades
        pending_trades = db.query(Trade).filter(
            Trade.market_type == "weather_hourly",
            Trade.settled == False
        ).all()

        if not pending_trades:
            return

        # Fetch latest METAR observations for verification
        metar_map = await fetch_metar_observations(force_refresh=True)

        for trade in pending_trades:
            # We determine city from ticker or event_slug
            city_key = None
            ticker = trade.market_ticker
            for c, st in CITY_STATIONS.items():
                if c in ticker.lower() or st.lower() in ticker.lower():
                    city_key = c
                    break

            if not city_key:
                continue

            station = CITY_STATIONS.get(city_key)
            obs = metar_map.get(station)
            if not obs:
                continue

            # Check if close_time has passed
            # Ticker format typically has timestamp or we check signal timestamp + 1h
            trade_age_seconds = (datetime.utcnow() - trade.timestamp).total_seconds()
            if trade_age_seconds < 3600:  # Minimum 1 hour before attempting settlement
                continue

            # Settlement logic: compare current terminal METAR temperature vs threshold
            # Extract threshold from market_ticker (e.g. -T79.99)
            import re
            match = re.search(r'-([TB])(-?[\d.]+)$', ticker)
            if not match:
                continue

            threshold_f = float(match.group(2))
            is_above_contract = (match.group(1) == "T")

            final_t = obs.temp_f
            if is_above_contract:
                outcome_hit = (final_t >= threshold_f)
            else:
                outcome_hit = (final_t < threshold_f)

            # Did our trade win?
            if trade.direction == "yes":
                trade_won = outcome_hit
            else:
                trade_won = not outcome_hit

            pnl = round((trade.size * (1.0 - trade.entry_price)) if trade_won else (-trade.size * trade.entry_price), 2)

            trade.settled = True
            trade.settlement_time = datetime.utcnow()
            trade.settlement_value = 1.0 if outcome_hit else 0.0
            trade.result = "win" if trade_won else "loss"
            trade.pnl = pnl

            # Update corresponding signal
            if trade.signal_id:
                sig = db.query(Signal).filter(Signal.id == trade.signal_id).first()
                if sig:
                    sig.actual_outcome = 1.0 if outcome_hit else 0.0
                    sig.outcome_correct = trade_won
                    sig.settled_at = datetime.utcnow()

            logger.info(
                f"[HOURLY SETTLED] {trade.market_ticker}: {trade.result.upper()} "
                f"(Final METAR {obs.station_id}: {final_t}°F vs {threshold_f}°F) -> PnL: ${pnl:+.2f}"
            )

        db.commit()
    except Exception as e:
        logger.error(f"Error in hourly_settlement_job: {e}", exc_info=True)
    finally:
        db.close()
