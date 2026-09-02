"""
Tests the orchestrator's loop mechanics without hitting real Binance or
Anthropic APIs — mocks both so we can verify the control flow (tool
selection, evidence accumulation, eventual conclusion) works correctly.

Run with: pytest tests/test_orchestrator.py -v
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.orchestrator import investigate, TOOLS


class FakeAnthropicResponse:
    """Mimics the shape of an Anthropic Messages API response."""
    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


@pytest.mark.asyncio
async def test_investigation_calls_spot_then_concludes():
    """Agent should call get_spot_snapshot, then conclude if nothing anomalous is found."""

    decisions = [
        json.dumps({
            "thought": "Need baseline price/volume data first.",
            "action": "call_tool",
            "tool_name": "get_spot_snapshot",
            "tool_args": {"symbol": "BTCUSDT"},
        }),
        json.dumps({
            "thought": "Price move is unremarkable, no need for derivatives data.",
            "action": "conclude",
        }),
    ]
    report_json = json.dumps({
        "verdict": "neutral",
        "confidence": 60,
        "summary": "BTC is trading in a normal range with no unusual signals.",
        "evidence_points": ["24h change +0.4%", "Volume in line with recent average"],
        "risk_note": "Low-signal environment; conclusion may not hold if volatility spikes.",
    })

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[FakeAnthropicResponse(d) for d in decisions] + [FakeAnthropicResponse(report_json)]
    )

    fake_spot = {
        "symbol": "BTCUSDT", "last_price": 65000.0, "price_change_pct_24h": 0.4,
        "volume_base_24h": 12000.0, "volume_quote_24h": 780000000.0,
        "high_24h": 65500.0, "low_24h": 64200.0,
    }

    with patch("agent.orchestrator.AsyncAnthropic", return_value=mock_client), \
         patch.dict(TOOLS["get_spot_snapshot"], {"fn": AsyncMock(return_value=fake_spot)}):

        steps = [s async for s in investigate("Why is BTC moving?", "BTCUSDT")]

    tool_calls = [s for s in steps if s["type"] == "observation"]
    report_steps = [s for s in steps if s["type"] == "report"]

    assert len(tool_calls) == 1
    assert tool_calls[0]["tool"] == "get_spot_snapshot"
    assert len(report_steps) == 1
    assert report_steps[0]["report"]["verdict"] == "neutral"


@pytest.mark.asyncio
async def test_investigation_escalates_to_derivatives_on_anomaly():
    """Agent should chain spot -> derivatives when spot data looks unusual."""

    decisions = [
        json.dumps({
            "thought": "Baseline check.", "action": "call_tool",
            "tool_name": "get_spot_snapshot", "tool_args": {"symbol": "BTCUSDT"},
        }),
        json.dumps({
            "thought": "Volume and price move look abnormal, checking derivatives.",
            "action": "call_tool", "tool_name": "get_derivatives_snapshot",
            "tool_args": {"symbol": "BTCUSDT"},
        }),
        json.dumps({"thought": "Funding rate confirms leverage-driven move.", "action": "conclude"}),
    ]
    report_json = json.dumps({
        "verdict": "bullish", "confidence": 78,
        "summary": "Elevated funding rate and volume spike suggest a short squeeze in progress.",
        "evidence_points": ["Price +6.2% in 24h", "Funding rate elevated at 0.08%"],
        "risk_note": "Squeezes can reverse sharply once leveraged positions are flushed out.",
    })

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[FakeAnthropicResponse(d) for d in decisions] + [FakeAnthropicResponse(report_json)]
    )

    fake_spot = {
        "symbol": "BTCUSDT", "last_price": 68000.0, "price_change_pct_24h": 6.2,
        "volume_base_24h": 45000.0, "volume_quote_24h": 3000000000.0,
        "high_24h": 68200.0, "low_24h": 63500.0,
    }
    fake_deriv = {"symbol": "BTCUSDT", "open_interest": 55000.0, "funding_rate": 0.0008, "mark_price": 68010.0}

    with patch("agent.orchestrator.AsyncAnthropic", return_value=mock_client), \
         patch.dict(TOOLS["get_spot_snapshot"], {"fn": AsyncMock(return_value=fake_spot)}), \
         patch.dict(TOOLS["get_derivatives_snapshot"], {"fn": AsyncMock(return_value=fake_deriv)}):

        steps = [s async for s in investigate("Why is BTC pumping?", "BTCUSDT")]

    tools_called = [s["tool"] for s in steps if s["type"] == "observation"]
    assert tools_called == ["get_spot_snapshot", "get_derivatives_snapshot"]

    report = [s for s in steps if s["type"] == "report"][0]["report"]
    assert report["verdict"] == "bullish"
    assert report["confidence"] > 50
