"""Background scheduler for BTC 5-min autonomous trading."""
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func
import logging

from backend.config import settings
from backend.models.database import SessionLocal, Trade, BotState, Signal
from backend.core.signals import scan_for_signals

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trading_bot")

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None

# Event log for terminal display (in-memory, last 200 events)
event_log: List[dict] = []
MAX_LOG_SIZE = 200


def log_event(event_type: str, message: str, data: dict = None):
    """Log an event for terminal display."""
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": event_type,
        "message": message,
        "data": data or {}
    }
    event_log.append(event)

    while len(event_log) > MAX_LOG_SIZE:
        event_log.pop(0)

    log_func = {
        "error": logger.error,
        "warning": logger.warning,
        "success": logger.info,
        "info": logger.info,
        "data": logger.debug,
        "trade": logger.info
    }.get(event_type, logger.info)

    log_func(f"[{event_type.upper()}] {message}")


def get_recent_events(limit: int = 50) -> List[dict]:
    """Get recent events for terminal display."""
    return event_log[-limit:]


async def scan_and_trade_job():
    """
    Background job: Scan BTC 5-min markets, generate signals, execute trades.
    Runs every minute.
    """
    log_event("info", "Scanning BTC 5-min markets...")

    try:
        signals = await scan_for_signals()
        actionable = [s for s in signals if s.passes_threshold]

        log_event("data", f"Found {len(signals)} signals, {len(actionable)} actionable", {
            "total_signals": len(signals),
            "actionable": len(actionable),
        })

        if not actionable:
            log_event("info", "No actionable BTC signals")
            return

        db = SessionLocal()
        try:
            state = db.query(BotState).first()
            if not state:
                log_event("error", "Bot state not initialized")
                return

            if not state.is_running:
                log_event("info", "Bot is paused, skipping trades")
                return

            MAX_TRADES_PER_SCAN = 2
            # Dedicated C-137 Paper BTC Calibration Configuration
            PAPER_BTC_BANKROLL = 100.0
            MIN_TRADE_SIZE = 2.0
            MAX_TRADE_FRACTION = 0.05  # 5% max per trade = $5.00
            MAX_TOTAL_PENDING = settings.MAX_TOTAL_PENDING_TRADES

            total_pending = db.query(Trade).filter(Trade.settled == False, Trade.market_type == "btc").count()
            if total_pending >= MAX_TOTAL_PENDING:
                log_event("info", f"Max pending BTC paper trades reached ({total_pending}/{MAX_TOTAL_PENDING})")
                return

            trades_executed = 0
            for signal in actionable:
                # Check if we already have a trade for this market window
                existing = db.query(Trade).filter(
                    Trade.event_slug == signal.market.slug,
                    Trade.settled == False
                ).first()

                if existing:
                    continue

                if signal.suggested_size <= 0:
                    continue

                trade_size = min(signal.suggested_size, PAPER_BTC_BANKROLL * MAX_TRADE_FRACTION)
                trade_size = max(trade_size, MIN_TRADE_SIZE)

                if trades_executed >= MAX_TRADES_PER_SCAN:
                    break

                # Map up/down to yes/no for storage
                entry_price = signal.market.up_price if signal.direction == "up" else signal.market.down_price

                trade = Trade(
                    market_ticker=signal.market.market_id,
                    platform=getattr(signal.market, "platform", "polymarket"),
                    event_slug=signal.market.slug,
                    market_type="btc",
                    direction=signal.direction,
                    entry_price=entry_price,
                    size=trade_size,
                    model_probability=signal.model_probability,
                    market_price_at_entry=signal.market_probability,
                    edge_at_entry=signal.edge,
                    is_paper=True,
                )

                db.add(trade)
                db.flush()  # get trade.id

                # Link trade to the most recent matching Signal and mark it executed
                matching_signal = db.query(Signal).filter(
                    Signal.market_ticker == signal.market.market_id,
                    Signal.market_type == "btc",
                    Signal.executed == False,
                ).order_by(Signal.timestamp.desc()).first()
                if matching_signal:
                    matching_signal.executed = True
                    matching_signal.is_paper = True
                    trade.signal_id = matching_signal.id

                trades_executed += 1

                log_event("trade",
                    f"[C-137 PAPER CALIBRATION] Simulated BTC {signal.direction.upper()} ${trade_size:.0f} @ {entry_price:.0%} | {signal.market.slug}",
                    {
                        "slug": signal.market.slug,
                        "direction": signal.direction,
                        "size": trade_size,
                        "edge": signal.edge,
                        "entry_price": entry_price,
                        "btc_price": signal.btc_price,
                    }
                )

            state.last_run = datetime.utcnow()
            db.commit()

            if trades_executed > 0:
                log_event("success", f"Executed {trades_executed} BTC trade(s)")
            else:
                log_event("info", "No new trades executed")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Scan error: {str(e)}")
        logger.exception("Error in scan_and_trade_job")


