"""Trade settlement logic for BTC 5-min and weather markets using Polymarket API."""
import httpx
import json
import logging
from datetime import datetime, date
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from backend.models.database import Trade, BotState, Signal
from backend.analytics.calibration import calibration_harness

logger = logging.getLogger("trading_bot")


async def fetch_polymarket_resolution(market_id: str, event_slug: Optional[str] = None) -> Tuple[bool, Optional[float]]:
    """
    Fetch actual market resolution from Polymarket API.

    For BTC 5-min markets, uses event slug to find the market.

    Returns: (is_resolved, settlement_value)
        - settlement_value: 1.0 if Up won, 0.0 if Down won
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try event slug first (more reliable for BTC 5-min markets)
            if event_slug:
                response = await client.get(
                    "https://gamma-api.polymarket.com/events",
                    params={"slug": event_slug}
                )
                response.raise_for_status()
                events = response.json()

                if events:
                    event = events[0] if isinstance(events, list) else events
                    markets = event.get("markets", [])
                    if markets:
                        return _parse_market_resolution(markets[0])

            # Fallback: try market ID directly
            url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            response = await client.get(url)

            if response.status_code == 404:
                return await _search_market_in_events(market_id)

            response.raise_for_status()
            market = response.json()
            return _parse_market_resolution(market)

    except Exception as e:
        logger.warning(f"Failed to fetch resolution for {event_slug or market_id}: {e}")
        return False, None


async def _search_market_in_events(market_id: str) -> Tuple[bool, Optional[float]]:
    """Search for market in events (both active and closed)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for closed in [True, False]:
                params = {
                    "closed": str(closed).lower(),
                    "limit": 200
                }
                response = await client.get(
                    "https://gamma-api.polymarket.com/events",
                    params=params
                )
                response.raise_for_status()
                events = response.json()

                for event in events:
                    for market in event.get("markets", []):
                        if str(market.get("id")) == str(market_id):
                            return _parse_market_resolution(market)

        return False, None

    except Exception as e:
        logger.warning(f"Failed to search for market {market_id}: {e}")
        return False, None


def _parse_market_resolution(market: dict) -> Tuple[bool, Optional[float]]:
    """
    Parse market data to determine if resolved and outcome.

    Handles both Yes/No and Up/Down outcomes.
    - outcomePrices[0] > 0.99 -> first outcome won (Yes or Up)
    - outcomePrices[0] < 0.01 -> second outcome won (No or Down)
    """
    is_closed = market.get("closed", False)

    if not is_closed:
        return False, None

    outcome_prices = market.get("outcomePrices", [])
    if not outcome_prices:
        return False, None

    try:
        if isinstance(outcome_prices, str):
            outcome_prices = json.loads(outcome_prices)

        first_price = float(outcome_prices[0]) if outcome_prices else 0.5

        if first_price > 0.99:
            # First outcome won (Up or Yes)
            logger.info(f"Market {market.get('id')} resolved: UP/YES won")
            return True, 1.0
        elif first_price < 0.01:
            # Second outcome won (Down or No)
            logger.info(f"Market {market.get('id')} resolved: DOWN/NO won")
            return True, 0.0
        else:
            return False, None

    except (ValueError, IndexError, TypeError) as e:
        logger.warning(f"Failed to parse outcome prices: {e}")
        return False, None


def calculate_pnl(trade: Trade, settlement_value: float) -> float:
    """
    Calculate net P&L for a trade given the settlement value.

    settlement_value: 1.0 if Up/Yes outcome, 0.0 if Down/No outcome.

    trade.size is the dollar capital allocated to the trade.
    If entry_price is P (where 0 < P < 1):
      - Contracts purchased = trade.size / P
      - Estimated transaction fee: $0.01 per contract round-trip
      - On WIN: Gross payout = (trade.size / P) * 1.0, Net PnL = trade.size * (1 - P) / P - fees
      - On LOSS: Net PnL = -trade.size - fees
    """
    direction = (trade.direction or "yes").lower()
    won = (
        (direction in ("up", "yes") and settlement_value == 1.0)
        or (direction in ("down", "no") and settlement_value == 0.0)
    )

    p = max(0.01, min(0.99, trade.entry_price or 0.50))
    capital_risked = trade.size
    contracts = capital_risked / p
    # Realistic taker exchange fee (~$0.01 per contract)
    fee = round(contracts * 0.01, 2)

    if won:
        gross_profit = capital_risked * (1.0 - p) / p
        pnl = gross_profit - fee
    else:
        pnl = -capital_risked - fee

    return round(pnl, 2)


