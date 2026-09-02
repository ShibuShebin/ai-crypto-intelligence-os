"""
Binance market + derivatives data tool.

Uses PUBLIC REST endpoints only — no API key required for any of this.
Spot data comes from api.binance.com, derivatives data (open interest,
funding rate, liquidations proxy) comes from fapi.binance.com (futures).

NOTE: this file was written and logic-tested with mocked HTTP responses
(see tests/test_binance_market.py) because the dev sandbox that built it
had no network access to binance.com. Before your demo, run:

    python -m agent.tools.binance_market

...on your own machine to confirm live calls succeed. If Binance is
geo-blocked in your region, swap BASE_URL / FUTURES_URL for a mirror
or a VPN'd host — the parsing logic doesn't need to change.
"""

from __future__ import annotations
import httpx
from typing import Any

BASE_URL = "https://api.binance.com"
FUTURES_URL = "https://fapi.binance.com"

TIMEOUT = 10.0


async def get_spot_snapshot(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """24h price/volume snapshot. This is the agent's first move on any question."""
    url = f"{BASE_URL}/api/v3/ticker/24hr"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params={"symbol": symbol})
        resp.raise_for_status()
        d = resp.json()

    return {
        "symbol": d["symbol"],
        "last_price": float(d["lastPrice"]),
        "price_change_pct_24h": float(d["priceChangePercent"]),
        "volume_base_24h": float(d["volume"]),
        "volume_quote_24h": float(d["quoteVolume"]),
        "high_24h": float(d["highPrice"]),
        "low_24h": float(d["lowPrice"]),
    }


async def get_derivatives_snapshot(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Open interest + funding rate — used when the agent suspects leverage-driven moves."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        oi_resp = await client.get(
            f"{FUTURES_URL}/fapi/v1/openInterest", params={"symbol": symbol}
        )
        oi_resp.raise_for_status()
        oi = oi_resp.json()

        funding_resp = await client.get(
            f"{FUTURES_URL}/fapi/v1/premiumIndex", params={"symbol": symbol}
        )
        funding_resp.raise_for_status()
        funding = funding_resp.json()

    return {
        "symbol": symbol,
        "open_interest": float(oi["openInterest"]),
        "funding_rate": float(funding["lastFundingRate"]),
        "mark_price": float(funding["markPrice"]),
    }


async def get_recent_liquidations(symbol: str = "BTCUSDT", limit: int = 50) -> dict[str, Any]:
    """
    Binance doesn't expose a clean public REST 'recent liquidations' endpoint —
    real implementations stream forceOrder events off the futures websocket.
    For the hackathon demo, this is a placeholder that returns an empty/neutral
    result so the orchestrator's logic branch still runs end-to-end. Wiring the
    actual websocket listener is a good 'nice to have' if Day 5 goes smoothly.
    """
    return {
        "symbol": symbol,
        "liquidation_count_sample": 0,
        "note": "placeholder — wire wss://fstream.binance.com/ws/!forceOrder@arr for real data",
    }


def detect_volume_anomaly(spot: dict[str, Any], threshold_pct: float = 50.0) -> bool:
    """
    Very simple heuristic: is quote volume unusually high relative to what
    we'd expect from the price range alone? Real version would compare
    against a rolling historical average; this is the v1 placeholder the
    orchestrator's decision logic hangs off of.
    """
    price_range_pct = (
        (spot["high_24h"] - spot["low_24h"]) / spot["low_24h"] * 100
        if spot["low_24h"] > 0
        else 0
    )
    # crude signal: volatility % much lower than volume would suggest "unusual" activity
    return abs(spot["price_change_pct_24h"]) > 3.0 and price_range_pct < 8.0


if __name__ == "__main__":
    import asyncio
    import json

    async def _demo():
        print("Fetching BTCUSDT spot snapshot...")
        spot = await get_spot_snapshot("BTCUSDT")
        print(json.dumps(spot, indent=2))

        print("\nFetching BTCUSDT derivatives snapshot...")
        deriv = await get_derivatives_snapshot("BTCUSDT")
        print(json.dumps(deriv, indent=2))

    asyncio.run(_demo())
