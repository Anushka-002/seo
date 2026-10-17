"""Provider-agnostic LLM client (Groq or Gemini over plain HTTP) + validated JSON output."""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3

_sleep = asyncio.sleep  # patched in tests


class LLMError(RuntimeError):
    """User-presentable LLM failure (never contains keys)."""


class LLMConfigError(LLMError):
    """No API key configured for the selected provider."""


class LLMOutputError(LLMError):
    """The model did not return valid structured output."""


class LLMClient(Protocol):
    name: str

    async def complete(
        self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2
    ) -> str: ...


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    try:
        return min(float(resp.headers.get("retry-after", "")), 5.0)
    except ValueError:
        return min(0.5 * 2**attempt, 4.0)


async def _post_with_retry(
    http: httpx.AsyncClient, url: str, *, headers: dict, body: dict, timeout: float
) -> httpx.Response:
    last: httpx.Response | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = await http.post(url, headers=headers, json=body, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise LLMError("The AI provider timed out. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise LLMError("Could not reach the AI provider.") from exc
        if resp.status_code not in RETRY_STATUSES:
            return resp
        last = resp
        if attempt < MAX_ATTEMPTS - 1:
            await _sleep(_retry_delay(resp, attempt))
    assert last is not None
    return last


def _raise_for_status(resp: httpx.Response) -> None:
    code = resp.status_code
    if code in (401, 403):
        raise LLMError("The AI provider rejected the API key (check your LLM key).")
    if code == 429:
        raise LLMError("The AI provider's rate limit or quota was reached. Try again shortly.")
    if code >= 400:
        raise LLMError(f"The AI provider returned an error (HTTP {code}).")


class GroqClient:
    """Groq's OpenAI-compatible chat completions API in JSON mode."""

    name = "groq"

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._s, self._http = settings, http

    async def complete(
        self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2
    ) -> str:
        body = {
            "model": self._s.groq_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._s.groq_api_key}"}
        async with _ClientScope(self._http) as http:
            resp = await _post_with_retry(
                http, GROQ_URL, headers=headers, body=body, timeout=self._s.llm_timeout
            )
        _raise_for_status(resp)
        try:
            return resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("The AI provider returned an unexpected response.") from exc


class GeminiClient:
    """Google Gemini generateContent API with JSON response mime type."""

    name = "gemini"

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._s, self._http = settings, http

    async def complete(
        self, system: str, user: str, *, max_tokens: int = 1500, temperature: float = 0.2
    ) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        headers = {
            "x-goog-api-key": self._s.gemini_api_key
        }  # header, not URL: keeps keys out of logs
        url = GEMINI_URL.format(model=self._s.gemini_model)
        async with _ClientScope(self._http) as http:
            resp = await _post_with_retry(
                http, url, headers=headers, body=body, timeout=self._s.llm_timeout
            )
        _raise_for_status(resp)
        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("The AI provider returned an unexpected response.") from exc


class _ClientScope:
    """Use the injected client as-is, or open (and close) a temporary one."""

    def __init__(self, http: httpx.AsyncClient | None) -> None:
        self._injected = http
        self._own: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        if self._injected is not None:
            return self._injected
        self._own = httpx.AsyncClient()
        return self._own

    async def __aexit__(self, *exc) -> None:
        if self._own is not None:
            await self._own.aclose()


def get_llm(settings: Settings | None = None, http: httpx.AsyncClient | None = None) -> LLMClient:
    """Build the configured client or raise LLMConfigError when no key is set."""
    s = settings or get_settings()
    if not s.llm_enabled:
        raise LLMConfigError(f"No API key configured for LLM provider '{s.llm_provider}'.")
    return GroqClient(s, http) if s.llm_provider == "groq" else GeminiClient(s, http)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and stray prose."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


async def generate_structured(
    llm: LLMClient,
    system: str,
    user: str,
    model: type[T],
    *,
    validator: Callable[[T], None] | None = None,
    max_tokens: int = 1500,
) -> T:
    """Call the LLM, validate against a Pydantic model, retry once with the error message."""
    prompt, last_error = user, ""
    for attempt in range(2):
        raw = await llm.complete(system, prompt, max_tokens=max_tokens)
        try:
            parsed = model.model_validate(extract_json(raw))
            if validator:
                validator(parsed)
            return parsed
        except (ValueError, ValidationError) as exc:  # JSONDecodeError is a ValueError
            last_error = str(exc)[:600]
            log.warning("llm output invalid (attempt %d): %s", attempt + 1, last_error[:200])
            prompt = (
                f"{user}\n\nYour previous reply was invalid: {last_error}\n"
                "Reply again with ONLY a valid JSON object that matches the requested schema."
            )
    raise LLMOutputError("The AI returned an invalid response twice. Please try again.")
