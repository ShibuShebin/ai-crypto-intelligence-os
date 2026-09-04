# Demo Guide

## Before you demo (checklist)

- [ ] `GROQ_API_KEY` set in `.env` (or in your deploy platform's env vars)
- [ ] Backend running: `uvicorn agent.api:app --reload --port 8000` (or your deployed URL)
- [ ] Opened in browser, page loads with no console errors
- [ ] Run through all 3 sample questions below at least once beforehand — Binance/Groq responses vary, so know roughly what verdict each tends to produce
- [ ] Record a backup video (see below) in case live network/API hiccups during judging

## Recommended demo flow (~2 minutes)

**1. Open with the problem (15 sec)**
"Most AI crypto tools just look at price and say buy or sell. This one
investigates — it decides for itself what evidence to check based on what
it finds, the same way an analyst would."

**2. Ask the anchor question (60-90 sec)**
Type: **"Why is BTC moving up?"** and hit Investigate.

Narrate what's happening as the log streams in:
- "It's checking price and volume first — that's always step one."
- "Now it's comparing volume against BTC's own 7-day average — not just guessing from the price move."
- (if it escalates) "Volume came back anomalous, so now it's checking derivatives — open interest and funding rate — to see if leverage is driving this."
- (if it checks news) "And it's cross-checking whether real news backs this move, or if it's purely mechanical."
- Point at the final verdict card: "Verdict, confidence, the actual evidence points, and a risk note — not just a bullish/bearish guess."

**3. Show it adapts (30 sec)**
Ask a second, calmer question: **"Is ETH stable right now?"**
Point out the agent takes a *shorter* path this time — it doesn't force the
same 4-step chain if the data doesn't warrant it. This is the proof it's
reasoning, not running a fixed pipeline.

**4. Close (15 sec)**
"This is Phase 1 — intelligence only, read-only, no trading. Phase 2 would
be verdict → user approval → execution, but we deliberately scoped that out
to keep this focused and safe to demo."

## Sample questions that showcase different paths

| Question | Symbol | Expected path |
|---|---|---|
| "Why is BTC moving up?" | BTCUSDT | Full chain if there's an active move: spot → volume baseline → derivatives → OI history → (maybe) news |
| "Is ETH showing signs of a short squeeze?" | ETHUSDT | Spot → volume → derivatives → OI history (squeeze-focused framing) |
| "Is the market calm right now?" | BTCUSDT | Short path: spot → conclude (good contrast — shows it doesn't over-investigate) |

## Recording a backup video

Do this the night before, not the morning of:

1. Screen-record a full run of the anchor question end to end (log streaming + final report)
2. Keep it under 90 seconds, no narration needed if your slides/README explain it
3. Save to `demo/` (e.g. `demo/demo.mp4`) and link it from the README
4. If your live demo breaks during judging, you have something to fall back to immediately — don't try to debug live in front of judges

## Known rough edges to be upfront about if asked

- Liquidation data is a placeholder (Binance has no clean public REST
  endpoint for it — would need a websocket listener)
- News relevance depends on what's in the RSS feeds at demo time; if
  headlines are thin, the agent correctly says so rather than forcing a read
- Free-tier Groq has rate limits — if you hit one during a live demo, wait
  ~30-60 seconds and retry, or mention it's a free-tier constraint, not a
  bug
