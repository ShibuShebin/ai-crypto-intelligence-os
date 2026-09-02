"""
CLI entrypoint — run an investigation and watch the agent's reasoning trace live.

Usage:
    python run.py "Why is BTC moving up?"
    python run.py "Is ETH showing signs of a short squeeze?" --symbol ETHUSDT
"""

import asyncio
import argparse
import json
from dotenv import load_dotenv

load_dotenv()

from agent.orchestrator import investigate


async def main(question: str, symbol: str):
    print(f"\n🔍 Investigating: \"{question}\" ({symbol})\n")
    print("-" * 60)

    async for step in investigate(question, symbol):
        if step["type"] == "thought":
            tool = step.get("tool_called")
            suffix = f" → calling {tool}" if tool else ""
            print(f"[step {step['step']}] 💭 {step['thought']}{suffix}")

        elif step["type"] == "observation":
            print(f"[step {step['step']}] 📊 {step['tool']} result:")
            print(json.dumps(step["result"], indent=2))

        elif step["type"] == "error":
            print(f"[step {step['step']}] ⚠️  {step['message']}")

        elif step["type"] == "report":
            r = step["report"]
            print("-" * 60)
            print(f"\n📋 FINAL REPORT")
            print(f"Verdict:     {r['verdict'].upper()}")
            print(f"Confidence:  {r['confidence']}%")
            print(f"Summary:     {r['summary']}")
            print(f"Evidence:")
            for e in r["evidence_points"]:
                print(f"  - {e}")
            print(f"Risk note:   {r['risk_note']}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("question", type=str, help="The question to investigate")
    parser.add_argument("--symbol", type=str, default="BTCUSDT")
    args = parser.parse_args()

    asyncio.run(main(args.question, args.symbol))