async def weather_scan_and_trade_job():
    """
    Background job: Scan weather temperature markets, generate signals, execute trades.
    Runs every 5 minutes when WEATHER_ENABLED.
    """
    log_event("info", "Scanning weather temperature markets...")

    try:
        from backend.core.weather_signals import scan_for_weather_signals

        signals = await scan_for_weather_signals()
        actionable = [s for s in signals if s.passes_threshold]

        log_event("data", f"Weather: {len(signals)} signals, {len(actionable)} actionable", {
            "total_signals": len(signals),
            "actionable": len(actionable),
        })

        if not actionable:
            log_event("info", "No actionable weather signals")
            return

        db = SessionLocal()
        try:
            state = db.query(BotState).first()
            if not state:
                log_event("error", "Bot state not initialized")
                return

            if not state.is_running:
                log_event("info", "Bot is paused, skipping weather trades")
                return

            MAX_TRADES_PER_SCAN = 3
            MIN_TRADE_SIZE = max(1.0, round(state.bankroll * 0.01, 2))
            MAX_WEATHER_ALLOCATION = max(20.0, round(state.bankroll * 0.50, 2))  # Max 50% exposure to weather markets

            # Check weather allocation limit (live bankroll only)
            weather_pending = db.query(func.coalesce(func.sum(Trade.size), 0.0)).filter(
                Trade.settled == False,
                Trade.market_type == "weather",
                Trade.is_paper == False,
            ).scalar()

            trades_executed = 0
            paper_trades_executed = 0
            attempted_live_tickers = set()
            live_held_tickers = set()

            # --- TRACK 1: TOP-TIER LIVE KALSHI DEMO TRADING ---
            for signal in actionable:
                # Check if we already have an active LIVE trade for this market
                existing_live = db.query(Trade).filter(
                    Trade.market_ticker == signal.market.market_id,
                    Trade.settled == False,
                    Trade.is_paper == False,
                ).first()

                if existing_live:
                    live_held_tickers.add(signal.market.market_id)
                    continue

                if signal.suggested_size <= 0:
                    continue

                if trades_executed >= MAX_TRADES_PER_SCAN:
                    break

                if weather_pending >= MAX_WEATHER_ALLOCATION:
                    log_event("info", f"Weather allocation limit reached: ${weather_pending:.0f}/${MAX_WEATHER_ALLOCATION:.0f}")
                    break

                if state.bankroll < MIN_TRADE_SIZE:
                    log_event("warning", f"Bankroll too low: ${state.bankroll:.2f}")
                    break

                attempted_live_tickers.add(signal.market.market_id)
                trade_size = min(signal.suggested_size, settings.WEATHER_MAX_TRADE_SIZE)
                trade_size = max(trade_size, MIN_TRADE_SIZE)

                entry_price = signal.market.yes_price if signal.direction == "yes" else signal.market.no_price

                # Live order execution on Kalshi Demo / Prod
                kalshi_order_id = None
                if getattr(signal.market, "platform", "") == "kalshi" and settings.KALSHI_EXECUTE_DEMO_ORDERS:
                    from backend.data.kalshi_client import KalshiClient, kalshi_credentials_present
                    if kalshi_credentials_present():
                        try:
                            k_client = KalshiClient()
                            num_contracts = max(1, int(trade_size / entry_price))
                            order_res = await k_client.create_order(
                                ticker=signal.market.market_id,
                                contract_type=signal.direction,
                                count=num_contracts,
                                price_dollars=entry_price,
                            )
                            order_obj = order_res.get("order", order_res) if isinstance(order_res, dict) else {}
                            kalshi_order_id = order_obj.get("order_id") or (order_res.get("order_id") if isinstance(order_res, dict) else None)
                            raw_fill = (
                                order_obj.get("fill_count")
                                or order_obj.get("fill_count_fp")
                                or (order_res.get("fill_count") if isinstance(order_res, dict) else 0)
                                or (order_res.get("fill_count_fp") if isinstance(order_res, dict) else 0)
                                or 0
                            )
                            filled_contracts = float(raw_fill or 0)
                            if filled_contracts <= 0:
                                log_event(
                                    "info",
                                    f"Kalshi IOC order unfilled (0/{num_contracts} contracts) on {signal.market.market_id}; skipping phantom trade",
                                    order_res if isinstance(order_res, dict) else {},
                                )
                                continue
                            trade_size = round(filled_contracts * entry_price, 2)
                            log_event("trade", f"KALSHI DEMO ORDER FILLED: {kalshi_order_id} | {filled_contracts:g}x {signal.direction.upper()} on {signal.market.market_id}", order_res)
                        except Exception as e:
                            log_event("error", f"Kalshi order placement error: {e}")
                            continue

                trade = Trade(
                    market_ticker=signal.market.market_id,
                    platform=getattr(signal.market, "platform", "kalshi"),
                    event_slug=signal.market.slug,
                    market_type="weather",
                    direction=signal.direction,
                    entry_price=entry_price,
                    size=trade_size,
                    model_probability=signal.model_probability,
                    market_price_at_entry=signal.market_probability,
                    edge_at_entry=signal.edge,
                    is_paper=False,
                )

                db.add(trade)
                db.flush()

                # Clean up any prior shadow paper trade for this market since live trade has executed
                existing_paper = db.query(Trade).filter(
                    Trade.market_ticker == signal.market.market_id,
                    Trade.settled == False,
                    Trade.is_paper == True,
                ).first()
                if existing_paper:
                    db.delete(existing_paper)

                # Link to signal record
                matching_signal = db.query(Signal).filter(
                    Signal.market_ticker == signal.market.market_id,
                    Signal.market_type == "weather",
                    Signal.executed == False,
                ).order_by(Signal.timestamp.desc()).first()
                if matching_signal:
                    matching_signal.executed = True
                    matching_signal.is_paper = False
                    trade.signal_id = matching_signal.id

                state.total_trades += 1
                trades_executed += 1
                weather_pending += trade_size

                log_event("trade",
                    f"WX [LIVE] {signal.market.city_name}: {signal.direction.upper()} "
                    f"${trade_size:.0f} @ {entry_price:.0%} | "
                    f"{signal.market.metric} {signal.market.direction} {signal.market.threshold_f:.0f}F",
                    {
                        "slug": signal.market.slug,
                        "direction": signal.direction,
                        "size": trade_size,
                        "edge": signal.edge,
                        "entry_price": entry_price,
                        "city": signal.market.city_name,
                        "is_paper": False,
                    }
                )

            # --- TRACK 2: SHADOW PAPER WEATHER TRADING (HIGH-VOLUME DATA HARVESTING) ---
            # Paper trades record for all actionable signals above lower hurdle (e.g. edge >= 3%),
            # allowing high-volume data collection across all weather markets without consuming live bankroll.
            paper_hurdle = getattr(settings, "WEATHER_PAPER_MIN_EDGE_THRESHOLD", 0.03)
            for signal in signals:
                ticker = signal.market.market_id
                if ticker in attempted_live_tickers or ticker in live_held_tickers:
                    continue

                if signal.edge < paper_hurdle:
                    continue

                entry_price = signal.market.yes_price if signal.direction == "yes" else signal.market.no_price
                if entry_price <= 0.0 or entry_price >= 1.0:
                    continue

                # Check if trade already exists
                existing_paper = db.query(Trade).filter(
                    Trade.market_ticker == ticker,
                    Trade.settled == False,
                ).first()
                if existing_paper:
                    continue

                paper_size = 5.0  # Standard simulated contract size ($5)
                paper_trade = Trade(
                    market_ticker=ticker,
                    platform=getattr(signal.market, "platform", "kalshi"),
                    event_slug=signal.market.slug,
                    market_type="weather",
                    direction=signal.direction,
                    entry_price=entry_price,
                    size=paper_size,
                    model_probability=signal.model_probability,
                    market_price_at_entry=signal.market_probability,
                    edge_at_entry=signal.edge,
                    is_paper=True,
                )

                db.add(paper_trade)
                db.flush()

                # Link to signal record
                matching_sig = db.query(Signal).filter(
                    Signal.market_ticker == ticker,
                    Signal.market_type == "weather",
                    Signal.executed == False,
                ).order_by(Signal.timestamp.desc()).first()
                if matching_sig:
                    matching_sig.executed = True
                    matching_sig.is_paper = True
                    paper_trade.signal_id = matching_sig.id

                paper_trades_executed += 1
                log_event("trade",
                    f"WX [PAPER] {signal.market.city_name}: {signal.direction.upper()} "
                    f"${paper_size:.0f} @ {entry_price:.0%} (Edge: {signal.edge:+.1%}) | "
                    f"{signal.market.metric} {signal.market.direction} {signal.market.threshold_f:.0f}F",
                    {
                        "slug": signal.market.slug,
                        "direction": signal.direction,
                        "size": paper_size,
                        "edge": signal.edge,
                        "entry_price": entry_price,
                        "city": signal.market.city_name,
                        "is_paper": True,
                    }
                )

            state.last_run = datetime.utcnow()
            db.commit()

            if trades_executed > 0 or paper_trades_executed > 0:
                log_event("success", f"Executed {trades_executed} live weather trade(s), {paper_trades_executed} paper trade(s)")
            else:
                log_event("info", "No new weather trades executed")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Weather scan error: {str(e)}")
        logger.exception("Error in weather_scan_and_trade_job")


