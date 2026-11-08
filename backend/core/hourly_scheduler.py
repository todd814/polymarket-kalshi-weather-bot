"""Autonomous background job for Hourly Weather Paper Trading and Settlement."""
import asyncio
import logging
from datetime import datetime, timezone
import re
from typing import Dict, List, Optional
import httpx

from backend.config import settings
from backend.core.hourly_signals import scan_for_hourly_signals, HourlySignal
from backend.data.metar import fetch_metar_observations, CITY_STATIONS
from backend.models.database import PaperSessionLocal, Trade, Signal, BotState

logger = logging.getLogger("trading_bot")

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

CITY_CODE_MAP = {
    "NYC": "nyc",
    "CHI": "chicago",
    "LAX": "los_angeles",
    "MIA": "miami",
    "AUS": "austin",
    "DEN": "denver",
    "HOU": "houston",
    "DCA": "washington_dc",
    "WDC": "washington_dc",
    "BOS": "boston",
    "PHL": "philadelphia",
}


def parse_expiry_from_ticker(ticker: str) -> Optional[datetime]:
    """Parse UTC expiry datetime from Kalshi Eastern-Time ticker like KXTEMPCHIHS-26NOV0414-T57.99"""
    m = re.search(r'-(\d{2})([A-Z]{3})(\d{2})(\d{2})-', ticker)
    if not m:
        return None
    try:
        from zoneinfo import ZoneInfo
        year = 2000 + int(m.group(1))
        month = MONTH_MAP.get(m.group(2).upper())
        day = int(m.group(3))
        hour = int(m.group(4))
        if not month:
            return None
        local_dt = datetime(year, month, day, hour, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None


def get_city_for_ticker(ticker: str) -> Optional[str]:
    """Extract standard city_key from Kalshi ticker using airport and metro codes."""
    t_upper = ticker.upper()
    for code, city in CITY_CODE_MAP.items():
        if code in t_upper:
            return city
    for city, st in CITY_STATIONS.items():
        if city.upper() in t_upper or st.upper() in t_upper:
            return city
    return None


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

        db = PaperSessionLocal()
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
    Background job: Settle completed hourly weather contracts using official Kalshi finalization
    with METAR observation fallback.
    """
    if not getattr(settings, "HOURLY_WEATHER_ENABLED", True):
        return

    db = PaperSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        pending_trades = db.query(Trade).filter(
            Trade.market_type == "weather_hourly",
            Trade.settled == False
        ).all()

        if not pending_trades:
            return

        # Filter trades whose contract close time has arrived
        eligible_trades: List[Trade] = []
        for trade in pending_trades:
            expiry_dt = parse_expiry_from_ticker(trade.market_ticker)
            if expiry_dt:
                # Settle if close time has arrived
                if now >= expiry_dt:
                    eligible_trades.append(trade)
            else:
                trade_age_seconds = (datetime.utcnow() - trade.timestamp).total_seconds()
                if trade_age_seconds >= 3600:
                    eligible_trades.append(trade)

        if not eligible_trades:
            return

        logger.info(f"Checking hourly settlement for {len(eligible_trades)} eligible contracts...")

        # 1. Batch query Kalshi official finalization status
        kalshi_markets: Dict[str, dict] = {}
        unique_tickers = list({t.market_ticker for t in eligible_trades})

        for i in range(0, len(unique_tickers), 50):
            chunk = unique_tickers[i:i + 50]
            tickers_param = ",".join(chunk)
            url = f"https://api.elections.kalshi.com/trade-api/v2/markets?tickers={tickers_param}"
            try:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.get(url, headers={"User-Agent": "WeatherBot/2.0"})
                    if resp.status_code == 200:
                        data = resp.json()
                        for m in data.get("markets", []):
                            t = m.get("ticker")
                            if t:
                                kalshi_markets[t] = m
            except Exception as e:
                logger.warning(f"Error fetching batch Kalshi settlement: {e}")

        settled_count = 0
        for trade in eligible_trades:
            ticker = trade.market_ticker
            outcome_hit = None
            final_metric_val = None

            # Official Kalshi determined/finalized results are accepted for settlement.
            # No third-party or external observation guesswork.
            k_market = kalshi_markets.get(ticker)
            if k_market and k_market.get("status") in ("determined", "finalized") and k_market.get("result") in ["yes", "no"]:
                outcome_hit = (k_market["result"].lower() == "yes")
                final_metric_val = k_market.get("expiration_value")

            # If Kalshi exchange has not officially finalized the market yet, defer to next cycle
            if outcome_hit is None:
                continue

            # Did our trade win?
            if trade.direction == "yes":
                trade_won = outcome_hit
            else:
                trade_won = not outcome_hit

            entry_p = max(0.01, float(trade.entry_price or 0.5))
            pnl = round((trade.size * ((1.0 - entry_p) / entry_p)) if trade_won else -trade.size, 2)

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

            settled_count += 1
            logger.info(
                f"[HOURLY SETTLED via kalshi_official] {trade.market_ticker}: {trade.result.upper()} "
                f"(Val: {final_metric_val}) -> PnL: ${pnl:+.2f}"
            )

        if settled_count > 0:
            db.commit()
            logger.info(f"Successfully settled {settled_count} hourly contracts.")
    except Exception as e:
        logger.error(f"Error in hourly_settlement_job: {e}", exc_info=True)
    finally:
        db.close()