async def check_market_settlement(trade: Trade) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Check if a trade's market has settled.

    Returns: (is_settled, settlement_value, pnl)
    """
    is_resolved, settlement_value = await fetch_polymarket_resolution(
        trade.market_ticker,
        event_slug=trade.event_slug
    )

    if not is_resolved or settlement_value is None:
        return False, None, None

    pnl = calculate_pnl(trade, settlement_value)

    mapped_dir = "UP" if trade.direction in ("up", "yes") else "DOWN"
    outcome = "UP" if settlement_value == 1.0 else "DOWN"
    result = "WIN" if mapped_dir == outcome else "LOSS"

    logger.info(f"Trade {trade.id} settled: {mapped_dir} @ {trade.entry_price:.0%} -> "
                f"{result} P&L: ${pnl:+.2f}")

    return True, settlement_value, pnl


async def check_weather_settlement(trade: Trade, db: Optional[Session] = None) -> Tuple[bool, Optional[float], Optional[float]]:
    """
    Check if a weather trade's market has settled.
    Routes to the correct platform's resolution method, falling back to official NWS resolution.
    """
    platform = getattr(trade, 'platform', 'polymarket') or 'polymarket'

    if platform == "kalshi":
        is_resolved, settlement_value = await _fetch_kalshi_resolution(trade.market_ticker)
    else:
        is_resolved, settlement_value = await fetch_polymarket_resolution(
            trade.market_ticker,
            event_slug=trade.event_slug,
        )

    # Fallback to official NWS observation resolution if platform resolution is delayed/pending
    if not is_resolved or settlement_value is None:
        is_resolved, settlement_value = await _fetch_nws_resolution(trade, db=db)

    if is_resolved and settlement_value is not None:
        pnl = calculate_pnl(trade, settlement_value)
        return True, settlement_value, pnl

    return False, None, None


async def _fetch_nws_resolution(trade: Trade, db: Optional[Session] = None) -> Tuple[bool, Optional[float]]:
    """
    Check if a weather trade can be settled against official NWS observations
    when platform resolution is delayed, pending, or for shadow paper trades.
    """
    try:
        from backend.data.kalshi_markets import MONTH_ABBR, CITY_SERIES
        from backend.data.weather import fetch_nws_observed_temperature
        import re
        from datetime import date

        ticker = trade.market_ticker or ""
        SERIES_TO_CITY = {v: k for k, v in CITY_SERIES.items()}

        city_key = None
        target_date = None
        strike_type = None
        threshold_f = None

        match = re.match(r'^([A-Z]+)-(\d{2})([A-Z]{3})(\d{2})-([BT])(-?[\d.]+)$', ticker)
        if match:
            series = match.group(1)
            yy = int(match.group(2))
            mon_str = match.group(3)
            dd = int(match.group(4))
            b_type = match.group(5)
            val = float(match.group(6))

            city_key = SERIES_TO_CITY.get(series)
            month = MONTH_ABBR.get(mon_str)
            if month:
                target_date = date(2000 + yy, month, dd)
            strike_type = "between" if b_type == "B" else "above"
            threshold_f = val

        # Fallback to matching city from ticker or event_slug
        if not city_key:
            target_str = (ticker + " " + (trade.event_slug or "")).lower()
            for c_key, c_series in CITY_SERIES.items():
                if c_key in target_str or c_series.lower() in target_str:
                    city_key = c_key
                    break

        if not city_key:
            return False, None

        # If date could not be parsed from ticker, try trade.timestamp or signal
        if not target_date and db and trade.signal_id:
            from backend.models.database import Signal
            sig = db.query(Signal).filter(Signal.id == trade.signal_id).first()
            if sig and sig.timestamp:
                target_date = sig.timestamp.date()

        if not target_date:
            return False, None

        # Only finalize against NWS observations if target date has completed (past date)
        if target_date >= date.today():
            return False, None

        obs = await fetch_nws_observed_temperature(city_key, target_date)
        if not obs or "high" not in obs:
            return False, None

        obs_high = obs["high"]
        if threshold_f is not None:
            if strike_type == "between":
                floor = threshold_f - 0.5
                cap = threshold_f + 0.5
                won_yes = (floor <= obs_high <= cap)
            else:
                won_yes = (obs_high > threshold_f)
            return True, (1.0 if won_yes else 0.0)

        return False, None
    except Exception as e:
        logger.warning(f"Failed to fetch NWS resolution for {trade.market_ticker}: {e}")
        return False, None


async def _fetch_kalshi_resolution(ticker: str) -> Tuple[bool, Optional[float]]:
    """Fetch resolution status for a Kalshi market (works on public market endpoint)."""
    try:
        from backend.data.kalshi_client import KalshiClient

        client = KalshiClient()
        data = await client.get_market(ticker)
        market = data.get("market", data)

        status = (market.get("status") or "").lower()
        result = (market.get("result") or "").lower()
        settlement_val_str = market.get("settlement_value_dollars")
        settlement_val_cents = market.get("settlement_value")

        if status == "finalized":
            if result == "yes":
                return True, 1.0
            elif result == "no":
                return True, 0.0
            elif settlement_val_str is not None:
                try:
                    sv = float(settlement_val_str)
                    if sv >= 0.99:
                        return True, 1.0
                    elif sv <= 0.01:
                        return True, 0.0
                except (ValueError, TypeError):
                    pass
            elif settlement_val_cents is not None:
                try:
                    sv = float(settlement_val_cents) / 100.0
                    if sv >= 0.99:
                        return True, 1.0
                    elif sv <= 0.01:
                        return True, 0.0
                except (ValueError, TypeError):
                    pass

        return False, None

    except Exception as e:
        logger.warning(f"Failed to fetch Kalshi resolution for {ticker}: {e}")
        return False, None


async def settle_pending_trades(db: Session) -> List[Trade]:
    """
    Process all pending trades for settlement.
    Uses REAL market outcomes from Polymarket API.
    """
    try:
        pending = db.query(Trade).filter(Trade.settled == False).all()
    except Exception as e:
        logger.error(f"Failed to query pending trades: {e}")
        return []

    if not pending:
        logger.info("No pending trades to settle")
        return []

    logger.info(f"Checking {len(pending)} pending trades for settlement...")
    settled_trades = []

    for trade in pending:
        try:
            # Route settlement by market type
            market_type = getattr(trade, 'market_type', 'btc') or 'btc'
            if market_type == "weather":
                is_settled, settlement_value, pnl = await check_weather_settlement(trade, db=db)
            else:
                is_settled, settlement_value, pnl = await check_market_settlement(trade)

            if is_settled and settlement_value is not None:
                trade.settled = True
                trade.settlement_value = settlement_value
                trade.pnl = pnl
                trade.settlement_time = datetime.utcnow()

                if pnl is not None and pnl > 0:
                    trade.result = "win"
                elif pnl is not None and pnl < 0:
                    trade.result = "loss"
                else:
                    trade.result = "push"

                settled_trades.append(trade)

                # Record to C-137 calibration harness
                try:
                    cat = getattr(trade, 'market_type', 'btc') or 'btc'
                    raw_model_prob = getattr(trade, 'model_probability', None)
                    dir_lower = (getattr(trade, 'direction', 'yes') or 'yes').lower()
                    if raw_model_prob is not None:
                        pred_prob = raw_model_prob if dir_lower in ("up", "yes") else (1.0 - raw_model_prob)
                    else:
                        pred_prob = getattr(trade, 'entry_price', 0.5) or 0.5
                    calibration_harness.record_settlement(
                        trade_id=str(trade.id),
                        ticker=trade.market_ticker,
                        category=cat,
                        predicted_prob=pred_prob,
                        actual_outcome=1.0 if trade.result == "win" else 0.0,
                        size=trade.size,
                        entry_price=trade.entry_price,
                        pnl=pnl or 0.0
                    )
                except Exception as ce:
                    logger.debug(f"Failed to record C-137 calibration for trade {trade.id}: {ce}")

                # Update linked Signal with actual outcome for calibration
                if trade.signal_id:
                    linked_signal = db.query(Signal).filter(Signal.id == trade.signal_id).first()
                    if linked_signal:
                        if getattr(linked_signal, "market_type", "btc") == "weather" or linked_signal.direction in ("yes", "no"):
                            actual_outcome = "yes" if settlement_value == 1.0 else "no"
                        else:
                            actual_outcome = "up" if settlement_value == 1.0 else "down"
                        linked_signal.actual_outcome = actual_outcome
                        linked_signal.outcome_correct = (linked_signal.direction == actual_outcome)
                        linked_signal.settlement_value = settlement_value
                        linked_signal.settled_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"Failed to settle trade {trade.id}: {e}")
            continue

    if settled_trades:
        try:
            db.commit()
            logger.info(f"Settled {len(settled_trades)} trades")
        except Exception as e:
            logger.error(f"Failed to commit settlements: {e}")
            db.rollback()
            return []
    else:
        logger.info("No trades ready for settlement (markets still open)")

    return settled_trades


async def update_bot_state_with_settlements(db: Session, settled_trades: List[Trade]) -> None:
    """Update bot state with P&L from settled trades."""
    if not settled_trades:
        return

    try:
        state = db.query(BotState).first()
        if not state:
            logger.warning("Bot state not found")
            return

        for trade in settled_trades:
            # Paper mode (BTC or shadow paper weather): calibrate model without risking live bankroll
            is_paper = getattr(trade, "is_paper", False) or (getattr(trade, "market_type", "btc") == "btc")
            if trade.pnl is not None and not is_paper:
                state.total_pnl += trade.pnl
                state.bankroll += trade.pnl

        # Reconcile winning trades count with actual live settled count
        state.winning_trades = db.query(Trade).filter(
            Trade.settled == True,
            Trade.is_paper == False,
            Trade.result == "win"
        ).count()

        # Reconcile total trades count with actual live trades count
        state.total_trades = db.query(Trade).filter(
            Trade.is_paper == False
        ).count()

        db.commit()
        logger.info(f"Updated bot state: Bankroll ${state.bankroll:.2f}, P&L ${state.total_pnl:+.2f}, Wins: {state.winning_trades}")
    except Exception as e:
        logger.error(f"Failed to update bot state: {e}")
        db.rollback()
