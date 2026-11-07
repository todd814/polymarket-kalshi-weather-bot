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
    KALSHI_EXECUTE_DEMO_ORDERS: bool = True

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
    WEATHER_PAPER_MIN_EDGE_THRESHOLD: float = 0.03  # 3% — shadow paper trading hurdle for volume data collection
    WEATHER_MIN_ENTRY_PRICE: float = 0.06  # 6c minimum floor for Threshold (-T) contracts
    WEATHER_BRACKET_YES_MIN_PRICE: float = 0.12  # 12c minimum floor for Bracket (-B) YES contracts
    WEATHER_MAX_ENTRY_PRICE: float = 0.68  # 68c ceiling (data science audit: >68c had negative expectancy)
    WEATHER_MAX_TRADE_SIZE: float = 5.0
    WEATHER_CITIES: str = "nyc,chicago,miami,los_angeles,denver,austin,houston,washington_dc,boston,philadelphia"

    # Hourly weather trading settings (100% paper-only)
    HOURLY_WEATHER_ENABLED: bool = True
    HOURLY_SCAN_INTERVAL_SECONDS: int = 120  # Scan every 2 minutes
    HOURLY_SETTLEMENT_INTERVAL_SECONDS: int = 300  # Check settlements every 5 minutes
    HOURLY_MIN_EDGE_THRESHOLD: float = 0.05  # 5% edge hurdle
    HOURLY_MAX_TRADE_SIZE: float = 5.0

    class Config:
        env_file = ".env"


settings = Settings()
