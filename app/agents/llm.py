"""Builds a LangChain chat model from a provider saved in Settings (the user's own credentials)."""

from langchain_core.language_models.chat_models import BaseChatModel

from ..providers import PROVIDER_TYPES, LLMError

TIMEOUT = 300.0
MAX_RETRIES = 3

# Claude models that accept an effort level
_EFFORT_PREFIXES = (
    "claude-fable", "claude-mythos", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5",
    "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-4-6",
)


def chat_model(provider: dict, model: str, *, effort: str = "", max_tokens: int = 32000) -> BaseChatModel:
    model = model or provider.get("default_model") or ""
    if not model:
        raise LLMError(f"No model set for provider '{provider.get('label')}'.")
    kind = provider["type"]
    key = provider.get("api_key") or None
    base = (provider.get("base_url") or "").rstrip("/")
    extra = provider.get("extra_params") or {}

    if kind == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        kwargs = {}
        if base and base != PROVIDER_TYPES["gemini"]["base_url"]:
            kwargs["base_url"] = base
        return ChatGoogleGenerativeAI(model=model, google_api_key=key, max_retries=MAX_RETRIES, timeout=TIMEOUT, **kwargs)

    if kind == "anthropic":
        from langchain_anthropic import ChatAnthropic
        kwargs = {}
        if effort and model.startswith(_EFFORT_PREFIXES):
            kwargs["reasoning_effort"] = effort
        return ChatAnthropic(model=model, api_key=key, base_url=base or None, max_tokens=max_tokens,
                             max_retries=MAX_RETRIES, default_request_timeout=TIMEOUT, **kwargs)

    if kind == "azure_openai":
        from langchain_openai import AzureChatOpenAI
        if not base or "<resource>" in base:
            raise LLMError(f"Set a base URL for provider '{provider.get('label')}'.")
        return AzureChatOpenAI(azure_endpoint=base, azure_deployment=model, api_key=key,
                               api_version=provider.get("api_version") or PROVIDER_TYPES[kind]["api_version"],
                               max_retries=MAX_RETRIES, timeout=TIMEOUT, model_kwargs=extra)

    if kind in ("openai", "openai_compatible"):
        from langchain_openai import ChatOpenAI
        base = base or PROVIDER_TYPES[kind]["base_url"]
        if not base:
            raise LLMError(f"Set a base URL for provider '{provider.get('label')}'.")
        return ChatOpenAI(model=model, api_key=key or "none", base_url=base, use_responses_api=False,
                          max_retries=MAX_RETRIES, timeout=TIMEOUT, model_kwargs=extra)

    if kind == "ollama":
        from langchain_ollama import ChatOllama
        base = base or PROVIDER_TYPES[kind]["base_url"]
        return ChatOllama(model=model, base_url=base.removesuffix("/v1"))

    raise LLMError(f"Unknown provider type: {kind}")