async def settlement_job():
    """
    Background job: Check and settle pending trades.
    Runs every 2 minutes (BTC 5-min markets resolve fast).
    """
    log_event("info", "Checking BTC trade settlements...")

    try:
        from backend.core.settlement import settle_pending_trades, update_bot_state_with_settlements

        db = SessionLocal()
        try:
            pending_count = db.query(Trade).filter(Trade.settled == False).count()

            if pending_count == 0:
                log_event("data", "No pending trades to settle")
                return

            log_event("data", f"Processing {pending_count} pending trades")

            settled = await settle_pending_trades(db)

            if settled:
                await update_bot_state_with_settlements(db, settled)

                wins = sum(1 for t in settled if t.result == "win")
                losses = sum(1 for t in settled if t.result == "loss")
                total_pnl = sum(t.pnl for t in settled if t.pnl is not None)

                log_event("success", f"Settled {len(settled)} trades: {wins}W/{losses}L, P&L: ${total_pnl:.2f}", {
                    "settled_count": len(settled),
                    "wins": wins,
                    "losses": losses,
                    "pnl": total_pnl
                })

                for trade in settled:
                    result_prefix = "+" if trade.pnl and trade.pnl > 0 else ""
                    log_event("data", f"  {trade.event_slug}: {trade.result.upper()} {result_prefix}${trade.pnl:.2f}")
            else:
                log_event("info", "No trades ready for settlement")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Settlement error: {str(e)}")
        logger.exception("Error in settlement_job")


