"""Kalshi API client with RSA-PSS signature authentication."""
import base64
import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from backend.config import settings

logger = logging.getLogger("trading_bot")

DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"
PROD_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def get_base_url() -> str:
    """Resolve Kalshi base URL based on config."""
    if settings.KALSHI_BASE_URL:
        return settings.KALSHI_BASE_URL.rstrip("/")
    if settings.KALSHI_USE_DEMO:
        return DEMO_BASE_URL
    return PROD_BASE_URL


class KalshiClient:
    """Async Kalshi API client using RSA-PSS signature auth with public fallback."""

    def __init__(self):
        self._private_key = None

    @property
    def base_url(self) -> str:
        return get_base_url()

    def _load_private_key(self):
        """Load RSA private key from file (lazy, cached)."""
        if self._private_key is not None:
            return self._private_key

        key_path = settings.KALSHI_PRIVATE_KEY_PATH
        if not key_path:
            raise ValueError("KALSHI_PRIVATE_KEY_PATH not configured")

        pem_data = Path(key_path).expanduser().read_bytes()
        self._private_key = serialization.load_pem_private_key(pem_data, password=None)
        return self._private_key

    def _sign_request(self, method: str, path: str) -> Dict[str, str]:
        """
        Generate auth headers for a Kalshi API request.
        Supports both Ed25519 (modern) and RSA-PSS (legacy) key formats.

        Signature = sign(timestamp_ms + METHOD + path)
        where path = /trade-api/v2/... (no query params).
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

        clean_path = path.split("?")[0]
        timestamp_ms = str(int(time.time() * 1000))
        message = f"{timestamp_ms}{method.upper()}{clean_path}".encode("utf-8")

        private_key = self._load_private_key()
        if isinstance(private_key, Ed25519PrivateKey):
            signature = private_key.sign(message)
        elif isinstance(private_key, RSAPrivateKey):
            signature = private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH,
                ),
                hashes.SHA256(),
            )
        else:
            # Fallback
            signature = private_key.sign(message)

        return {
            "KALSHI-ACCESS-KEY": settings.KALSHI_API_KEY_ID or "",
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> dict:
        """
        GET request to Kalshi API (signed if credentials present, unsigned otherwise).

        Args:
            path: API path after /trade-api/v2 (e.g., "/markets")
            params: Query parameters (not included in signature)
        """
        full_path = f"/trade-api/v2{path}"
        url = f"{self.base_url}{path}"
        
        if kalshi_credentials_present():
            headers = self._sign_request("GET", full_path)
        else:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_markets(self, params: Optional[Dict[str, Any]] = None) -> dict:
        """Fetch markets with optional filters."""
        return await self.get("/markets", params=params)

    async def get_market(self, ticker: str) -> dict:
        """Fetch a single market by ticker."""
        return await self.get(f"/markets/{ticker}")

    async def post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> dict:
        """
        Authenticated POST request to Kalshi API.

        Args:
            path: API path after /trade-api/v2 (e.g., "/portfolio/orders")
            payload: JSON request body
        """
        full_path = f"/trade-api/v2{path}"
        url = f"{self.base_url}{path}"
        headers = self._sign_request("POST", full_path)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload or {})
            if response.status_code >= 400:
                logger.error(f"Kalshi POST error {response.status_code}: {response.text}")
                raise ValueError(f"Kalshi request failed ({response.status_code}): {response.text}")
            return response.json()

    async def create_order(
        self,
        ticker: str,
        contract_type: str,  # "yes" or "no"
        count: int,
        price_dollars: float,  # e.g. 0.05
        time_in_force: str = "immediate_or_cancel",
    ) -> dict:
        """
        Submit a real order to Kalshi V2 events order endpoint (Demo or Prod).
        Adheres to CreateOrderV2Request single-book YES-leg specification:
          - Buying YES at P -> side="bid", price=f"{P:.4f}"
          - Buying NO at P  -> side="ask", price=f"{round(1.0 - P, 4):.4f}"
        """
        import uuid

        is_yes = contract_type.lower() in ("yes", "up")
        p_clean = max(0.01, min(0.99, float(price_dollars)))
        count_int = max(1, int(count))

        if is_yes:
            side = "bid"
            price_str = f"{p_clean:.4f}"
        else:
            side = "ask"
            price_str = f"{round(1.0 - p_clean, 4):.4f}"

        payload: Dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "count": str(count_int),
            "price": price_str,
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": str(uuid.uuid4()),
        }

        return await self.post("/portfolio/events/orders", payload)

    async def get_orders(self, params: Optional[Dict[str, Any]] = None) -> dict:
        """Fetch portfolio orders."""
        return await self.get("/portfolio/orders", params=params)

    async def get_balance(self) -> dict:
        """Get portfolio balance (requires authentication)."""
        if not kalshi_credentials_present():
            raise ValueError("Kalshi credentials (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH) required to check balance")
        return await self.get("/portfolio/balance")


def kalshi_credentials_present() -> bool:
    """Check if Kalshi API credentials are configured."""
    return bool(settings.KALSHI_API_KEY_ID and settings.KALSHI_PRIVATE_KEY_PATH)
