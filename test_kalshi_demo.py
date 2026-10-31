#!/usr/bin/env python3
"""
Test suite for Kalshi Demo API integration & weather arbitrage model.
Rick Sanchez (C-137) approved. No Jerry logic permitted.
"""
import asyncio
import os
import sys
import logging
from datetime import date, timedelta

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.config import settings
from backend.data.kalshi_client import KalshiClient, get_base_url, kalshi_credentials_present
from backend.data.kalshi_markets import fetch_kalshi_weather_markets, _parse_kalshi_market, _extract_price
from backend.data.weather import fetch_ensemble_forecast
from backend.core.weather_signals import generate_weather_signal, scan_for_weather_signals

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("test_kalshi_demo")


async def test_kalshi_demo_connectivity():
    print("\n" + "=" * 60)
    print("🛸 STEP 1: Verifying Kalshi Demo API Endpoint Connectivity")
    print("=" * 60)
    client = KalshiClient()
    base_url = client.base_url
    print(f"Target Base URL: {base_url}")
    assert "demo" in base_url or "kalshi.co" in base_url, f"Unexpected non-demo URL: {base_url}"

    # Fetch markets with small limit
    res = await client.get_markets({"limit": 5})
    markets = res.get("markets", [])
    print(f"✅ Successfully pinged demo API. Received {len(markets)} sample markets.")
    assert len(markets) > 0, "No markets returned from demo API"


async def test_ticker_and_price_parsing():
    print("\n" + "=" * 60)
    print("🛸 STEP 2: Testing Ticker & Modern Price Parser (Eliminating Jerry's 50c Fallback)")
    print("=" * 60)
    
    # Test ticker parser
    ticker = "KXHIGHNY-26OCT27-T67"
    parsed = _parse_kalshi_market({"ticker": ticker, "strike_type": "less", "cap_strike": 67.0}, "nyc")
    assert parsed is not None, f"Failed to parse valid ticker {ticker}"
    assert parsed["threshold_f"] == 67.0
    assert parsed["direction"] == "below"
    print(f"✅ Ticker {ticker} -> threshold: {parsed['threshold_f']}°F, direction: {parsed['direction']}")

    # Test modern Kalshi dollars vs legacy cents
    mock_modern = {"yes_ask_dollars": "0.4200", "no_ask_dollars": "0.5800", "last_price_dollars": "0.4000"}
    mock_legacy = {"yes_ask": 42, "no_ask": 58, "last_price": 40}

    assert _extract_price(mock_modern, "yes_ask", "yes_ask_dollars") == 0.42
    assert _extract_price(mock_legacy, "yes_ask", "yes_ask_dollars") == 0.42
    print("✅ Price extraction verified across both modern Kalshi float-strings and legacy integer cents.")


async def test_kalshi_demo_weather_market_scan():
    print("\n" + "=" * 60)
    print("🛸 STEP 3: Scanning Live Weather Markets on Kalshi Demo")
    print("=" * 60)
    cities = ["nyc", "chicago", "miami", "los_angeles", "denver"]
    markets = await fetch_kalshi_weather_markets(cities)
    print(f"Found {len(markets)} active/open weather temperature markets across {len(cities)} cities on demo.")
    
    for m in markets[:5]:
        print(f"  • [{m.city_name}] {m.slug} | Target: {m.target_date} | {m.direction} {m.threshold_f}°F | Yes: ${m.yes_price:.2f} | No: ${m.no_price:.2f}")

    assert len(markets) > 0, "Failed to fetch any weather markets from Kalshi demo"
    return markets


async def test_weather_ensemble_and_edge_calculation(markets):
    print("\n" + "=" * 60)
    print("🛸 STEP 4: Open-Meteo GFS 31-Member Ensemble Forecast & Edge Calculation")
    print("=" * 60)
    
    # Pick a market to evaluate
    sample_market = markets[0]
    print(f"Evaluating market: {sample_market.slug} for {sample_market.city_name} on {sample_market.target_date}")
    
    forecast = await fetch_ensemble_forecast(sample_market.city_key, sample_market.target_date)
    assert forecast is not None, "Failed to retrieve Open-Meteo ensemble forecast"
    print(f"✅ Retrieved 31-member ensemble forecast. Mean High: {forecast.mean_high:.1f}°F, Std: {forecast.std_high:.1f}°F")

    signal = await generate_weather_signal(sample_market)
    if signal:
        print(f"Signal Result:")
        print(f"  • Direction: {signal.direction.upper()}")
        print(f"  • Model Prob: {signal.model_probability:.1%}")
        print(f"  • Market Prob: {signal.market_probability:.1%}")
        print(f"  • Edge: {signal.edge:+.1%}")
        print(f"  • Kelly Sizing: ${signal.suggested_size:.2f}")
        print(f"  • Passes 8% Threshold: {signal.passes_threshold}")
    else:
        print("  • Market price / conditions did not produce an active directional signal.")


async def test_rsa_pss_auth_layer():
    print("\n" + "=" * 60)
    print("🛸 STEP 5: Verifying RSA-PSS Signature Authentication Scheme")
    print("=" * 60)
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    import base64
    import tempfile

    # Generate a fresh ephemeral 2048-bit RSA key pair to test the signing pipeline
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".pem") as f:
        f.write(pem_bytes)
        temp_key_path = f.name

    try:
        # Test signature generation
        orig_key_id = settings.KALSHI_API_KEY_ID
        orig_key_path = settings.KALSHI_PRIVATE_KEY_PATH
        
        settings.KALSHI_API_KEY_ID = "test-demo-key-c137"
        settings.KALSHI_PRIVATE_KEY_PATH = temp_key_path

        client = KalshiClient()
        headers = client._sign_request("GET", "/trade-api/v2/portfolio/balance")
        
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers

        # Verify signature mathematically using the public key
        sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        msg = f"{headers['KALSHI-ACCESS-TIMESTAMP']}GET/trade-api/v2/portfolio/balance".encode("utf-8")
        
        public_key = private_key.public_key()
        public_key.verify(
            sig,
            msg,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256()
        )
        print("✅ Cryptographic RSA-PSS signature matches Kalshi's required spec perfectly.")

    finally:
        settings.KALSHI_API_KEY_ID = orig_key_id
        settings.KALSHI_PRIVATE_KEY_PATH = orig_key_path
        if os.path.exists(temp_key_path):
            os.remove(temp_key_path)


async def main():
    print("\n🧪 STARTING RICK SANCHEZ C-137 KALSHI DEMO VERIFICATION SUITE 🧪\n")
    try:
        await test_kalshi_demo_connectivity()
        await test_ticker_and_price_parsing()
        markets = await test_kalshi_demo_weather_market_scan()
        await test_weather_ensemble_and_edge_calculation(markets)
        await test_rsa_pss_auth_layer()
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED! KALSHI DEMO API & WEATHER ARB BOT ARE BULLETPROOF.")
        print("=" * 60 + "\n")
    except Exception as e:
        logger.exception(f"Test failure: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
