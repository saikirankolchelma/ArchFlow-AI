"""LLM provider adapters. Each agent can run on any configured provider.

Supported provider types:
  anthropic          - Claude, via the official Anthropic SDK
  openai             - OpenAI chat completions
  azure_openai       - Azure OpenAI deployments
  gemini             - Google Gemini (generateContent)
  openai_compatible  - any OpenAI-compatible endpoint (OpenRouter, Groq, DeepSeek, Mistral, Together, LM Studio, ...)
  ollama             - local models via Ollama's OpenAI-compatible endpoint
"""

import asyncio
import copy

import anthropic
import httpx

# A healthy model answers well within this; a stalled/overloaded one should fail fast with a clear message
# instead of leaving the UI spinning for many minutes.
READ_TIMEOUT = 300.0
TIMEOUT = httpx.Timeout(READ_TIMEOUT, connect=20.0)

PROVIDER_TYPES = {
    "anthropic": {
        "label": "Anthropic (Claude)",
        "needs_key": True,
        "base_url": "",
        "model_hint": "claude-opus-5-5",
    },
    "openai": {
        "label": "OpenAI",
        "needs_key": True,
        "base_url": "https://api.openai.com/v1",
        "model_hint": "your OpenAI model id",
    },
    "azure_openai": {
        "label": "Azure OpenAI",
        "needs_key": True,
        "base_url": "https://<resource>.openai.azure.com",
        "model_hint": "your deployment name",
        "api_version": "2024-10-21",
    },
    "gemini": {
        "label": "Google Gemini",
        "needs_key": True,
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model_hint": "gemini-3.5-flash",
    },
    "openai_compatible": {
        "label": "OpenAI-compatible (OpenRouter, Groq, DeepSeek, Mistral, ...)",
        "needs_key": True,
        "base_url": "",
        "model_hint": "provider's model id",
    },
    "ollama": {
        "label": "Ollama (local)",
        "needs_key": False,
        "base_url": "http://localhost:11434/v1",
        "model_hint": "e.g. llama3.1",
    },
}

# Models that accept output_config.effort
_EFFORT_PREFIXES = (
    "claude-fable", "claude-mythos", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5",
    "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-4-6",
)
# Models that support server-side refusal fallbacks ("default" routing)
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class LLMError(Exception):
    pass


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


async def complete(provider: dict, model: str, system: str, user: str,
                   *, max_tokens: int = 32000, effort: str = "") -> str:
    """Send one system+user prompt and return the model's text reply."""
    model = model or provider.get("default_model") or ""
    if not model:
        raise LLMError(f"No model set for provider '{provider.get('label')}'.")
    kind = provider["type"]
    if kind == "anthropic":
        return await _anthropic(provider, model, system, user, max_tokens, effort)
    if kind == "gemini":
        return await _gemini(provider, model, system, user)
    if kind in ("openai", "openai_compatible", "ollama", "azure_openai"):
        return await _openai_chat(provider, model, system, user)
    raise LLMError(f"Unknown provider type: {kind}")


# ---------------------------------------------------------------- Anthropic

async def _anthropic(p: dict, model: str, system: str, user: str, max_tokens: int, effort: str) -> str:
    client = anthropic.AsyncAnthropic(
        api_key=p.get("api_key") or None,  # None -> SDK resolves ANTHROPIC_API_KEY / profile
        base_url=p.get("base_url") or None,
        timeout=900.0,
    )
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if effort and model.startswith(_EFFORT_PREFIXES):
        kwargs["output_config"] = {"effort": effort}
    extra_body = dict(p.get("extra_params") or {})
    try:
        if model in _FALLBACK_MODELS:
            # On a safety refusal the API re-runs the request on a suitable fallback model.
            async with client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                extra_body=extra_body or None, **kwargs
            ) as stream:
                msg = await stream.get_final_message()
        else:
            async with client.messages.stream(extra_body=extra_body or None, **kwargs) as stream:
                msg = await stream.get_final_message()
    except anthropic.AuthenticationError:
        raise LLMError("Anthropic rejected the API key. Check it in Settings.")
    except anthropic.NotFoundError:
        raise LLMError(f"Anthropic: model '{model}' not found.")
    except anthropic.RateLimitError:
        raise LLMError("Anthropic: rate limited. Wait a moment and retry.")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise LLMError("Could not reach the Anthropic API. Check your network / base URL.")
    finally:
        await client.close()

    if msg.stop_reason == "refusal":
        raise LLMError("The model declined this request.")
    text = "".join(b.text for b in msg.content if b.type == "text")
    if msg.stop_reason == "max_tokens":
        raise LLMError(f"Output hit max_tokens ({max_tokens}). Raise it for this agent in Settings.")
    return text


