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


async def get_volume_baseline(symbol: str = "BTCUSDT", lookback_days: int = 8) -> dict[str, Any]:
    """
    Fetches daily candles and computes a REAL historical volume baseline,
    then compares today's rolling 24h volume against it. This replaces the
    old crude "big price move + narrow range = anomaly" guess with an
    actual number: how many % above/below its own 7-day average is volume
    right now?

    lookback_days=8 because we fetch 8 days and drop the most recent
    (still-forming) candle, leaving 7 complete days for the baseline.
    """
    url = f"{BASE_URL}/api/v3/klines"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            url, params={"symbol": symbol, "interval": "1d", "limit": lookback_days}
        )
        resp.raise_for_status()
        klines = resp.json()

    # Kline format: [open_time, open, high, low, close, volume, close_time, quote_volume, ...]
    # Drop the last (current, still-forming) day — we only want completed days for the baseline.
    completed = klines[:-1] if len(klines) > 1 else klines
    daily_volumes = [float(k[7]) for k in completed]  # quote asset volume per day

    spot = await get_spot_snapshot(symbol)
    return compute_volume_anomaly(spot["volume_quote_24h"], daily_volumes)


def compute_volume_anomaly(
    current_24h_quote_volume: float, historical_daily_volumes: list[float]
) -> dict[str, Any]:
    """
    Pure function (no network) so it's independently unit-testable.
    Returns the baseline average, current volume, % deviation, and a bool flag.
    """
    if not historical_daily_volumes:
        return {
            "current_volume": current_24h_quote_volume,
            "baseline_avg_volume": None,
            "pct_above_baseline": None,
            "is_anomaly": False,
            "note": "insufficient history to compute baseline",
        }

    baseline_avg = sum(historical_daily_volumes) / len(historical_daily_volumes)
    pct_above = (
        ((current_24h_quote_volume - baseline_avg) / baseline_avg) * 100
        if baseline_avg > 0
        else 0
    )

    return {
        "current_volume": round(current_24h_quote_volume, 2),
        "baseline_avg_volume": round(baseline_avg, 2),
        "pct_above_baseline": round(pct_above, 1),
        "is_anomaly": pct_above > 40.0,  # >40% above 7-day average counts as unusual
    }


async def get_oi_history(symbol: str = "BTCUSDT", period: str = "1h", limit: int = 12) -> dict[str, Any]:
    """
    Historical open interest — lets the agent see whether OI is BUILDING
    (new leveraged positions opening, fuel for a future squeeze) or
    UNWINDING (positions closing/getting liquidated, a squeeze in progress).
    A single current OI reading can't tell you which; the trend can.
    """
    url = f"{FUTURES_URL}/futures/data/openInterestHist"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            url, params={"symbol": symbol, "period": period, "limit": limit}
        )
        resp.raise_for_status()
        history = resp.json()

    oi_values = [float(h["sumOpenInterest"]) for h in history]
    return compute_oi_trend(oi_values)


def compute_oi_trend(oi_values: list[float]) -> dict[str, Any]:
    """
    Pure function, independently testable. Compares first vs last reading
    in the window to classify the OI trend.
    """
    if len(oi_values) < 2:
        return {"pct_change": None, "direction": "unknown", "note": "insufficient data points"}

    first, last = oi_values[0], oi_values[-1]
    pct_change = ((last - first) / first) * 100 if first > 0 else 0

    if pct_change > 5.0:
        direction = "building"       # new leveraged positions opening
    elif pct_change < -5.0:
        direction = "unwinding"      # positions closing / being liquidated
    else:
        direction = "flat"

    return {
        "pct_change": round(pct_change, 1),
        "direction": direction,
        "window_size": len(oi_values),
    }


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
