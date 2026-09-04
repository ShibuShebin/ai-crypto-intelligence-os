# Architecture

## The core idea

Most "AI crypto" projects are a single LLM call: dump some price data into a
prompt, ask for a verdict. That's a classifier wearing a chatbot costume.

This project is built around one constraint instead: **the agent doesn't
know in advance what evidence it needs.** It decides that at runtime, one
step at a time, based on what it's already found. That's the difference
between an agent and a script — a script's control flow is fixed by the
programmer; this agent's control flow is decided by the model, live,
per-question.

## The investigation loop

```
agent/orchestrator.py :: investigate()

┌─────────────────────────────────────────────────────────┐
│  loop (max 6 steps):                                     │
│                                                            │
│   1. Build a prompt: question + evidence gathered so far  │
│   2. LLM decides: call_tool(name, args)  OR  conclude      │
│   3. If call_tool: run it, append result to evidence,     │
│      yield {thought, tool_called} then {observation}      │
│      → go to 1                                            │
│   4. If conclude: hand all evidence to the decision        │
│      engine, yield {report}, stop                         │
└─────────────────────────────────────────────────────────┘
```

Each iteration is a fresh LLM call that sees the full evidence trail so far
— this is what lets it escalate (or stop early) based on what it actually
found, not a hardcoded sequence.

## Tool registry and the reasoning chain it encodes

| Tool | What it checks | When the agent reaches for it |
|---|---|---|
| `get_spot_snapshot` | 24h price/volume | Always first |
| `get_volume_baseline` | Current volume vs. 7-day average | If price move looks notable |
| `get_derivatives_snapshot` | Open interest, funding rate | If volume is confirmed anomalous |
| `get_oi_history` | OI trend (building/unwinding) | If funding rate is elevated |
| `get_recent_liquidations` | Recent forced closures | If OI is unwinding fast + funding elevated |
| `get_news_sentiment` | RSS headlines + LLM sentiment | To confirm a move has a real story behind it, or to catch a purely mechanical/leverage move with no fundamental backing |

The tool *descriptions themselves* (in `TOOLS` in `orchestrator.py`) are
where the domain reasoning lives — they tell the LLM not just what each
tool returns, but when it's worth calling. This is the "why" the diagram in
the README references:

```
Need market data → check price+volume → abnormal volume detected
→ need derivatives data → check OI+funding → potential short squeeze
→ need external confirmation → check news+sentiment → combine evidence
→ generate investigation report
```

That chain isn't hardcoded as an if/else tree. It's the *expected* path a
well-reasoning agent takes given the tool descriptions — but the agent can
and does deviate: a quiet market with no anomaly stops after one tool call;
a market with anomalous volume but no leverage involvement skips straight
to news without ever touching derivatives data.

## Decision engine: turning evidence into a verdict

`agent/decision_engine.py` is deliberately separate from the orchestration
loop. Its only job is: given a pile of evidence, produce
`{verdict, confidence, summary, evidence_points, risk_note}`.

The system prompt encodes explicit evidence-weighing rules, e.g.:
- Price move + unconfirmed volume anomaly → low confidence, don't force a call
- Elevated funding + OI *building* → a setup, not a confirmed move (lower confidence than "unwinding")
- Elevated funding + OI *unwinding* → active squeeze (higher confidence)
- News sentiment agreeing with price direction → strengthens confidence
- News sentiment silent/contradicting during a leverage-driven move → flagged in the risk note as "could reverse once the squeeze exhausts"

This keeps the "how do we judge evidence" logic testable and tunable
independently of "how do we gather it."

## Why two separate LLM calls (decision + synthesis) instead of one?

Splitting "what to check next" from "what does this all mean" keeps each
prompt focused and keeps the reasoning trace legible — the person watching
the live log sees discrete, explainable decisions rather than one long
opaque chain-of-thought. It also makes both stages independently testable
(see `tests/test_orchestrator.py`, which mocks `call_llm` per-call to
verify the loop branches correctly under different evidence).

## LLM provider abstraction

`agent/llm_client.py` is the only file that knows which LLM provider is
configured (Groq by default, free tier; Anthropic as a drop-in alternative
via `LLM_PROVIDER=anthropic`). Neither the orchestrator nor the decision
engine imports a provider SDK directly — they call `call_llm(system, user,
max_tokens)` and get text back. This was a deliberate refactor (see build
log in the README) once the original Anthropic-only version needed to run
on a free tier for the hackathon budget.

## Frontend: why SSE instead of a request/response API

The live reasoning trace is the actual differentiator of this project over
a plain "ask AI, get answer" tool. A single request/response API would hide
that — the person would just see a spinner, then a final answer, indistin-
guishable from a chatbot. Server-Sent Events let `agent/api.py` push each
orchestrator step to the browser the moment it happens, so `frontend/app.js`
can render the log growing in real time. This is a one-way stream (server →
client), which is all this needs — no websocket complexity for something
that's fundamentally a progress feed.

## What's explicitly out of scope (Phase 2, not built)

Execution — turning a verdict into an actual Binance order — is
deliberately not implemented. A read-only intelligence agent is a safer,
more focused thing to demo and evaluate than a bot that also trades, and it
keeps the submission scoped to what could actually be built well in the
time available. The natural extension (verdict → user approval → order
placement via Binance's authenticated REST endpoints) is a straightforward
next phase given the evidence pipeline already in place.
