"""Background scheduler for BTC 5-min autonomous trading."""
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func
import logging

from backend.config import settings
from backend.models.database import SessionLocal, PaperSessionLocal, Trade, BotState, Signal
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


def _parse_ticker_target_date(ticker: str):
    """
    C-137 Ticker Chronology Parser:
    Extracts the contract target date from a Kalshi ticker (e.g. KXHIGHDEN-26NOV08-B69.5 -> 2026-11-08)
    so yesterday's closed 'Outcome pending' corpses don't hostage today's capital.
    """
    import re
    m = re.search(r"-(\d{2}[A-Z]{3}\d{2})-", (ticker or "").upper())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%y%b%d").date()
    except ValueError:
        return None


def _extract_ticker_city_and_date(ticker: str):
    """
    Extract canonical city_key and target_date from ticker to prevent multi-strike concentration clustering.
    """
    prefix = (ticker or "").split("-")[0].upper()
    city_map = {
        "KXHIGHNY": "nyc",
        "KXHIGHCHI": "chicago",
        "KXHIGHMIA": "miami",
        "KXHIGHLAX": "los_angeles",
        "KXHIGHDEN": "denver",
        "KXHIGHAUS": "austin",
        "KXHIGHTHOU": "houston",
        "KXHIGHDCA": "washington_dc",
        "KXHIGHBOS": "boston",
        "KXHIGHPHIL": "philadelphia",
    }
    return city_map.get(prefix), _parse_ticker_target_date(ticker)


def _compute_staged_weather_exposure(db, signals: list, today_est=None) -> tuple[float, float, float, int]:
    """
    C-137 Staged Rolling Target-Date Vintage Exposure Engine:
    Splits active at-risk weather exposure into two horizon buckets:
      - Bucket A (today_exposure): Same-day contracts (target_date <= today_est), capped at 25% of bankroll.
      - Bucket B (future_exposure): Tomorrow/future contracts (target_date > today_est), capped at 12.5% of bankroll
        so when Tomorrow rolls into Today at midnight EST, it automatically inherits the full 25% Today cap
        with at least 12.5% dry powder reserved for high-precision same-day synoptic & ASOS ratchet setups.
    Excludes unsettled positions that:
      1. Are in 'Outcome pending' status (prior-day contracts where target_date < today_est,
         or closed contracts no longer in active open signals while their series is active)
         AND are expected to win (held-side win probability >= 0.50).
      2. Are active open positions that have already locked in an expected win intraday
         via the C-137 ASOS High-Water Mark Ratchet (held-side model prob >= 0.90) or
         a live market mark on our held side >= 0.85 (excluding 1.00 empty-book placeholders).
    Returns (today_exposure_usd, future_exposure_usd, excluded_exposure_usd, excluded_count).
    """
    from zoneinfo import ZoneInfo
    if today_est is None:
        today_est = datetime.now(ZoneInfo("America/New_York")).date()

    open_trades = db.query(Trade).filter(
        Trade.settled == False,
        Trade.market_type == "weather",
        Trade.is_paper == False,
    ).all()

    sig_by_ticker = {s.market.market_id: s for s in (signals or []) if getattr(s, "market", None)}
    active_series_prefixes = {
        t_id.split("-")[0] for t_id in sig_by_ticker.keys() if "-" in t_id
    }

    today_exposure = 0.0
    future_exposure = 0.0
    excluded_exposure = 0.0
    excluded_count = 0

    for t in open_trades:
        t_size = float(t.size or 0.0)
        ticker = t.market_ticker or ""
        series_prefix = ticker.split("-")[0] if "-" in ticker else ""
        target_dt = _parse_ticker_target_date(ticker)

        held_dir = (t.direction or "yes").lower()
        raw_model_prob = float(t.model_probability if t.model_probability is not None else 0.5)
        # Trade.model_probability stores model_yes_prob from WeatherTradingSignal
        stored_side_win_prob = raw_model_prob if held_dir == "yes" else (1.0 - raw_model_prob)

        # 1. Kalshi "Outcome pending" status (prior-day contract or closed trading window)
        is_outcome_pending = (
            (target_dt is not None and target_dt < today_est)
            or (series_prefix in active_series_prefixes and ticker not in sig_by_ticker)
        )
        if is_outcome_pending and stored_side_win_prob >= 0.50:
            excluded_exposure += t_size
            excluded_count += 1
            continue

        # 2. Active open position that locked in an expected win (Ratchet >= 90% or market mark >= 85c)
        sig = sig_by_ticker.get(ticker)
        if sig is not None:
            live_side_prob = sig.model_probability if held_dir == "yes" else (1.0 - sig.model_probability)
            live_side_mark = sig.market.yes_price if held_dir == "yes" else sig.market.no_price
            if live_side_prob >= 0.90 or (live_side_mark is not None and 0.85 <= live_side_mark < 1.0):
                excluded_exposure += t_size
                excluded_count += 1
                continue

        if target_dt is not None and target_dt > today_est:
            future_exposure += t_size
        else:
            today_exposure += t_size

    return round(today_exposure, 2), round(future_exposure, 2), round(excluded_exposure, 2), excluded_count


