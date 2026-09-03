"""
Decision Engine — turns raw evidence (list of tool results) into a final,
structured investigation report: verdict, confidence, evidence summary, risk.

Kept separate from orchestrator.py so the "how do we decide" logic can be
tested/tuned independently of "how do we gather evidence."
"""

from __future__ import annotations
import json
from typing import Any

REPORT_SYSTEM_PROMPT = """You are the synthesis stage of a crypto market investigation agent.
You've been given a user's question and a list of evidence gathered by tool calls
(spot market data, volume-vs-baseline comparison, derivatives data, open-interest
trend, liquidation data). Produce a final investigation report.

Respond ONLY with JSON, no markdown fences:
{
  "verdict": "bullish" | "bearish" | "neutral" | "inconclusive",
  "confidence": <integer 0-100>,
  "summary": "<2-3 sentence plain-English explanation of what's happening>",
  "evidence_points": ["<short evidence bullet>", "..."],
  "risk_note": "<1 sentence on what could invalidate this read, or key risk to be aware of>"
}

How to weigh the evidence:
- A price move alone, with volume NOT flagged as anomalous, is weak evidence — keep confidence low or return "neutral"/"inconclusive".
- Volume confirmed anomalous + no derivatives data gathered = spot-driven move (real buying/selling), not leverage-driven. State that distinction explicitly.
- Elevated funding rate + OI "building" = a crowded leveraged position accumulating — this is a setup that COULD reverse later, not a confirmed move happening now. Say so, don't overstate confidence.
- Elevated funding rate + OI "unwinding" = an active squeeze — positions are being forced closed right now. This deserves higher confidence than the "building" case.
- Be honest about uncertainty. If evidence is thin, partial, or conflicting, say so and lower confidence and/or return "inconclusive" rather than forcing a bullish/bearish call.
- Never state a specific number (price, %, funding rate) that isn't actually present in the evidence provided.
"""


async def synthesize_report(
    question: str, symbol: str, evidence: list[dict[str, Any]], client
) -> dict[str, Any]:
    evidence_str = json.dumps(evidence, indent=2) if evidence else "(no evidence gathered)"

    user_msg = (
        f"User question: {question}\n"
        f"Symbol: {symbol}\n\n"
        f"Evidence gathered:\n{evidence_str}\n\n"
        "Produce the final investigation report now."
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=REPORT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "verdict": "inconclusive",
            "confidence": 0,
            "summary": "The agent could not synthesize a clean report from the evidence gathered.",
            "evidence_points": [json.dumps(e) for e in evidence],
            "risk_note": "Report generation failed to parse — check raw model output.",
        }
