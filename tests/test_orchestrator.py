"""
Tests the orchestrator's loop mechanics without hitting real Binance or any
LLM provider — mocks agent.llm_client.call_llm directly so these tests don't
care which provider (Groq, Anthropic, etc.) is actually configured.

Run with: pytest tests/test_orchestrator.py -v
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from agent.orchestrator import investigate, TOOLS


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

    mock_call_llm = AsyncMock(side_effect=decisions + [report_json])

    fake_spot = {
        "symbol": "BTCUSDT", "last_price": 65000.0, "price_change_pct_24h": 0.4,
        "volume_base_24h": 12000.0, "volume_quote_24h": 780000000.0,
        "high_24h": 65500.0, "low_24h": 64200.0,
    }

    with patch("agent.orchestrator.call_llm", mock_call_llm), \
         patch("agent.decision_engine.call_llm", mock_call_llm), \
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

    mock_call_llm = AsyncMock(side_effect=decisions + [report_json])

    fake_spot = {
        "symbol": "BTCUSDT", "last_price": 68000.0, "price_change_pct_24h": 6.2,
        "volume_base_24h": 45000.0, "volume_quote_24h": 3000000000.0,
        "high_24h": 68200.0, "low_24h": 63500.0,
    }
    fake_deriv = {"symbol": "BTCUSDT", "open_interest": 55000.0, "funding_rate": 0.0008, "mark_price": 68010.0}

    with patch("agent.orchestrator.call_llm", mock_call_llm), \
         patch("agent.decision_engine.call_llm", mock_call_llm), \
         patch.dict(TOOLS["get_spot_snapshot"], {"fn": AsyncMock(return_value=fake_spot)}), \
         patch.dict(TOOLS["get_derivatives_snapshot"], {"fn": AsyncMock(return_value=fake_deriv)}):

        steps = [s async for s in investigate("Why is BTC pumping?", "BTCUSDT")]

    tools_called = [s["tool"] for s in steps if s["type"] == "observation"]
    assert tools_called == ["get_spot_snapshot", "get_derivatives_snapshot"]

    report = [s for s in steps if s["type"] == "report"][0]["report"]
    assert report["verdict"] == "bullish"
    assert report["confidence"] > 50


@pytest.mark.asyncio
async def test_investigation_uses_news_sentiment_tool():
    """Agent should be able to reach for get_news_sentiment when it's the LLM's chosen next step."""

    decisions = [
        json.dumps({
            "thought": "Check baseline first.", "action": "call_tool",
            "tool_name": "get_spot_snapshot", "tool_args": {"symbol": "BTCUSDT"},
        }),
        json.dumps({
            "thought": "Notable move — checking if news explains it.",
            "action": "call_tool", "tool_name": "get_news_sentiment",
            "tool_args": {"symbol": "BTCUSDT"},
        }),
        json.dumps({"thought": "News confirms bullish sentiment.", "action": "conclude"}),
    ]
    report_json = json.dumps({
        "verdict": "bullish", "confidence": 70,
        "summary": "Price move is backed by bullish news sentiment.",
        "evidence_points": ["Positive headlines about institutional adoption"],
        "risk_note": "Sentiment can shift quickly; not a guarantee of continued direction.",
    })

    mock_call_llm = AsyncMock(side_effect=decisions + [report_json])

    fake_spot = {
        "symbol": "BTCUSDT", "last_price": 70000.0, "price_change_pct_24h": 4.1,
        "volume_base_24h": 30000.0, "volume_quote_24h": 2100000000.0,
        "high_24h": 70200.0, "low_24h": 66500.0,
    }
    fake_sentiment = {
        "symbol": "BTCUSDT", "sentiment": "bullish",
        "summary": "Headlines point to institutional adoption news.",
        "relevant_headline_count": 4, "headlines_sample": ["Big bank adds BTC exposure"],
    }

    with patch("agent.orchestrator.call_llm", mock_call_llm), \
         patch("agent.decision_engine.call_llm", mock_call_llm), \
         patch.dict(TOOLS["get_spot_snapshot"], {"fn": AsyncMock(return_value=fake_spot)}), \
         patch.dict(TOOLS["get_news_sentiment"], {"fn": AsyncMock(return_value=fake_sentiment)}):

        steps = [s async for s in investigate("Why is BTC pumping?", "BTCUSDT")]

    tools_called = [s["tool"] for s in steps if s["type"] == "observation"]
    assert tools_called == ["get_spot_snapshot", "get_news_sentiment"]

    report = [s for s in steps if s["type"] == "report"][0]["report"]
    assert report["verdict"] == "bullish"
