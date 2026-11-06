"""FastAPI backend for BTC 5-min trading bot dashboard."""
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
import asyncio
import json
import os

from backend.config import settings
from backend.models.database import (
    get_db, init_db, SessionLocal,
    Signal, Trade, BotState, AILog, ScanLog
)
from backend.core.signals import scan_for_signals, TradingSignal
from backend.data.btc_markets import fetch_active_btc_markets, BtcMarket
from backend.data.crypto import fetch_crypto_price, compute_btc_microstructure

from pydantic import BaseModel

app = FastAPI(
    title="BTC 5-Min Trading Bot",
    description="Polymarket BTC Up/Down 5-minute market trading bot",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


ws_manager = ConnectionManager()


# Pydantic response models
class BtcPriceResponse(BaseModel):
    price: float
    change_24h: float
    change_7d: float
    market_cap: float
    volume_24h: float
    last_updated: datetime


class BtcWindowResponse(BaseModel):
    slug: str
    market_id: str
    up_price: float
    down_price: float
    window_start: datetime
    window_end: datetime
    volume: float
    is_active: bool
    is_upcoming: bool
    time_until_end: float
    spread: float


class MicrostructureResponse(BaseModel):
    rsi: float = 50.0
    momentum_1m: float = 0.0
    momentum_5m: float = 0.0
    momentum_15m: float = 0.0
    vwap_deviation: float = 0.0
    sma_crossover: float = 0.0
    volatility: float = 0.0
    price: float = 0.0
    source: str = "unknown"


class SignalResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    market_ticker: str
    market_title: str
    platform: str
    direction: str
    model_probability: float
    market_probability: float
    edge: float
    confidence: float
    suggested_size: float
    reasoning: str
    timestamp: datetime
    category: str = "crypto"
    event_slug: Optional[str] = None
    btc_price: float = 0.0
    btc_change_24h: float = 0.0
    window_end: Optional[datetime] = None
    actionable: bool = False


class TradeResponse(BaseModel):
    id: int
    market_ticker: str
    platform: str
    event_slug: Optional[str] = None
    direction: str
    entry_price: float
    size: float
    timestamp: datetime
    settled: bool
    result: str
    pnl: Optional[float]
    is_paper: Optional[bool] = False


class BotStats(BaseModel):
    bankroll: float
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl: float
    is_running: bool
    last_run: Optional[datetime]
    paper_trades: Optional[int] = 0
    paper_winning_trades: Optional[int] = 0
    paper_win_rate: Optional[float] = 0.0
    paper_pnl: Optional[float] = 0.0


class CalibrationBucket(BaseModel):
    bucket: str
    predicted_avg: float
    actual_rate: float
    count: int


class CalibrationSummary(BaseModel):
    total_signals: int
    total_with_outcome: int
    accuracy: float
    avg_predicted_edge: float
    avg_actual_edge: float
    brier_score: float


class WeatherForecastResponse(BaseModel):
    city_key: str
    city_name: str
    target_date: str
    mean_high: float
    std_high: float
    mean_low: float
    std_low: float
    num_members: int
    ensemble_agreement: float


class WeatherMarketResponse(BaseModel):
    slug: str
    market_id: str
    platform: str = "polymarket"
    title: str
    city_key: str
    city_name: str
    target_date: str
    threshold_f: float
    metric: str
    direction: str
    yes_price: float
    no_price: float
    volume: float


class WeatherSignalResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    market_id: str
    city_key: str
    city_name: str
    target_date: str
    threshold_f: float
    metric: str
    direction: str
    model_probability: float
    market_probability: float
    edge: float
    confidence: float
    suggested_size: float
    reasoning: str
    ensemble_mean: float
    ensemble_std: float
    ensemble_members: int
    actionable: bool = False


class DashboardData(BaseModel):
    stats: BotStats
    btc_price: Optional[BtcPriceResponse]
    microstructure: Optional[MicrostructureResponse] = None
    windows: List[BtcWindowResponse]
    active_signals: List[SignalResponse]
    recent_trades: List[TradeResponse]
    equity_curve: List[dict]
    calibration: Optional[CalibrationSummary] = None
    weather_signals: List[WeatherSignalResponse] = []
    weather_forecasts: List[WeatherForecastResponse] = []


class EventResponse(BaseModel):
    timestamp: str
    type: str
    message: str
    data: dict = {}


# Startup / Shutdown
@app.on_event("startup")
async def startup():
    print("=" * 60)
    print("BTC 5-MIN TRADING BOT v3.0")
    print("=" * 60)
    print("Initializing database...")

    init_db()

    db = SessionLocal()
    try:
        from backend.data.kalshi_client import kalshi_credentials_present, KalshiClient
        state = db.query(BotState).first()
        if not state:
            state = BotState(
                bankroll=settings.INITIAL_BANKROLL,
                total_trades=0,
                winning_trades=0,
                total_pnl=0.0,
                is_running=True
            )
            db.add(state)
            db.commit()
            print(f"Created new bot state with ${settings.INITIAL_BANKROLL:,.2f} bankroll")
        else:
            state.is_running = True
            db.commit()
            print(f"Loaded bot state: Bankroll ${state.bankroll:,.2f}, P&L ${state.total_pnl:+,.2f}, {state.total_trades} trades")

        if settings.KALSHI_SYNC_BALANCE and kalshi_credentials_present():
            try:
                client = KalshiClient()
                bal_data = await client.get_balance()
                if bal_data.get("balance_dollars") is not None:
                    real_bal = float(bal_data["balance_dollars"])
                    state.bankroll = real_bal
                    db.commit()
                    print(f"💰 Synced bankroll with live Kalshi Demo balance: ${real_bal:,.2f}")
                elif bal_data.get("balance") is not None:
                    real_bal = float(bal_data["balance"]) / 100.0
                    state.bankroll = real_bal
                    db.commit()
                    print(f"💰 Synced bankroll with live Kalshi Demo balance: ${real_bal:,.2f}")
            except Exception as e:
                print(f"Could not auto-sync Kalshi balance: {e}")
    finally:
        db.close()

    print("")
    print("Configuration:")
    print(f"  - Simulation mode: {settings.SIMULATION_MODE}")
    print(f"  - Min edge threshold: {settings.MIN_EDGE_THRESHOLD:.0%}")
    print(f"  - Kelly fraction: {settings.KELLY_FRACTION:.0%}")
    print(f"  - Scan interval: {settings.SCAN_INTERVAL_SECONDS}s")
    print(f"  - Settlement interval: {settings.SETTLEMENT_INTERVAL_SECONDS}s")
    print("")

    from backend.core.scheduler import start_scheduler, log_event
    start_scheduler()
    log_event("success", "BTC 5-min trading bot initialized")

    print("Bot is now running!")
    if settings.BTC_ENABLED:
        print(f"  - BTC scan: every {settings.SCAN_INTERVAL_SECONDS}s (edge >= {settings.MIN_EDGE_THRESHOLD:.0%})")
        print(f"  - BTC settlement check: every {settings.SETTLEMENT_INTERVAL_SECONDS}s")
    else:
        print("  - BTC 5-min trading: DISABLED (C-137 lockdown: negative edge asset retired)")
    if settings.WEATHER_ENABLED:
        print(f"  - Weather scan: every {settings.WEATHER_SCAN_INTERVAL_SECONDS}s (edge >= {settings.WEATHER_MIN_EDGE_THRESHOLD:.0%})")
        print(f"  - Weather cities: {settings.WEATHER_CITIES}")
    else:
        print("  - Weather trading: DISABLED")
    if getattr(settings, "HOURLY_WEATHER_ENABLED", False):
        print(f"  - Hourly METAR Paper scan: every {settings.HOURLY_SCAN_INTERVAL_SECONDS}s (edge >= {settings.HOURLY_MIN_EDGE_THRESHOLD:.0%})")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown():
    from backend.core.scheduler import stop_scheduler
    stop_scheduler()


# Static frontend directory (for single-service deployment on GCP)
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    from fastapi.staticfiles import StaticFiles
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


# Core endpoints
@app.get("/")
async def root(request: Request):
    index_html = os.path.join(frontend_dist, "index.html")
    accept = request.headers.get("accept", "")
    if os.path.exists(index_html) and "application/json" not in accept:
        from starlette.responses import FileResponse
        return FileResponse(index_html)
    return {"status": "ok", "message": "BTC 5-Min Trading Bot API v3.0", "simulation_mode": settings.SIMULATION_MODE}


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/stats", response_model=BotStats)
async def get_stats(db: Session = Depends(get_db)):
    state = db.query(BotState).first()
    if not state:
        raise HTTPException(status_code=404, detail="Bot state not initialized")

    # Win rate calculated strictly over settled LIVE trades, preventing in-flight and paper distortions
    live_trades = db.query(Trade).filter(Trade.is_paper == False).all()
    live_settled = [t for t in live_trades if t.settled and t.result in ("win", "loss")]
    live_wins = sum(1 for t in live_settled if t.result == "win")
    live_total = len(live_settled)
    live_win_rate = (live_wins / live_total) if live_total > 0 else 0.0

    # Separate paper trading telemetry (high-volume data harvesting)
    paper_trades = db.query(Trade).filter(Trade.is_paper == True).all()
    paper_settled = [t for t in paper_trades if t.settled and t.result in ("win", "loss")]
    paper_wins = sum(1 for t in paper_settled if t.result == "win")
    paper_total = len(paper_settled)
    paper_win_rate = (paper_wins / paper_total) if paper_total > 0 else 0.0
    paper_pnl = sum(t.pnl for t in paper_settled if t.pnl is not None)

    return BotStats(
        bankroll=round(state.bankroll, 2),
        total_trades=len(live_trades),
        winning_trades=live_wins,
        win_rate=round(live_win_rate, 4),
        total_pnl=round(state.total_pnl, 2),
        is_running=state.is_running,
        last_run=state.last_run,
        paper_trades=len(paper_trades),
        paper_winning_trades=paper_wins,
        paper_win_rate=round(paper_win_rate, 4),
        paper_pnl=round(paper_pnl, 2),
    )


# BTC-specific endpoints
@app.get("/api/btc/price", response_model=Optional[BtcPriceResponse])
async def get_btc_price():
    """Get current BTC price and momentum data."""
    try:
        btc = await fetch_crypto_price("BTC")
        if not btc:
            return None

        return BtcPriceResponse(
            price=btc.current_price,
            change_24h=btc.change_24h,
            change_7d=btc.change_7d,
            market_cap=btc.market_cap,
            volume_24h=btc.volume_24h,
            last_updated=btc.last_updated
        )
    except Exception:
        return None


@app.get("/api/btc/windows", response_model=List[BtcWindowResponse])
async def get_btc_windows():
    """Get upcoming BTC 5-min windows with prices."""
    try:
        markets = await fetch_active_btc_markets()
        return [
            BtcWindowResponse(
                slug=m.slug,
                market_id=m.market_id,
                up_price=m.up_price,
                down_price=m.down_price,
                window_start=m.window_start,
                window_end=m.window_end,
                volume=m.volume,
                is_active=m.is_active,
                is_upcoming=m.is_upcoming,
                time_until_end=m.time_until_end,
                spread=m.spread,
            )
            for m in markets
        ]
    except Exception:
        return []


@app.get("/api/signals", response_model=List[SignalResponse])
async def get_signals():
    """Get current BTC trading signals."""
    try:
        signals = await scan_for_signals()
        return [_signal_to_response(s) for s in signals]
    except Exception:
        return []


@app.get("/api/signals/actionable", response_model=List[SignalResponse])
async def get_actionable_signals():
    """Get only signals that pass the edge threshold."""
    try:
        signals = await scan_for_signals()
        actionable = [s for s in signals if s.passes_threshold]
        return [_signal_to_response(s) for s in actionable]
    except Exception:
        return []


def _signal_to_response(s: TradingSignal, actionable: bool = False) -> SignalResponse:
    return SignalResponse(
        market_ticker=s.market.market_id,
        market_title=f"BTC 5m - {s.market.slug}",
        platform="polymarket",
        direction=s.direction,
        model_probability=s.model_probability,
        market_probability=s.market_probability,
        edge=s.edge,
        confidence=s.confidence,
        suggested_size=s.suggested_size,
        reasoning=s.reasoning,
        timestamp=s.timestamp,
        category="crypto",
        event_slug=s.market.slug,
        btc_price=s.btc_price,
        btc_change_24h=s.btc_change_24h,
        window_end=s.market.window_end,
        actionable=actionable,
    )


@app.get("/api/trades", response_model=List[TradeResponse])
async def get_trades(
    limit: int = 50,
    status: Optional[str] = None,
    is_paper: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Trade)
    if status:
        query = query.filter(Trade.result == status)
    if is_paper is not None:
        query = query.filter(Trade.is_paper == is_paper)
    trades = query.order_by(Trade.timestamp.desc()).limit(limit).all()

    return [
        TradeResponse(
            id=t.id,
            market_ticker=t.market_ticker,
            platform=t.platform,
            event_slug=t.event_slug,
            direction=t.direction,
            entry_price=t.entry_price,
            size=t.size,
            timestamp=t.timestamp,
            settled=t.settled,
            result=t.result,
            pnl=t.pnl,
            is_paper=getattr(t, "is_paper", False),
        )
        for t in trades
    ]


@app.get("/api/equity-curve")
async def get_equity_curve(is_paper: bool = False, db: Session = Depends(get_db)):
    state = db.query(BotState).first()
    # Baseline starting bankroll tracks actual configured capital rather than static defaults
    starting_bankroll = (state.bankroll - state.total_pnl) if state else settings.INITIAL_BANKROLL

    trades = db.query(Trade).filter(
        Trade.settled == True,
        Trade.is_paper == is_paper
    ).order_by(Trade.timestamp).all()

    curve = []
    cumulative_pnl = 0.0

    for trade in trades:
        if trade.pnl is not None:
            cumulative_pnl += trade.pnl
            curve.append({
                "timestamp": trade.timestamp.isoformat(),
                "pnl": round(cumulative_pnl, 2),
                "bankroll": round(starting_bankroll + cumulative_pnl, 2),
                "trade_id": trade.id
            })

    return curve


@app.post("/api/simulate-trade")
async def simulate_trade(signal_ticker: str, db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event

    state = db.query(BotState).first()
    if not state:
        raise HTTPException(status_code=500, detail="Bot state not initialized")

    # 1. Check Hourly Weather Signals (Kalshi Synoptic series e.g. KXTEMPNYCHS, KXTEMPMIAH)
    if "KXTEMP" in signal_ticker.upper():
        from backend.core.hourly_signals import scan_for_hourly_signals
        hourly_signals = await scan_for_hourly_signals()
        h_sig = next((s for s in hourly_signals if s.market.ticker == signal_ticker), None)
        if h_sig:
            trade = Trade(
                market_ticker=h_sig.market.ticker,
                platform="kalshi",
                event_slug=h_sig.market.series_ticker,
                market_type="weather_hourly",
                direction=h_sig.direction,
                entry_price=h_sig.market_price,
                size=h_sig.suggested_size or 5.0,
                model_probability=h_sig.model_probability,
                market_price_at_entry=h_sig.market_price,
                edge_at_entry=h_sig.edge,
                is_paper=True,
                settled=False
            )
            db.add(trade)
            db.commit()
            log_event("trade", f"Manual 1H Paper Trade: {h_sig.direction.upper()} ${trade.size:.2f} on {h_sig.market.ticker}")
            return {"status": "ok", "trade_id": trade.id, "size": trade.size}

    # 2. Check Daily Weather Signals (Kalshi / Polymarket e.g. KXHIGHNY, KXHIGHCHI)
    if settings.WEATHER_ENABLED:
        from backend.core.weather_signals import scan_for_weather_signals
        wx_signals = await scan_for_weather_signals()
        wx_sig = next((s for s in wx_signals if s.market.market_id == signal_ticker), None)
        if wx_sig:
            entry_price = wx_sig.market.yes_price if wx_sig.direction == "yes" else wx_sig.market.no_price
            trade = Trade(
                market_ticker=wx_sig.market.market_id,
                platform=getattr(wx_sig.market, "platform", "kalshi"),
                event_slug=wx_sig.market.slug,
                market_type="weather",
                direction=wx_sig.direction,
                entry_price=entry_price,
                size=min(wx_sig.suggested_size or 5.0, settings.WEATHER_MAX_TRADE_SIZE),
                model_probability=wx_sig.model_probability,
                market_price_at_entry=wx_sig.market_probability,
                edge_at_entry=wx_sig.edge,
                is_paper=True,
                settled=False
            )
            db.add(trade)
            db.commit()
            log_event("trade", f"Manual Daily Paper Trade: {wx_sig.direction.upper()} ${trade.size:.2f} on {wx_sig.market.market_id}")
            return {"status": "ok", "trade_id": trade.id, "size": trade.size}

    # 3. Fallback to BTC signals (if enabled)
    signals = await scan_for_signals()
    signal = next((s for s in signals if s.market.market_id == signal_ticker), None)

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    entry_price = signal.market.up_price if signal.direction == "up" else signal.market.down_price

    trade = Trade(
        market_ticker=signal.market.market_id,
        platform="polymarket",
        event_slug=signal.market.slug,
        market_type="btc",
        direction=signal.direction,
        entry_price=entry_price,
        size=min(signal.suggested_size, state.bankroll * 0.05),
        model_probability=signal.model_probability,
        market_price_at_entry=signal.market_probability,
        edge_at_entry=signal.edge,
        is_paper=True,
    )

    db.add(trade)
    db.commit()

    log_event("trade", f"Manual BTC trade: {signal.direction.upper()} {signal.market.slug}")
    return {"status": "ok", "trade_id": trade.id, "size": trade.size}


@app.post("/api/run-scan")
async def run_scan(db: Session = Depends(get_db)):
    from backend.core.scheduler import run_manual_scan, log_event

    state = db.query(BotState).first()
    if state:
        state.last_run = datetime.utcnow()
        db.commit()

    log_event("info", "Manual scan triggered (BTC + Weather)")
    await run_manual_scan()

    signals = await scan_for_signals()
    actionable = [s for s in signals if s.passes_threshold]

    result = {
        "status": "ok",
        "total_signals": len(signals),
        "actionable_signals": len(actionable),
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Also run weather scan if enabled
    if settings.WEATHER_ENABLED:
        try:
            from backend.core.weather_signals import scan_for_weather_signals
            wx_signals = await scan_for_weather_signals()
            wx_actionable = [s for s in wx_signals if s.passes_threshold]
            result["weather_signals"] = len(wx_signals)
            result["weather_actionable"] = len(wx_actionable)
        except Exception:
            result["weather_signals"] = 0
            result["weather_actionable"] = 0

    return result


@app.post("/api/settle-trades")
async def settle_trades_endpoint(db: Session = Depends(get_db)):
    from backend.core.settlement import settle_pending_trades, update_bot_state_with_settlements
    from backend.core.scheduler import log_event

    log_event("info", "Manual settlement triggered")

    settled = await settle_pending_trades(db)
    await update_bot_state_with_settlements(db, settled)

    return {
        "status": "ok",
        "settled_count": len(settled),
        "trades": [{"id": t.id, "result": t.result, "pnl": t.pnl} for t in settled]
    }


def _compute_calibration_summary(db: Session) -> Optional[CalibrationSummary]:
    """Compute calibration summary from settled signals."""
    total_signals = db.query(Signal).count()
    settled_signals = db.query(Signal).filter(Signal.outcome_correct.isnot(None)).all()

    if not settled_signals:
        return CalibrationSummary(
            total_signals=total_signals,
            total_with_outcome=0,
            accuracy=0.0,
            avg_predicted_edge=0.0,
            avg_actual_edge=0.0,
            brier_score=0.0,
        )

    total_with_outcome = len(settled_signals)
    correct = sum(1 for s in settled_signals if s.outcome_correct)
    accuracy = correct / total_with_outcome if total_with_outcome > 0 else 0.0

    avg_predicted_edge = sum(abs(s.edge) for s in settled_signals) / total_with_outcome
    # Actual edge: for correct predictions, edge was real; for incorrect, edge was negative
    avg_actual_edge = sum(
        abs(s.edge) if s.outcome_correct else -abs(s.edge)
        for s in settled_signals
    ) / total_with_outcome

    # Brier score: mean squared error of probability forecasts
    # For each signal: (predicted_prob - actual_outcome)^2
    brier_sum = 0.0
    for s in settled_signals:
        # Model probability is for UP; actual is 1.0 if UP won, 0.0 if DOWN won
        actual = s.settlement_value if s.settlement_value is not None else 0.5
        brier_sum += (s.model_probability - actual) ** 2
    brier_score = brier_sum / total_with_outcome

    return CalibrationSummary(
        total_signals=total_signals,
        total_with_outcome=total_with_outcome,
        accuracy=accuracy,
        avg_predicted_edge=avg_predicted_edge,
        avg_actual_edge=avg_actual_edge,
        brier_score=brier_score,
    )


@app.get("/api/calibration")
async def get_calibration(db: Session = Depends(get_db)):
    """Return calibration data: predicted probability vs actual win rate."""
    signals = db.query(Signal).filter(Signal.outcome_correct.isnot(None)).all()

    if not signals:
        return {"buckets": [], "summary": None}

    # Bucket signals by model_probability into 5% bins
    from collections import defaultdict
    buckets_data = defaultdict(lambda: {"predicted_sum": 0.0, "correct": 0, "total": 0})

    for s in signals:
        # Bin by 5% increments
        bin_start = int(s.model_probability * 100 // 5) * 5
        bin_end = bin_start + 5
        bucket_key = f"{bin_start}-{bin_end}%"

        buckets_data[bucket_key]["predicted_sum"] += s.model_probability
        buckets_data[bucket_key]["total"] += 1
        if s.outcome_correct:
            buckets_data[bucket_key]["correct"] += 1

    buckets = []
    for bucket_key in sorted(buckets_data.keys()):
        d = buckets_data[bucket_key]
        buckets.append(CalibrationBucket(
            bucket=bucket_key,
            predicted_avg=d["predicted_sum"] / d["total"],
            actual_rate=d["correct"] / d["total"],
            count=d["total"],
        ))

    summary = _compute_calibration_summary(db)

    return {"buckets": buckets, "summary": summary}


# Kalshi endpoints
@app.get("/api/kalshi/status")
async def get_kalshi_status():
    """Test Kalshi API connectivity (demo or prod) and return connection status."""
    from backend.data.kalshi_client import KalshiClient, kalshi_credentials_present

    client = KalshiClient()
    status = {
        "use_demo": settings.KALSHI_USE_DEMO,
        "base_url": client.base_url,
        "credentials_configured": kalshi_credentials_present(),
        "public_api_connected": False,
        "authenticated": False,
    }

    try:
        test_markets = await client.get_markets({"limit": 1})
        status["public_api_connected"] = bool(test_markets)
    except Exception as e:
        status["public_api_error"] = str(e)

    if kalshi_credentials_present():
        try:
            balance_data = await client.get_balance()
            status["authenticated"] = True
            status["balance"] = balance_data
        except Exception as e:
            status["auth_error"] = str(e)

    return {
        "connected": status["public_api_connected"] and (status["authenticated"] or settings.SIMULATION_MODE),
        **status,
    }


# Weather endpoints
@app.get("/api/weather/forecasts", response_model=List[WeatherForecastResponse])
async def get_weather_forecasts():
    """Get ensemble forecasts for configured cities."""
    if not settings.WEATHER_ENABLED:
        return []

    try:
        from backend.data.weather import fetch_ensemble_forecast, CITY_CONFIG
        from datetime import date

        city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]
        forecasts = []

        for city_key in city_keys:
            if city_key not in CITY_CONFIG:
                continue
            forecast = await fetch_ensemble_forecast(city_key)
            if forecast:
                forecasts.append(WeatherForecastResponse(
                    city_key=forecast.city_key,
                    city_name=forecast.city_name,
                    target_date=forecast.target_date.isoformat(),
                    mean_high=forecast.mean_high,
                    std_high=forecast.std_high,
                    mean_low=forecast.mean_low,
                    std_low=forecast.std_low,
                    num_members=forecast.num_members,
                    ensemble_agreement=forecast.ensemble_agreement,
                ))

        return forecasts
    except Exception:
        return []


@app.get("/api/weather/markets", response_model=List[WeatherMarketResponse])
async def get_weather_markets():
    """Get active weather temperature markets."""
    if not settings.WEATHER_ENABLED:
        return []

    try:
        from backend.data.weather_markets import fetch_polymarket_weather_markets

        city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]
        markets = await fetch_polymarket_weather_markets(city_keys)

        # Also fetch Kalshi markets if enabled
        if settings.KALSHI_ENABLED:
            try:
                from backend.data.kalshi_markets import fetch_kalshi_weather_markets
                kalshi_markets = await fetch_kalshi_weather_markets(city_keys)
                markets.extend(kalshi_markets)
            except Exception:
                pass

        return [
            WeatherMarketResponse(
                slug=m.slug,
                market_id=m.market_id,
                platform=m.platform,
                title=m.title,
                city_key=m.city_key,
                city_name=m.city_name,
                target_date=m.target_date.isoformat(),
                threshold_f=m.threshold_f,
                metric=m.metric,
                direction=m.direction,
                yes_price=m.yes_price,
                no_price=m.no_price,
                volume=m.volume,
            )
            for m in markets
        ]
    except Exception:
        return []


@app.get("/api/weather/signals", response_model=List[WeatherSignalResponse])
async def get_weather_signals():
    """Get current weather trading signals."""
    if not settings.WEATHER_ENABLED:
        return []

    try:
        from backend.core.weather_signals import scan_for_weather_signals

        signals = await scan_for_weather_signals()
        return [_weather_signal_to_response(s) for s in signals]
    except Exception:
        return []


def _weather_signal_to_response(s) -> WeatherSignalResponse:
    return WeatherSignalResponse(
        market_id=s.market.market_id,
        city_key=s.market.city_key,
        city_name=s.market.city_name,
        target_date=s.market.target_date.isoformat(),
        threshold_f=s.market.threshold_f,
        metric=s.market.metric,
        direction=s.direction,
        model_probability=s.model_probability,
        market_probability=s.market_probability,
        edge=s.edge,
        confidence=s.confidence,
        suggested_size=s.suggested_size,
        reasoning=s.reasoning,
        ensemble_mean=s.ensemble_mean,
        ensemble_std=s.ensemble_std,
        ensemble_members=s.ensemble_members,
        actionable=s.passes_threshold,
    )


@app.get("/api/weather/metar")
async def get_metar_observations():
    """Get latest real-time airport METAR observations for all cities."""
    from backend.data.metar import fetch_metar_observations
    obs_map = await fetch_metar_observations()
    return {
        station: {
            "station_id": obs.station_id,
            "city_key": obs.city_key,
            "temp_c": obs.temp_c,
            "temp_f": obs.temp_f,
            "dewpoint_f": obs.dewpoint_f,
            "wind_speed_kt": obs.wind_speed_kt,
            "report_time": obs.report_time.isoformat() if obs.report_time else None,
            "age_seconds": round(obs.age_seconds, 1),
            "raw_ob": obs.raw_ob,
        }
        for station, obs in obs_map.items()
    }


@app.get("/api/weather/hourly/signals")
async def get_hourly_signals():
    """Get current hourly temperature signals from METAR nowcasting."""
    from backend.core.hourly_signals import scan_for_hourly_signals
    signals = await scan_for_hourly_signals()
    return [
        {
            "ticker": s.market.ticker,
            "series_ticker": s.market.series_ticker,
            "city_key": s.market.city_key,
            "threshold_f": s.market.threshold_f,
            "direction": s.direction,
            "current_temp_f": s.current_temp_f,
            "expected_temp_f": s.expected_temp_f,
            "minutes_to_close": s.minutes_to_close,
            "model_probability": s.model_probability,
            "market_price": s.market_price,
            "edge": s.edge,
            "actionable": s.passes_threshold,
            "suggested_size": s.suggested_size,
            "reasoning": s.reasoning,
        }
        for s in signals
    ]


@app.get("/api/events", response_model=List[EventResponse])
async def get_events(limit: int = 50):
    from backend.core.scheduler import get_recent_events
    events = get_recent_events(limit)
    return [
        EventResponse(
            timestamp=e["timestamp"],
            type=e["type"],
            message=e["message"],
            data=e.get("data", {})
        )
        for e in events
    ]


# Bot control
@app.post("/api/bot/start")
async def start_bot(db: Session = Depends(get_db)):
    from backend.core.scheduler import start_scheduler, log_event, is_scheduler_running

    state = db.query(BotState).first()
    if state:
        state.is_running = True
        db.commit()

    if not is_scheduler_running():
        start_scheduler()

    log_event("success", "Trading bot started")
    return {"status": "started", "is_running": True}


@app.post("/api/bot/stop")
async def stop_bot(db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event

    state = db.query(BotState).first()
    if state:
        state.is_running = False
        db.commit()

    log_event("info", "Trading bot paused")
    return {"status": "stopped", "is_running": False}


@app.post("/api/bot/reset")
async def reset_bot(db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event

    try:
        trades_deleted = db.query(Trade).delete()
        state = db.query(BotState).first()
        current_bankroll = settings.INITIAL_BANKROLL
        from backend.data.kalshi_client import kalshi_credentials_present, KalshiClient
        if kalshi_credentials_present():
            try:
                c = KalshiClient()
                b = await c.get_balance()
                if b.get("balance_dollars") is not None:
                    current_bankroll = float(b["balance_dollars"])
                elif b.get("balance") is not None:
                    current_bankroll = float(b["balance"]) / 100.0
            except Exception:
                pass

        if state:
            state.bankroll = current_bankroll
            state.total_trades = 0
            state.winning_trades = 0
            state.total_pnl = 0.0
            state.is_running = True

        ai_logs_deleted = db.query(AILog).delete()
        db.commit()

        log_event("success", f"Bot reset: {trades_deleted} trades deleted. Fresh start with ${current_bankroll:,.2f}")

        return {
            "status": "reset",
            "trades_deleted": trades_deleted,
            "ai_logs_deleted": ai_logs_deleted,
            "new_bankroll": current_bankroll
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")


@app.get("/api/dashboard", response_model=DashboardData)
async def get_dashboard(db: Session = Depends(get_db)):
    """Get all dashboard data in one call."""
    stats = await get_stats(db)

    # Fetch BTC price from microstructure first, fallback to CoinGecko
    btc_price_data = None
    micro_data = None
    try:
        micro = await compute_btc_microstructure()
        if micro:
            micro_data = MicrostructureResponse(
                rsi=micro.rsi,
                momentum_1m=micro.momentum_1m,
                momentum_5m=micro.momentum_5m,
                momentum_15m=micro.momentum_15m,
                vwap_deviation=micro.vwap_deviation,
                sma_crossover=micro.sma_crossover,
                volatility=micro.volatility,
                price=micro.price,
                source=micro.source,
            )
            btc_price_data = BtcPriceResponse(
                price=micro.price,
                change_24h=micro.momentum_15m * 96,  # rough extrapolation
                change_7d=0,
                market_cap=0,
                volume_24h=0,
                last_updated=datetime.utcnow(),
            )
    except Exception:
        pass
    if not btc_price_data:
        try:
            btc = await fetch_crypto_price("BTC")
            if btc:
                btc_price_data = BtcPriceResponse(
                    price=btc.current_price,
                    change_24h=btc.change_24h,
                    change_7d=btc.change_7d,
                    market_cap=btc.market_cap,
                    volume_24h=btc.volume_24h,
                    last_updated=btc.last_updated
                )
        except Exception:
            pass

    # Fetch windows
    windows = []
    try:
        markets = await fetch_active_btc_markets()
        windows = [
            BtcWindowResponse(
                slug=m.slug,
                market_id=m.market_id,
                up_price=m.up_price,
                down_price=m.down_price,
                window_start=m.window_start,
                window_end=m.window_end,
                volume=m.volume,
                is_active=m.is_active,
                is_upcoming=m.is_upcoming,
                time_until_end=m.time_until_end,
                spread=m.spread,
            )
            for m in markets
        ]
    except Exception:
        pass

    # Signals — return ALL signals, mark which are actionable
    signals = []
    try:
        raw_signals = await scan_for_signals()
        signals = [_signal_to_response(s, actionable=s.passes_threshold) for s in raw_signals]
    except Exception:
        pass

    # Recent trades
    trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(50).all()
    recent_trades = [
        TradeResponse(
            id=t.id,
            market_ticker=t.market_ticker,
            platform=t.platform,
            event_slug=t.event_slug,
            direction=t.direction,
            entry_price=t.entry_price,
            size=t.size,
            timestamp=t.timestamp,
            settled=t.settled,
            result=t.result,
            pnl=t.pnl,
            is_paper=getattr(t, "is_paper", False),
        )
        for t in trades
    ]

    # Equity curve anchored dynamically to active live bankroll
    starting_bankroll = (stats.bankroll - stats.total_pnl) if stats else settings.INITIAL_BANKROLL
    equity_trades = db.query(Trade).filter(
        Trade.settled == True,
        Trade.is_paper == False
    ).order_by(Trade.timestamp).all()
    equity_curve = []
    cumulative_pnl = 0
    for trade in equity_trades:
        if trade.pnl is not None:
            cumulative_pnl += trade.pnl
            equity_curve.append({
                "timestamp": trade.timestamp.isoformat(),
                "pnl": round(cumulative_pnl, 2),
                "bankroll": round(starting_bankroll + cumulative_pnl, 2)
            })

    # Calibration summary
    calibration = _compute_calibration_summary(db)

    # Weather data (if enabled)
    weather_signals_data = []
    weather_forecasts_data = []
    if settings.WEATHER_ENABLED:
        try:
            from backend.core.weather_signals import scan_for_weather_signals
            from backend.data.weather import fetch_ensemble_forecast, CITY_CONFIG

            wx_signals = await scan_for_weather_signals()
            weather_signals_data = [_weather_signal_to_response(s) for s in wx_signals]

            city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]
            for city_key in city_keys:
                if city_key not in CITY_CONFIG:
                    continue
                forecast = await fetch_ensemble_forecast(city_key)
                if forecast:
                    weather_forecasts_data.append(WeatherForecastResponse(
                        city_key=forecast.city_key,
                        city_name=forecast.city_name,
                        target_date=forecast.target_date.isoformat(),
                        mean_high=forecast.mean_high,
                        std_high=forecast.std_high,
                        mean_low=forecast.mean_low,
                        std_low=forecast.std_low,
                        num_members=forecast.num_members,
                        ensemble_agreement=forecast.ensemble_agreement,
                    ))
        except Exception:
            pass

    return DashboardData(
        stats=stats,
        btc_price=btc_price_data,
        microstructure=micro_data,
        windows=windows,
        active_signals=signals,
        recent_trades=recent_trades,
        equity_curve=equity_curve,
        calibration=calibration,
        weather_signals=weather_signals_data,
        weather_forecasts=weather_forecasts_data,
    )


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await ws_manager.connect(websocket)

    try:
        await websocket.send_json({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "success",
            "message": "Connected to Weather trading bot"
        })

        from backend.core.scheduler import get_recent_events
        for event in get_recent_events(20):
            await websocket.send_json(event)

        last_event_count = len(get_recent_events(200))
        while True:
            await asyncio.sleep(2)

            current_events = get_recent_events(200)
            if len(current_events) > last_event_count:
                new_events = current_events[last_event_count - len(current_events):]
                for event in new_events:
                    await websocket.send_json(event)
                last_event_count = len(current_events)

            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": datetime.utcnow().isoformat()
            })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


@app.get("/api/c137/calibration")
async def get_c137_calibration():
    """Returns C-137 Brier Score and Category Lockout status from delightful-bose."""
    from backend.analytics.calibration import calibration_harness
    btc_brier = calibration_harness.get_category_brier("btc")
    btc_permitted, btc_reason = calibration_harness.is_category_permitted("btc")
    weather_brier = calibration_harness.get_category_brier("weather")
    weather_permitted, weather_reason = calibration_harness.is_category_permitted("weather")
    global_brier = calibration_harness.get_global_brier()

    return {
        "global_brier": round(global_brier, 4) if global_brier else None,
        "categories": {
            "btc": {
                "brier_score": round(btc_brier, 4) if btc_brier else None,
                "permitted": btc_permitted,
                "reason": btc_reason,
                "trades_audited": len(calibration_harness.category_records.get("btc", []))
            },
            "weather": {
                "brier_score": round(weather_brier, 4) if weather_brier else None,
                "permitted": weather_permitted,
                "reason": weather_reason,
                "trades_audited": len(calibration_harness.category_records.get("weather", []))
            }
        },
        "locked_categories": calibration_harness.locked_categories
    }


# SPA fallback route for frontend routing
if os.path.exists(frontend_dist):
    from starlette.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith(("api", "ws", "docs", "openapi.json")):
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        index_html = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_html):
            return FileResponse(index_html)
        raise HTTPException(status_code=404, detail="Not Found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
