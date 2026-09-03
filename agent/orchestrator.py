"""
The Orchestrator — this is what makes the project an AGENT rather than a
chatbot that reads one API and guesses.

Loop shape (ReAct-style):
    1. Look at the question + evidence gathered so far
    2. Decide: call another tool, or conclude?
    3. If calling a tool: call it, add result to evidence, go to 1
    4. If concluding: hand evidence to the decision engine, produce a report

Each step is logged as a structured dict and yielded immediately, so a
frontend can stream the investigation live instead of waiting for the
final answer. That live trace IS the demo — lean on it.
"""

from __future__ import annotations
import os
import json
from typing import AsyncGenerator, Any
from anthropic import AsyncAnthropic

from agent.tools import binance_market
from agent.decision_engine import synthesize_report

MAX_STEPS = 6

# Tool registry: name -> (async callable, description shown to the LLM)
TOOLS = {
    "get_spot_snapshot": {
        "fn": binance_market.get_spot_snapshot,
        "description": "Get 24h price, price-change %, and volume for a symbol (e.g. BTCUSDT). Always call this first.",
    },
    "get_volume_baseline": {
        "fn": binance_market.get_volume_baseline,
        "description": "Compare current 24h volume against the symbol's own 7-day average. Returns pct_above_baseline and is_anomaly. Call this after spot data if the price move looks notable — it tells you if volume is ACTUALLY unusual, not just guessed from price range.",
    },
    "get_derivatives_snapshot": {
        "fn": binance_market.get_derivatives_snapshot,
        "description": "Get current open interest, funding rate, and mark price. Call this if volume is confirmed anomalous — it reveals whether leverage/futures are driving the move. A high positive funding rate means longs are paying shorts (crowded long trade); a high negative rate means the reverse.",
    },
    "get_oi_history": {
        "fn": binance_market.get_oi_history,
        "description": "Get the recent trend in open interest (building/unwinding/flat over the last several hours). Call this after get_derivatives_snapshot to distinguish 'new leverage piling in' (OI building) from 'a squeeze already unwinding' (OI dropping fast) — the same funding rate can mean very different things depending on this.",
    },
    "get_recent_liquidations": {
        "fn": binance_market.get_recent_liquidations,
        "description": "Get recent liquidation activity. Call this only if OI is unwinding fast AND funding rate is elevated — that combination suggests an active squeeze worth confirming.",
    },
}

SYSTEM_PROMPT = """You are the decision core of an autonomous crypto market investigation agent.

Given a user's question and the evidence gathered so far, decide ONE of:
1. Call another tool to gather more evidence (pick from the tool list, give a one-sentence reason)
2. Conclude the investigation (you have enough evidence for a confident answer)

Respond ONLY with JSON, no other text, no markdown fences:
{
  "thought": "<your one-sentence reasoning>",
  "action": "call_tool" | "conclude",
  "tool_name": "<tool name, only if action is call_tool>",
  "tool_args": {"symbol": "BTCUSDT"}
}

How to reason through an investigation:
- Always call get_spot_snapshot first if it hasn't been called yet.
- If the price move is small (<2%) and nothing looks unusual, conclude early — don't over-investigate a quiet market.
- If the price move is notable, call get_volume_baseline to check whether volume is ACTUALLY anomalous (is_anomaly: true), not just assumed from price alone.
- Only escalate to get_derivatives_snapshot if get_volume_baseline confirmed an anomaly. Volume without confirmation isn't worth chasing into derivatives data.
- If derivatives data shows an elevated |funding_rate| (roughly >0.0005 in either direction), call get_oi_history to see whether positions are building or unwinding — this is what separates "leverage building up, could reverse later" from "squeeze happening right now."
- Only call get_recent_liquidations if OI is unwinding fast alongside elevated funding — that's the specific signature of an active squeeze.
- Conclude as soon as you have enough evidence. A typical investigation is 2-4 tool calls; don't call tools just to call them.
"""


async def investigate(question: str, symbol: str = "BTCUSDT") -> AsyncGenerator[dict[str, Any], None]:
    """
    Runs the investigation loop, yielding one step dict at a time.
    Final yielded item has type "report" and contains the synthesized conclusion.
    """
    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    evidence: list[dict[str, Any]] = []
    called_tools: list[str] = []

    for step_num in range(1, MAX_STEPS + 1):
        tool_list_str = "\n".join(
            f"- {name}: {meta['description']}" for name, meta in TOOLS.items()
        )
        evidence_str = json.dumps(evidence, indent=2) if evidence else "(none yet)"

        user_msg = (
            f"User question: {question}\n"
            f"Symbol: {symbol}\n\n"
            f"Available tools:\n{tool_list_str}\n\n"
            f"Evidence gathered so far:\n{evidence_str}\n\n"
            f"Tools already called: {called_tools}\n\n"
            "What's your next move?"
        )

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            decision = json.loads(raw)
        except json.JSONDecodeError:
            # Fail safe: if the model didn't return clean JSON, conclude with what we have
            decision = {"thought": "Could not parse decision, concluding with available evidence.", "action": "conclude"}

        if decision["action"] == "call_tool":
            tool_name = decision["tool_name"]
            tool_args = decision.get("tool_args", {"symbol": symbol})
            tool_meta = TOOLS.get(tool_name)

            if tool_meta is None:
                yield {"step": step_num, "type": "error", "message": f"Unknown tool: {tool_name}"}
                continue

            yield {
                "step": step_num,
                "type": "thought",
                "thought": decision["thought"],
                "tool_called": tool_name,
            }

            result = await tool_meta["fn"](**tool_args)
            called_tools.append(tool_name)
            evidence.append({"tool": tool_name, "result": result})

            yield {
                "step": step_num,
                "type": "observation",
                "tool": tool_name,
                "result": result,
            }

        else:  # conclude
            yield {
                "step": step_num,
                "type": "thought",
                "thought": decision.get("thought", "Concluding investigation."),
            }
            report = await synthesize_report(question, symbol, evidence, client)
            yield {"step": step_num + 1, "type": "report", "report": report}
            return

    # Hit MAX_STEPS without concluding — force a conclusion with whatever we have
    report = await synthesize_report(question, symbol, evidence, client)
    yield {"step": MAX_STEPS + 1, "type": "report", "report": report}
