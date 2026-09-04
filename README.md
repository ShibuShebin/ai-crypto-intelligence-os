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

## Deploy

This repo deploys as-is to Render (config included: `render.yaml`):

1. Push to GitHub (if you haven't already)
2. Go to [render.com](https://render.com) → New → Web Service → connect your repo
3. Render auto-detects `render.yaml`. Add your `GROQ_API_KEY` in the environment variables section (it's marked `sync: false` so Render prompts you for it rather than committing it)
4. Deploy — you'll get a public URL like `https://ai-crypto-intelligence-os.onrender.com`

A `Procfile` and `runtime.txt` are also included for Railway or other buildpack-based hosts.

**Note:** free-tier Render instances spin down after inactivity and take ~30-60s to wake on the first request — mention this if demoing from a cold deploy, or just hit the URL a minute before you go live.

## Project structure

```
ai-crypto-intelligence-os/
├── agent/
│   ├── api.py                # FastAPI server (SSE streaming + serves frontend)
│   ├── orchestrator.py       # the investigation loop
│   ├── decision_engine.py    # evidence -> verdict synthesis
│   ├── llm_client.py         # provider-agnostic LLM wrapper (Groq default)
│   └── tools/
│       ├── binance_market.py
│       └── news_sentiment.py
├── frontend/                 # no-build HTML/CSS/JS live trace dashboard
├── tests/                    # 21 tests, mocked network/LLM calls
├── docs/
│   ├── architecture.md       # detailed design rationale
│   └── demo.md                # demo script + recording guide
├── run.py                    # CLI entrypoint
├── render.yaml / Procfile    # deploy configs
└── requirements.txt
```

## Setup

```bash
git clone <your-repo-url>
cd ai-crypto-intelligence-os
pip install -r requirements.txt
cp .env.example .env
```

Then add a free Groq API key to `.env`:
1. Go to [console.groq.com](https://console.groq.com), sign up (no credit card needed)
2. Create an API key
3. Paste it into `.env` as `GROQ_API_KEY=...`

## Usage

**CLI:**
```bash
python run.py "Why is BTC moving up?"
python run.py "Is ETH showing signs of a short squeeze?" --symbol ETHUSDT
```

**Web dashboard:**
```bash
uvicorn agent.api:app --reload --port 8000
```
Then open **http://localhost:8000** — type a question, watch the agent's reasoning trace stream in live, ending in a verdict card (bullish/bearish/neutral, confidence, evidence, risk note).

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

## Build log

**Day 1 —** Orchestrator loop, spot + derivatives tools, decision engine, CLI.
Loop logic tested with mocks.

**Day 2 —** Replaced the crude "big price move = anomaly" guess with a real
7-day volume baseline comparison (`get_volume_baseline`), and added open
interest trend tracking (`get_oi_history`) so the agent can tell the
difference between leverage *building up* (a setup) and leverage *unwinding*
(an active squeeze) — same funding rate, very different meaning. Both new
calculations are pure functions with full unit test coverage (edge cases
included, e.g. the exact anomaly threshold boundary). Orchestrator's
tool-selection prompt now encodes this reasoning chain explicitly, and the
decision engine's synthesis prompt weighs evidence accordingly instead of
just reading raw numbers.

**Day 3 —** Swapped the LLM provider from Anthropic to Groq (free tier,
`llama-3.3-70b-versatile`) behind a small `agent/llm_client.py` abstraction —
switching providers now only touches one file. Added a news/sentiment tool
(`get_news_sentiment`) using free public RSS feeds (CoinDesk, CoinTelegraph)
for headlines, no API key needed, with the LLM classifying sentiment.
RSS-parsing and keyword-filtering logic are pure functions with full unit
test coverage. Decision engine now weighs sentiment against the derivatives
evidence — agreement strengthens confidence, disagreement flags a purely
mechanical/leverage-driven move as riskier.

**Day 4 —** Built the web dashboard: `agent/api.py` (FastAPI) streams the
investigation as Server-Sent Events, and `frontend/` (plain HTML/CSS/JS, no
build step) renders the live reasoning trace as a connected case-log, then
a verdict card. Verified end-to-end with a mocked SSE stream (5 events:
thought → observation → thought → report → done) since this sandbox has no
live network access to test the real browser experience — you'll do that
final check locally.

**Day 5 —** Deploy configs (`render.yaml`, `Procfile`, `runtime.txt`),
detailed architecture writeup (`docs/architecture.md`) explaining the
reasoning behind the tool chain and evidence-weighing rules, and a demo
script (`docs/demo.md`) with a recording guide for a backup video.

## Known limitations (as of Day 5)

- **Liquidation data is a placeholder.** Binance doesn't expose a clean REST
  endpoint for this — real implementation needs a `forceOrder` websocket
  listener. Stubbed so the orchestrator's branching logic still runs
  end-to-end; wiring the real feed is a stretch goal.
- **On-chain/whale tracking is not yet integrated** — cut from scope unless
  time allows; not required for the core investigation loop to work.
- **No frontend yet** — CLI only so far, planned for Day 4.
- **News sentiment quality depends on feed relevance** — if RSS feeds return
  mostly unrelated headlines, the tool returns "neutral" honestly rather
  than forcing a read, by design.

## License

MIT
