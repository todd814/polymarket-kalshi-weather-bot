"""Configuration settings for the BTC 5-min trading bot."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database (SQLite for Phase 1, PostgreSQL for production)
    DATABASE_URL: str = "sqlite:///./tradingbot.db"
    PAPER_DATABASE_URL: str = "sqlite:///./paper_training.db"

    # API Keys (optional)
    POLYMARKET_API_KEY: Optional[str] = None

    # Kalshi API
    KALSHI_API_KEY_ID: Optional[str] = None
    KALSHI_PRIVATE_KEY_PATH: Optional[str] = None
    KALSHI_ENABLED: bool = True
    KALSHI_USE_DEMO: bool = True
    KALSHI_BASE_URL: Optional[str] = None
    KALSHI_SYNC_BALANCE: bool = True
    KALSHI_EXECUTE_ORDERS: bool = False

    # AI API Keys
    GROQ_API_KEY: Optional[str] = None

    # AI Model Configuration
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # AI Feature Flags
    AI_LOG_ALL_CALLS: bool = True
    AI_DAILY_BUDGET_USD: float = 1.0

    # Bot settings - BTC 5-MIN TRADING
    BTC_ENABLED: bool = False  # Permanently disabled - 5m BTC has negative edge and noisy flow
    SIMULATION_MODE: bool = True
    INITIAL_BANKROLL: float = 99.53
    KELLY_FRACTION: float = 0.15  # Fractional Kelly

    # BTC 5-min specific settings
    SCAN_INTERVAL_SECONDS: int = 60  # Scan every minute
    SETTLEMENT_INTERVAL_SECONDS: int = 120  # Check settlements every 2 min
    BTC_PRICE_SOURCE: str = "coinbase"
    MIN_EDGE_THRESHOLD: float = 0.06  # Require solid edge
    MAX_ENTRY_PRICE: float = 0.55  # Enter up to 55c
    MAX_TRADES_PER_WINDOW: int = 1
    MAX_TOTAL_PENDING_TRADES: int = 10

    # Risk management (scaled to ~$100 bankroll)
    DAILY_LOSS_LIMIT: float = 15.0
    MAX_TRADE_SIZE: float = 5.0
    MIN_TIME_REMAINING: int = 60  # Don't trade windows closing in < 60s
    MAX_TIME_REMAINING: int = 1800  # Trade windows up to 30min out

    # Indicator weights for composite signal (must sum to ~1.0)
    WEIGHT_RSI: float = 0.20
    WEIGHT_MOMENTUM: float = 0.35
    WEIGHT_VWAP: float = 0.20
    WEIGHT_SMA: float = 0.15
    WEIGHT_MARKET_SKEW: float = 0.10

    # Volume filter
    MIN_MARKET_VOLUME: float = 100.0  # Low volume for 5-min markets

    # Weather trading settings
    WEATHER_ENABLED: bool = True
    WEATHER_SCAN_INTERVAL_SECONDS: int = 300  # 5 min
    WEATHER_SETTLEMENT_INTERVAL_SECONDS: int = 1800  # 30 min
    WEATHER_MIN_EDGE_THRESHOLD: float = 0.08  # 8% — weather has more signal than 5-min BTC
    WEATHER_FUTURE_MIN_EDGE_THRESHOLD: float = 0.12  # 12% — stricter hurdle for T+1 (Tomorrow) pre-allocation
    WEATHER_PAPER_MIN_EDGE_THRESHOLD: float = 0.03  # 3% — shadow paper trading hurdle for volume data collection
    WEATHER_MIN_ENTRY_PRICE: float = 0.20  # 20c minimum floor (<20c had 0W/13L in live)
    WEATHER_BRACKET_YES_MIN_PRICE: float = 0.20  # 20c minimum floor for Bracket (-B) YES contracts
    WEATHER_MAX_ENTRY_PRICE: float = 0.68  # 68c ceiling (data science audit: >68c had negative expectancy)
    WEATHER_MAX_DIVERGENCE: float = 0.35  # 35% max divergence vs liquid order book before phantom edge guard triggers
    WEATHER_MAX_POSITIONS_PER_CITY_DATE: int = 1  # Max 1 live position per city per date to prevent synoptic correlation collapse
    WEATHER_MAX_TRADE_SIZE: float = 5.0
    WEATHER_CITIES: str = "nyc,chicago,miami,los_angeles,denver,austin,houston,washington_dc,boston,philadelphia"
    WEATHER_MARKET_SHRINKAGE_WEIGHT: float = 0.30  # 30% Bayesian shrinkage toward market prior; 70% bias-corrected model
    WEATHER_ALLOW_THRESHOLD_LIVE: bool = False  # Block non-ratchet -T threshold trades for live execution (paper still tracks)
    WEATHER_FUTURE_MIN_UTC_HOUR: int = 18  # Delay live T+1 entries until 18:00 UTC (1 PM EST) after 12Z NBM/ECMWF/GFS cycles publish
    WEATHER_ENSEMBLE_STD_INFLATION: float = 1.35  # Correct empirical ensemble underdispersion
    WEATHER_ENSEMBLE_MIN_STD_T0: float = 1.3  # Minimum calibrated std (deg F) for T+0
    WEATHER_ENSEMBLE_MIN_STD_T1: float = 2.0  # Minimum calibrated std (deg F) for T+1+
    WEATHER_CALIBRATION_ROLLING_WINDOW: int = 30  # Rolling trade window for Brier kill-switch

    # Hourly weather trading settings (100% paper-only)
    HOURLY_WEATHER_ENABLED: bool = True
    HOURLY_SCAN_INTERVAL_SECONDS: int = 120  # Scan every 2 minutes
    HOURLY_SETTLEMENT_INTERVAL_SECONDS: int = 300  # Check settlements every 5 minutes
    HOURLY_MIN_EDGE_THRESHOLD: float = 0.08  # Stricter 8% edge hurdle
    HOURLY_MAX_TRADE_SIZE: float = 5.0
    HOURLY_MAX_DIVERGENCE: float = 0.35  # Phantom edge guard: max 35% divergence vs liquid book
    HOURLY_MIN_MINUTES_TO_CLOSE: float = 3.0  # Min minutes remaining
    HOURLY_MAX_MINUTES_TO_CLOSE: float = 35.0  # Max 35 minutes remaining (avoid stale 50-minute METAR lag)
    HOURLY_SIGMA_FLOOR: float = 1.8  # Minimum standard deviation in deg F (realistic urban turbulence)
    HOURLY_BLACKLISTED_CITIES: str = "los_angeles,miami"  # Exclude non-linear marine layer coastal chaos

    class Config:
        env_file = ".env"


settings = Settings()