async def heartbeat_job():
    """Periodic heartbeat. Runs every minute."""
    db = None
    try:
        db = SessionLocal()
        state = db.query(BotState).first()
        pending = db.query(Trade).filter(Trade.settled == False).count()

        if state is None:
            log_event("warning", "Heartbeat: Bot state not initialized")
            return

        log_event("data", f"Heartbeat: {pending} pending trades, bankroll: ${state.bankroll:.2f}", {
            "pending_trades": pending,
            "bankroll": state.bankroll,
            "is_running": state.is_running
        })
    except Exception as e:
        log_event("warning", f"Heartbeat failed: {str(e)}")
    finally:
        if db:
            db.close()


def start_scheduler():
    """Start the background scheduler for BTC 5-min trading."""
    global scheduler

    if scheduler is not None and scheduler.running:
        log_event("warning", "Scheduler already running")
        return

    scheduler = AsyncIOScheduler()

    scan_seconds = settings.SCAN_INTERVAL_SECONDS
    settle_seconds = settings.SETTLEMENT_INTERVAL_SECONDS

    # Scan BTC markets every minute (only if enabled)
    if settings.BTC_ENABLED:
        scheduler.add_job(
            scan_and_trade_job,
            IntervalTrigger(seconds=scan_seconds),
            id="market_scan",
            replace_existing=True,
            max_instances=1
        )

        # Check settlements every 2 minutes
        scheduler.add_job(
            settlement_job,
            IntervalTrigger(seconds=settle_seconds),
            id="settlement_check",
            replace_existing=True,
            max_instances=1
        )

    # Heartbeat every minute
    scheduler.add_job(
        heartbeat_job,
        IntervalTrigger(minutes=1),
        id="heartbeat",
        replace_existing=True,
        max_instances=1
    )

    # Weather trading jobs (gated by WEATHER_ENABLED)
    if settings.WEATHER_ENABLED:
        weather_scan_seconds = settings.WEATHER_SCAN_INTERVAL_SECONDS
        weather_settle_seconds = settings.WEATHER_SETTLEMENT_INTERVAL_SECONDS

        scheduler.add_job(
            weather_scan_and_trade_job,
            IntervalTrigger(seconds=weather_scan_seconds),
            id="weather_scan",
            replace_existing=True,
            max_instances=1,
        )

    scheduler.start()
    log_event("success", "BTC 5-min trading scheduler started", {
        "scan_interval": f"{scan_seconds}s",
        "settlement_interval": f"{settle_seconds}s",
        "min_edge": f"{settings.MIN_EDGE_THRESHOLD:.0%}",
        "weather_enabled": settings.WEATHER_ENABLED,
    })

    if settings.BTC_ENABLED:
        asyncio.create_task(scan_and_trade_job())

    if settings.WEATHER_ENABLED:
        asyncio.create_task(weather_scan_and_trade_job())


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler

    if scheduler is None or not scheduler.running:
        log_event("info", "Scheduler not running")
        return

    scheduler.shutdown(wait=False)
    scheduler = None
    log_event("info", "Scheduler stopped")


def is_scheduler_running() -> bool:
    """Check if scheduler is currently running."""
    return scheduler is not None and scheduler.running


async def run_manual_scan():
    """Trigger a manual market scan."""
    log_event("info", "Manual scan triggered")
    await scan_and_trade_job()


async def run_manual_settlement():
    """Trigger a manual settlement check."""
    log_event("info", "Manual settlement triggered")
    await settlement_job()
