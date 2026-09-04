"""
FastAPI server — exposes the orchestrator as a streaming HTTP endpoint and
serves the static frontend from the same process. One port, one process:
simplest possible deploy target for Render/Railway/Vercel-with-a-server.

Run with:
    uvicorn agent.api:app --reload --port 8000

Then open http://localhost:8000 in a browser.
"""

from __future__ import annotations
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from agent.orchestrator import investigate

app = FastAPI(title="AI Crypto Intelligence OS")

# Wide-open CORS for the hackathon demo. If you deploy frontend and backend
# on different domains, this is what lets the browser talk to the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvestigateRequest(BaseModel):
    question: str
    symbol: str = "BTCUSDT"


@app.post("/api/investigate")
async def api_investigate(req: InvestigateRequest):
    """
    Streams the investigation as Server-Sent Events. Each event's `data` is
    one JSON step dict (same shape yielded by agent.orchestrator.investigate).
    The frontend reads this stream and renders steps live as they arrive.
    """
    async def event_stream():
        async for step in investigate(req.question, req.symbol):
            yield f"data: {json.dumps(step)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve the static frontend at the root. Mounted LAST so it doesn't shadow
# the /api routes registered above.
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
