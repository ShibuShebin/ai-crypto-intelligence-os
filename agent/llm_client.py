"""
LLM client wrapper — single place that talks to whichever LLM provider is
configured, so orchestrator.py and decision_engine.py don't need to know or
care which one it is.

Default: Groq (free tier, fast, OpenAI-compatible API — get a key at
console.groq.com, no credit card required). Model used is
llama-3.3-70b-versatile, which is strong enough at following the strict
JSON-only instructions this project relies on.

If you later want to switch to Anthropic (e.g. once you have credits again),
set LLM_PROVIDER=anthropic in .env and add ANTHROPIC_API_KEY — the rest of
the codebase doesn't change at all, only this file's internals.
"""

from __future__ import annotations
import os


async def call_llm(system_prompt: str, user_message: str, max_tokens: int = 500) -> str:
    """
    Sends a system+user prompt to the configured LLM and returns the raw
    text response. Callers are responsible for parsing (this project uses
    strict JSON-only prompts, parsed by the caller).
    """
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        return await _call_groq(system_prompt, user_message, max_tokens)
    elif provider == "anthropic":
        return await _call_anthropic(system_prompt, user_message, max_tokens)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Use 'groq' or 'anthropic'.")


async def _call_groq(system_prompt: str, user_message: str, max_tokens: int) -> str:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
    response = await client.chat.completions.create(
        model="openai/gpt-oss-120b",
        max_tokens=max_tokens,
        temperature=0.3,  # lower temp — we want consistent, parseable JSON, not creativity
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content.strip()


async def _call_anthropic(system_prompt: str, user_message: str, max_tokens: int) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text.strip()