def _compute_active_weather_exposure(db, signals: list, today_est=None) -> tuple[float, float, int]:
    """
    Backwards-compatible wrapper returning (total_active_exposure_usd, excluded_exposure_usd, excluded_count).
    """
    today_exp, future_exp, excluded_exp, excluded_cnt = _compute_staged_weather_exposure(
        db, signals, today_est=today_est
    )
    return round(today_exp + future_exp, 2), excluded_exp, excluded_cnt


async def weather_scan_and_trade_job():
    """
    Background job: Scan weather temperature markets, generate signals, execute trades.
    Runs every 5 minutes when WEATHER_ENABLED.
    """
    log_event("info", "Scanning weather temperature markets...")

    try:
        from datetime import date
        from zoneinfo import ZoneInfo
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

            # C-137 Staged Rolling Target-Date Vintage Caps:
            # - Today (T+0): 25% of bankroll ($25.00 floor) for high-precision same-day + ASOS ratchet setups
            # - Tomorrow/Future (T+1): 12.5% of bankroll ($12.50 floor) pre-allocation with 12% min edge hurdle;
            #   automatically matures into the 25% Today bucket at midnight EST with >=12.5% dry powder left!
            MAX_TODAY_ALLOCATION = max(25.0, round(state.bankroll * 0.25, 2))
            MAX_FUTURE_ALLOCATION = max(12.5, round(state.bankroll * 0.125, 2))
            FUTURE_MIN_EDGE_HURDLE = getattr(settings, "WEATHER_FUTURE_MIN_EDGE_THRESHOLD", 0.12)

            today_est = datetime.now(ZoneInfo("America/New_York")).date()
            today_pending, future_pending, excluded_pending, excluded_count = _compute_staged_weather_exposure(
                db, signals, today_est=today_est
            )
            if excluded_count > 0:
                log_event(
                    "info",
                    f"C-137 Limiter Bypass: Excluded {excluded_count} outcome-pending/expected-win position(s) "
                    f"(${excluded_pending:.2f}) -> Today: ${today_pending:.2f}/${MAX_TODAY_ALLOCATION:.2f} | "
                    f"Future: ${future_pending:.2f}/${MAX_FUTURE_ALLOCATION:.2f}",
                )

            trades_executed = 0
            paper_trades_executed = 0
            attempted_live_tickers = set()
            live_held_tickers = set()
            logged_today_cap = False
            logged_future_cap = False

            # City concentration map: track open positions per (city, target_date)
            max_pos_per_city_date = getattr(settings, "WEATHER_MAX_POSITIONS_PER_CITY_DATE", 1)
            city_date_counts = {}
            open_live_trades = db.query(Trade).filter(
                Trade.settled == False,
                Trade.market_type == "weather",
                Trade.is_paper == False,
            ).all()
            for ot in open_live_trades:
                c, d = _extract_ticker_city_and_date(ot.market_ticker or "")
                if c and d:
                    city_date_counts[(c, d)] = city_date_counts.get((c, d), 0) + 1

            # --- TRACK 1: TOP-TIER LIVE PRODUCTION KALSHI TRADING ---
            # Only execute into the live production database (tradingbot.db) when live order execution
            # is enabled (KALSHI_EXECUTE_ORDERS=true or SIMULATION_MODE=false).
            if settings.KALSHI_EXECUTE_ORDERS or not settings.SIMULATION_MODE:
                for signal in actionable:
                    # Check if we already have an active LIVE trade for this market
                    existing_live = db.query(Trade).filter(
                        Trade.market_ticker == signal.market.market_id,
                        Trade.settled == False,
                        Trade.is_paper == False,
                    ).first()

                    is_dust_topup = False
                    if existing_live:
                        existing_size = getattr(existing_live, "size", None)
                        if (
                            isinstance(existing_size, (int, float))
                            and 0 < float(existing_size) < MIN_TRADE_SIZE
                            and getattr(existing_live, "direction", None) == signal.direction
                        ):
                            # Sub-$1.00 dust stub fill (e.g. $0.03 or $0.05 fractional IOC sweep):
                            # allow topping up the remaining size and merging into the existing row!
                            is_dust_topup = True
                        else:
                            live_held_tickers.add(signal.market.market_id)
                            continue

                    if signal.suggested_size <= 0:
                        continue

                    if trades_executed >= MAX_TRADES_PER_SCAN:
                        break

                    if today_pending >= MAX_TODAY_ALLOCATION and future_pending >= MAX_FUTURE_ALLOCATION:
                        log_event(
                            "info",
                            f"Both weather buckets full: Today ${today_pending:.2f}/${MAX_TODAY_ALLOCATION:.2f}, "
                            f"Future ${future_pending:.2f}/${MAX_FUTURE_ALLOCATION:.2f}",
                        )
                        break

                    sig_target_dt = _parse_ticker_target_date(signal.market.market_id)
                    if sig_target_dt is None:
                        mkt_dt = getattr(signal.market, "target_date", None)
                        if isinstance(mkt_dt, date):
                            sig_target_dt = mkt_dt
                    is_future_contract = (sig_target_dt is not None and sig_target_dt > today_est)

                    sig_city = getattr(signal.market, "city_key", None)
                    if not sig_city:
                        sig_city, _ = _extract_ticker_city_and_date(signal.market.market_id)

                    # Enforce city-date concentration limits (e.g. max 1 position per city per date)
                    if not is_dust_topup and sig_city and sig_target_dt:
                        current_city_cnt = city_date_counts.get((sig_city, sig_target_dt), 0)
                        if current_city_cnt >= max_pos_per_city_date:
                            log_event("info", f"City concentration limit ({max_pos_per_city_date}) reached for {sig_city} on {sig_target_dt}; skipping correlated strike")
                            continue

                    if is_future_contract:
                        if signal.edge < FUTURE_MIN_EDGE_HURDLE:
                            continue
                        if future_pending >= MAX_FUTURE_ALLOCATION:
                            if not logged_future_cap:
                                log_event(
                                    "info",
                                    f"Future (T+1) weather bucket limit reached: ${future_pending:.2f}/${MAX_FUTURE_ALLOCATION:.2f}",
                                )
                                logged_future_cap = True
                            continue
                    else:
                        if today_pending >= MAX_TODAY_ALLOCATION:
                            if not logged_today_cap:
                                log_event(
                                    "info",
                                    f"Today (T+0) weather bucket limit reached: ${today_pending:.2f}/${MAX_TODAY_ALLOCATION:.2f}",
                                )
                                logged_today_cap = True
                            continue

                    if state.bankroll < MIN_TRADE_SIZE:
                        log_event("warning", f"Bankroll too low: ${state.bankroll:.2f}")
                        break

                    attempted_live_tickers.add(signal.market.market_id)
                    target_size = max(min(signal.suggested_size, settings.WEATHER_MAX_TRADE_SIZE), MIN_TRADE_SIZE)
                    if is_dust_topup:
                        trade_size = max(MIN_TRADE_SIZE, round(target_size - float(existing_live.size or 0.0), 2))
                    else:
                        trade_size = target_size

                    entry_price = signal.market.yes_price if signal.direction == "yes" else signal.market.no_price

                    # Live order execution on Kalshi Prod
                    kalshi_order_id = None
                    filled_contracts = 0.0
                    if getattr(signal.market, "platform", "") == "kalshi":
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
                                log_event("trade", f"KALSHI LIVE ORDER FILLED: {kalshi_order_id} | {filled_contracts:g}x {signal.direction.upper()} on {signal.market.market_id}", order_res)
                            except Exception as e:
                                log_event("error", f"Kalshi order placement error: {e}")
                                continue

                    if is_dust_topup and existing_live is not None:
                        old_size = float(existing_live.size or 0.0)
                        old_price = float(existing_live.entry_price or entry_price)
                        old_contracts = (old_size / old_price) if old_price > 0 else 0.0
                        add_contracts = filled_contracts if filled_contracts > 0 else (trade_size / entry_price if entry_price > 0 else 0.0)
                        tot_contracts = old_contracts + add_contracts
                        merged_size = round(old_size + trade_size, 2)
                        merged_price = round(merged_size / tot_contracts, 4) if tot_contracts > 0 else entry_price
                        existing_live.size = merged_size
                        existing_live.entry_price = merged_price
                        existing_live.model_probability = signal.model_probability
                        existing_live.market_price_at_entry = signal.market_probability
                        existing_live.edge_at_entry = signal.edge
                        trade = existing_live
                        db.flush()
                    else:
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
                    if sig_city and sig_target_dt:
                        city_date_counts[(sig_city, sig_target_dt)] = city_date_counts.get((sig_city, sig_target_dt), 0) + 1
                    if is_future_contract:
                        future_pending += trade_size
                    else:
                        today_pending += trade_size

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

            # --- TRACK 2: SHADOW PAPER WEATHER TRAINING (ISOLATED IN paper_training.db) ---
            # Paper training trades are stored exclusively in PaperSessionLocal (paper_training.db)
            # so they never pollute the live production database or live dashboard UI.
            paper_hurdle = getattr(settings, "WEATHER_PAPER_MIN_EDGE_THRESHOLD", 0.03)
            paper_db = PaperSessionLocal()
            try:
                for signal in signals:
                    ticker = signal.market.market_id
                    if ticker in attempted_live_tickers or ticker in live_held_tickers:
                        continue

                    if signal.edge < paper_hurdle:
                        continue

                    entry_price = signal.market.yes_price if signal.direction == "yes" else signal.market.no_price
                    if entry_price <= 0.0 or entry_price >= 1.0:
                        continue

                    # Check if trade already exists in paper_training.db
                    existing_paper = paper_db.query(Trade).filter(
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

                    paper_db.add(paper_trade)
                    paper_db.flush()

                    # Link to signal record in paper_training.db
                    matching_sig = paper_db.query(Signal).filter(
                        Signal.market_ticker == ticker,
                        Signal.market_type == "weather",
                        Signal.executed == False,
                    ).order_by(Signal.timestamp.desc()).first()
                    if matching_sig:
                        matching_sig.executed = True
                        matching_sig.is_paper = True
                        paper_trade.signal_id = matching_sig.id

                    paper_trades_executed += 1

                paper_db.commit()
            finally:
                paper_db.close()

            state.last_run = datetime.utcnow()
            db.commit()

            if trades_executed > 0:
                log_event("success", f"Executed {trades_executed} live weather trade(s)")
            elif not settings.SIMULATION_MODE:
                log_event("info", "No new live weather trades executed")
            else:
                logger.info(f"Weather scan complete (SIMULATION_MODE=true; {paper_trades_executed} training trades logged to paper_training.db)")

        finally:
            db.close()

    except Exception as e:
        log_event("error", f"Weather scan error: {str(e)}")
        logger.exception("Error in weather_scan_and_trade_job")


async def settlement_job():
    """
    Background job: Check and settle pending trades.
    Runs every 2 minutes.
    """
    log_event("info", "Checking trade settlements...")

    try:
        from backend.core.settlement import settle_pending_trades, update_bot_state_with_settlements

        db = SessionLocal()
        try:
            pending_count = db.query(Trade).filter(Trade.settled == False).count()

            if pending_count > 0:
                log_event("data", f"Processing {pending_count} pending live trades")
                settled = await settle_pending_trades(db)

                if settled:
                    await update_bot_state_with_settlements(db, settled)

                    wins = sum(1 for t in settled if t.result == "win")
                    losses = sum(1 for t in settled if t.result == "loss")
                    total_pnl = sum(t.pnl for t in settled if t.pnl is not None)

                    log_event("success", f"Settled {len(settled)} live trades: {wins}W/{losses}L, P&L: ${total_pnl:.2f}", {
                        "settled_count": len(settled),
                        "wins": wins,
                        "losses": losses,
                        "pnl": total_pnl
                    })

                    for trade in settled:
                        result_prefix = "+" if trade.pnl and trade.pnl > 0 else ""
                        log_event("data", f"  {trade.event_slug}: {trade.result.upper()} {result_prefix}${trade.pnl:.2f}")
        finally:
            db.close()

        # Also settle pending paper training trades inside paper_training.db silently
        paper_db = PaperSessionLocal()
        try:
            paper_pending = paper_db.query(Trade).filter(
                Trade.settled == False,
                Trade.market_type != "weather_hourly",
            ).count()
            if paper_pending > 0:
                paper_settled = await settle_pending_trades(paper_db, record_calibration=False)
                if paper_settled:
                    paper_db.commit()
                    logger.info(f"Settled {len(paper_settled)} daily paper training trades in paper_training.db")
        finally:
            paper_db.close()

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

        if settings.KALSHI_SYNC_BALANCE:
            try:
                from backend.data.kalshi_client import KalshiClient, kalshi_credentials_present
                if kalshi_credentials_present():
                    bal_data = await KalshiClient().get_balance()
                    if bal_data.get("balance_dollars") is not None:
                        state.bankroll = float(bal_data["balance_dollars"])
                        db.commit()
                    elif bal_data.get("balance") is not None:
                        state.bankroll = float(bal_data["balance"]) / 100.0
                        db.commit()
            except Exception as sync_err:
                logger.debug(f"Heartbeat Kalshi balance sync skipped: {sync_err}")

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

    # Check settlements for all active markets (BTC and Daily Weather)
    if settings.BTC_ENABLED or settings.WEATHER_ENABLED:
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

    # Hourly weather trading jobs (gated by HOURLY_WEATHER_ENABLED)
    if getattr(settings, "HOURLY_WEATHER_ENABLED", False):
        from backend.core.hourly_scheduler import hourly_scan_and_trade_job, hourly_settlement_job
        hourly_scan_seconds = getattr(settings, "HOURLY_SCAN_INTERVAL_SECONDS", 120)
        hourly_settle_seconds = getattr(settings, "HOURLY_SETTLEMENT_INTERVAL_SECONDS", 300)

        scheduler.add_job(
            hourly_scan_and_trade_job,
            IntervalTrigger(seconds=hourly_scan_seconds),
            id="hourly_weather_scan",
            replace_existing=True,
            max_instances=1,
        )

        scheduler.add_job(
            hourly_settlement_job,
            IntervalTrigger(seconds=hourly_settle_seconds),
            id="hourly_weather_settlement",
            replace_existing=True,
            max_instances=1,
        )

    scheduler.start()
    log_event("success", "Autonomous trading scheduler started", {
        "scan_interval": f"{scan_seconds}s",
        "settlement_interval": f"{settle_seconds}s",
        "btc_enabled": settings.BTC_ENABLED,
        "weather_enabled": settings.WEATHER_ENABLED,
        "hourly_weather_enabled": getattr(settings, "HOURLY_WEATHER_ENABLED", False),
    })

    if settings.BTC_ENABLED:
        asyncio.create_task(scan_and_trade_job())

    if settings.WEATHER_ENABLED:
        asyncio.create_task(weather_scan_and_trade_job())

    if getattr(settings, "HOURLY_WEATHER_ENABLED", False):
        from backend.core.hourly_scheduler import hourly_scan_and_trade_job
        asyncio.create_task(hourly_scan_and_trade_job())


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
