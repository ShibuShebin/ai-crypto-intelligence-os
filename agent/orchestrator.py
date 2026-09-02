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
    "get_derivatives_snapshot": {
        "fn": binance_market.get_derivatives_snapshot,
        "description": "Get open interest, funding rate, and mark price. Call this if spot data shows an unusual move — it reveals whether leverage/futures are driving it.",
    },
    "get_recent_liquidations": {
        "fn": binance_market.get_recent_liquidations,
        "description": "Get recent liquidation activity. Call this if derivatives data suggests a squeeze (high funding rate + volume anomaly).",
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

Rules:
- Always call get_spot_snapshot first if it hasn't been called yet.
- Only call get_derivatives_snapshot if the spot data shows something worth explaining (notable price move and/or volume anomaly).
- Only call get_recent_liquidations if derivatives data suggests leverage is involved (elevated funding rate).
- Conclude as soon as you have enough evidence — don't call tools just to call them. A typical investigation is 2-4 tool calls.
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
