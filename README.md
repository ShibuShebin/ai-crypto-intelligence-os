# AI Crypto Intelligence OS

An autonomous agent that **investigates** crypto market movements instead of
just labeling them. Ask it "why is BTC moving up?" and it decides for itself
what evidence it needs, gathers it step by step, and produces a reasoned
report — with a live trace of every decision it makes along the way.

This is not "AI looks at price → says BUY." It's an agent that reasons about
*what to check next* based on what it's already found.

## Why this is an agent, not a chatbot

```
Need market data
       ↓
Check price + volume
       ↓
Abnormal volume detected
       ↓
Need derivatives data
       ↓
Check open interest + funding rate
       ↓
Potential short squeeze
       ↓
Combine evidence
       ↓
Generate investigation report
```

Each arrow above is a real decision the agent makes at runtime — it doesn't
call a fixed pipeline of tools. If spot data looks unremarkable, it stops
after one check. If something's off, it escalates. That branching logic is
driven by an LLM (Claude) at each step, not hardcoded if/else on price alone.

## Architecture

```
                    AI CRYPTO INTELLIGENCE OS
                              │
                         User / CLI / Dashboard
                              │
                              ▼
                    ┌─────────────────────┐
                    │   AI Orchestrator    │
                    │  (agent/orchestrator │
                    │       .py)           │
                    │                      │
                    │ Decides next tool     │
                    │ Runs investigation    │
                    │ Loops until confident │
                    └──────────┬───────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
       Spot Market        Derivatives        Liquidations
        Snapshot           Snapshot          (placeholder)
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
                     Decision Engine
                  (agent/decision_engine.py)
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Final Report       │
                    │                      │
                    │ Verdict + Confidence │
                    │ Evidence + Risk note │
                    └─────────────────────┘
```

## Status

**Phase 1 (this repo): Intelligence.** Market + derivatives data → autonomous
investigation → report. This is the full current scope.

**Phase 2 (future work, not built): Execution.** AI conclusion → user
approval → Binance order placement. Deliberately out of scope for this
submission — a read-only intelligence agent is a safer, more focused demo
than a bot that also trades.

## Project structure

```
ai-crypto-intelligence-os/
├── agent/
│   ├── orchestrator.py      # the investigation loop
│   ├── decision_engine.py   # evidence -> verdict synthesis
│   └── tools/
│       └── binance_market.py
├── tests/
│   └── test_orchestrator.py # loop logic tested with mocks
├── run.py                   # CLI entrypoint
├── frontend/                # live trace + report UI (in progress)
└── docs/
    └── architecture.md
```

## Setup

```bash
git clone <your-repo-url>
cd ai-crypto-intelligence-os
pip install -r requirements.txt
cp .env.example .env
# add your ANTHROPIC_API_KEY to .env
```

## Usage

```bash
python run.py "Why is BTC moving up?"
python run.py "Is ETH showing signs of a short squeeze?" --symbol ETHUSDT
```

You'll see the agent's reasoning trace print live, step by step, ending in a
structured report:

```
[step 1] 💭 Need baseline price/volume data first. → calling get_spot_snapshot
[step 1] 📊 get_spot_snapshot result: {...}
[step 2] 💭 Volume and price look abnormal, checking derivatives. → calling get_derivatives_snapshot
[step 2] 📊 get_derivatives_snapshot result: {...}
[step 3] 💭 Funding rate confirms leverage-driven move.

📋 FINAL REPORT
Verdict:     BULLISH
Confidence:  78%
Summary:     Elevated funding rate and volume spike suggest a short squeeze in progress.
...
```

## Testing

The orchestrator's decision loop is tested with mocked Binance/Anthropic
responses (no live API calls or keys needed):

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

## Known limitations (Day 1 build)

- **Liquidation data is a placeholder.** Binance doesn't expose a clean REST
  endpoint for this — real implementation needs a `forceOrder` websocket
  listener. Stubbed so the orchestrator's branching logic still runs
  end-to-end; wiring the real feed is a stretch goal.
- **News/sentiment and on-chain sources are not yet integrated** — planned
  for later in the build (see roadmap in `docs/architecture.md`).
- **No frontend yet** — CLI only so far.

## License

MIT
