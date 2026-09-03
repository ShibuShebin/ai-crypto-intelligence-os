"""
News & sentiment tool.

Uses PUBLIC RSS feeds — no API key, no cost, no rate-limit headaches for a
hackathon demo. Sentiment classification is done by the same LLM the rest
of the agent uses (via agent.llm_client), not a separate paid sentiment API.

NOTE: like binance_market.py, this was written and logic-tested with a
mocked RSS response because the dev sandbox that built it has no network
access to coindesk.com / cointelegraph.com. Run:

    python -m agent.tools.news_sentiment

...on your own machine to confirm live fetches work. If a feed URL has
moved, swap FEEDS below — the parsing logic (standard RSS <item><title>)
doesn't need to change.
"""

from __future__ import annotations
import httpx
import re
from xml.etree import ElementTree
from typing import Any

from agent.llm_client import call_llm

TIMEOUT = 10.0

FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
]

SENTIMENT_SYSTEM_PROMPT = """You are a crypto news sentiment classifier.
Given a list of recent headlines, classify the OVERALL sentiment toward the
given symbol/asset.

Respond ONLY with JSON, no markdown fences:
{
  "sentiment": "bullish" | "bearish" | "neutral" | "mixed",
  "summary": "<1-2 sentence explanation of what the headlines suggest>",
  "relevant_headline_count": <int, how many headlines actually mentioned the asset or closely related topics>
}

If none or almost none of the headlines are relevant to the asset, say so
honestly (sentiment: "neutral", low relevant_headline_count) rather than
forcing a read from unrelated news.
"""


async def _fetch_feed_titles(url: str) -> list[str]:
    """Fetches one RSS feed and extracts item titles. Pure network I/O, no filtering."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        xml_text = resp.text

    return parse_rss_titles(xml_text)


def parse_rss_titles(xml_text: str) -> list[str]:
    """
    Pure function (no network) — parses standard RSS XML and extracts
    <item><title> values. Separated out so it's independently unit-testable
    against a small sample XML string.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    titles = []
    for item in root.iter("item"):
        title_el = item.find("title")
        if title_el is not None and title_el.text:
            titles.append(title_el.text.strip())
    return titles


def filter_relevant_headlines(headlines: list[str], keywords: list[str]) -> list[str]:
    """
    Pure function — keeps only headlines mentioning any of the given keywords
    (case-insensitive). e.g. keywords=["bitcoin", "btc"] for a BTCUSDT question.
    """
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    return [h for h in headlines if pattern.search(h)]


def symbol_to_keywords(symbol: str) -> list[str]:
    """Maps a trading pair like BTCUSDT to headline-matching keywords."""
    base = symbol.upper().replace("USDT", "").replace("USD", "").replace("BUSD", "")
    known = {
        "BTC": ["bitcoin", "btc"],
        "ETH": ["ethereum", "eth", "ether"],
        "SOL": ["solana", "sol"],
        "BNB": ["binance coin", "bnb"],
        "XRP": ["ripple", "xrp"],
    }
    return known.get(base, [base.lower()])


async def get_news_sentiment(symbol: str = "BTCUSDT", headline_limit: int = 15) -> dict[str, Any]:
    """
    Fetches recent headlines from configured RSS feeds, filters to ones
    relevant to the given symbol, and asks the LLM to classify sentiment.
    This is what the orchestrator calls as a single tool.
    """
    all_titles: list[str] = []
    for feed_url in FEEDS:
        try:
            titles = await _fetch_feed_titles(feed_url)
            all_titles.extend(titles)
        except (httpx.HTTPError, httpx.TimeoutException):
            continue  # one feed being down shouldn't kill the whole investigation

    keywords = symbol_to_keywords(symbol)
    relevant = filter_relevant_headlines(all_titles, keywords)[:headline_limit]

    if not relevant:
        return {
            "symbol": symbol,
            "sentiment": "neutral",
            "summary": "No recent headlines specifically mentioning this asset were found.",
            "relevant_headline_count": 0,
            "headlines_sample": [],
        }

    headlines_str = "\n".join(f"- {h}" for h in relevant)
    user_msg = f"Asset: {symbol}\n\nRecent headlines:\n{headlines_str}\n\nClassify the sentiment."

    raw = await call_llm(SENTIMENT_SYSTEM_PROMPT, user_msg, max_tokens=250)
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    import json
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "sentiment": "neutral",
            "summary": "Could not parse sentiment classification.",
            "relevant_headline_count": len(relevant),
        }

    result["symbol"] = symbol
    result["headlines_sample"] = relevant[:5]
    return result


if __name__ == "__main__":
    import asyncio
    import json as _json

    async def _demo():
        print("Fetching news sentiment for BTCUSDT...")
        result = await get_news_sentiment("BTCUSDT")
        print(_json.dumps(result, indent=2))

    asyncio.run(_demo())