# ---------------------------------------------------------------- OpenAI-style chat

async def _openai_chat(p: dict, model: str, system: str, user: str) -> str:
    kind = p["type"]
    base = (p.get("base_url") or PROVIDER_TYPES[kind]["base_url"]).rstrip("/")
    if not base or "<resource>" in base:
        raise LLMError(f"Set a base URL for provider '{p.get('label')}'.")
    headers = {"Content-Type": "application/json"}
    if kind == "azure_openai":
        version = p.get("api_version") or PROVIDER_TYPES[kind]["api_version"]
        url = f"{base}/openai/deployments/{model}/chat/completions?api-version={version}"
        if p.get("api_key"):
            headers["api-key"] = p["api_key"]
    else:
        url = f"{base}/chat/completions"
        if p.get("api_key"):
            headers["Authorization"] = f"Bearer {p['api_key']}"

    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if kind in ("openai", "azure_openai"):
        body["response_format"] = {"type": "json_object"}
    body = _deep_merge(body, p.get("extra_params") or {})

    data = await _post(url, headers, body, p.get("label", kind))
    try:
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"Unexpected response from {p.get('label')}: {str(data)[:300]}")
    if choice.get("finish_reason") == "length":
        raise LLMError("Output was cut off (length limit). Add a larger max_tokens in the provider's extra params.")
    return text


# ---------------------------------------------------------------- Gemini

async def _gemini(p: dict, model: str, system: str, user: str) -> str:
    base = (p.get("base_url") or PROVIDER_TYPES["gemini"]["base_url"]).rstrip("/")
    url = f"{base}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": p.get("api_key", "")}
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    body = _deep_merge(body, p.get("extra_params") or {})
    data = await _post(url, headers, body, p.get("label", "Gemini"))
    try:
        cand = data["candidates"][0]
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"Unexpected response from Gemini: {str(data)[:300]}")
    if cand.get("finishReason") == "MAX_TOKENS":
        raise LLMError("Gemini output hit its token limit. Set generationConfig.maxOutputTokens in extra params.")
    return text


RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS = (3, 8, 20)  # seconds; overloaded / rate-limited providers usually recover quickly


async def _post(url: str, headers: dict, body: dict, label: str) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                r = await client.post(url, headers=headers, json=body)
            except httpx.TimeoutException:
                raise LLMError(f"{label}: no response after {int(READ_TIMEOUT)}s. The model is probably overloaded; "
                               "retry, or pick a faster model for this agent in Settings.")
            except httpx.HTTPError as e:
                raise LLMError(f"Could not reach {label}: {e}")
            if r.status_code not in RETRY_STATUS or attempt == len(RETRY_DELAYS):
                break
            await asyncio.sleep(RETRY_DELAYS[attempt])
    if r.status_code == 429:
        raise LLMError(f"{label}: rate limit or quota exceeded. Wait a minute and retry, or check your plan. {r.text[:300]}")
    if r.status_code == 503:
        raise LLMError(f"{label}: the model is overloaded right now. Try again shortly or pick another model in Settings.")
    if r.status_code >= 400:
        raise LLMError(f"{label} returned HTTP {r.status_code}: {r.text[:500]}")
    try:
        return r.json()
    except ValueError:
        raise LLMError(f"{label} returned non-JSON: {r.text[:300]}")


async def test_provider(provider: dict, model: str) -> str:
    return await complete(
        provider, model,
        "You are a connectivity check. Respond with a JSON object.",
        'Reply with exactly: {"status": "ok"}',
        max_tokens=2000,
    )
