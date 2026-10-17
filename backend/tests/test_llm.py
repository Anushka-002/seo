import json

import httpx
import pytest
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.services import llm as llm_mod
from app.services.llm import (
    GeminiClient,
    GroqClient,
    LLMConfigError,
    LLMError,
    LLMOutputError,
    extract_json,
    generate_structured,
    get_llm,
)

SECRET = "sk-super-secret-123"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(llm_mod, "_sleep", fake_sleep)
    return sleeps


def _settings(provider="groq", **kw) -> Settings:
    return Settings(
        llm_provider=provider,
        groq_api_key=SECRET,
        gemini_api_key=SECRET,
        database_url="sqlite://",
        **kw,
    )


def _http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- request shapes
async def test_groq_request_and_response_parsing():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"] = str(request.url), request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": 1}'}}]})

    async with _http(handler) as http:
        out = await GroqClient(_settings(), http).complete("SYS", "USER", max_tokens=321)
    assert out == '{"ok": 1}'
    assert seen["url"] == llm_mod.GROQ_URL and seen["auth"] == f"Bearer {SECRET}"
    b = seen["body"]
    assert b["model"] == "llama-3.3-70b-versatile" and b["max_tokens"] == 321
    assert b["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in b["messages"]] == ["system", "user"]


async def test_gemini_request_keeps_key_out_of_url():
    seen = {}

    def handler(request):
        seen["url"], seen["key"] = str(request.url), request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"a":'}, {"text": "1}"}]}}]}
        )

    async with _http(handler) as http:
        out = await GeminiClient(_settings("gemini", gemini_model="gem-x"), http).complete("S", "U")
    assert out == '{"a":1}'
    assert SECRET not in seen["url"] and seen["key"] == SECRET and "gem-x" in seen["url"]
    cfg = seen["body"]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "S"


# ---------------------------------------------------------------- errors & retries
@pytest.mark.parametrize("cls", [GroqClient, GeminiClient])
async def test_auth_error_is_friendly_and_does_not_leak_key(cls):
    async with _http(lambda r: httpx.Response(401, text=f"bad key {SECRET}")) as http:
        with pytest.raises(LLMError, match="rejected the API key") as exc:
            await cls(_settings(), http).complete("s", "u")
    assert SECRET not in str(exc.value)


async def test_429_is_retried_with_backoff_then_succeeds(no_sleep):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"retry-after": "2"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    async with _http(handler) as http:
        assert await GroqClient(_settings(), http).complete("s", "u") == "{}"
    assert len(calls) == 3 and no_sleep == [2.0, 2.0]


async def test_persistent_429_gives_rate_limit_message(no_sleep):
    async with _http(lambda r: httpx.Response(429)) as http:
        with pytest.raises(LLMError, match="rate limit"):
            await GroqClient(_settings(), http).complete("s", "u")
    assert len(no_sleep) == llm_mod.MAX_ATTEMPTS - 1


async def test_server_error_and_unexpected_body():
    async with _http(lambda r: httpx.Response(503)) as http:
        with pytest.raises(LLMError, match="HTTP 503"):
            await GroqClient(_settings(), http).complete("s", "u")
    async with _http(lambda r: httpx.Response(200, json={"weird": True})) as http:
        with pytest.raises(LLMError, match="unexpected response"):
            await GroqClient(_settings(), http).complete("s", "u")


async def test_timeout_and_network_errors_are_wrapped():
    def timeout(request):
        raise httpx.ReadTimeout("slow")

    def down(request):
        raise httpx.ConnectError("down")

    async with _http(timeout) as http:
        with pytest.raises(LLMError, match="timed out"):
            await GroqClient(_settings(), http).complete("s", "u")
    async with _http(down) as http:
        with pytest.raises(LLMError, match="Could not reach"):
            await GroqClient(_settings(), http).complete("s", "u")


# ---------------------------------------------------------------- factory
def test_get_llm_selects_provider_and_requires_key():
    assert isinstance(get_llm(_settings("groq")), GroqClient)
    assert isinstance(get_llm(_settings("gemini")), GeminiClient)
    with pytest.raises(LLMConfigError, match="groq"):
        get_llm(Settings(llm_provider="groq", groq_api_key="", database_url="sqlite://"))
    with pytest.raises(ValueError):
        Settings(llm_provider="openai", database_url="sqlite://")


# ---------------------------------------------------------------- JSON extraction
@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Sure! Here you go:\n{"a": 1}\nHope that helps',
        '```{"a": 1}```',
    ],
)
def test_extract_json_tolerates_fences_and_prose(raw):
    assert extract_json(raw) == {"a": 1}


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"str"', ""])
def test_extract_json_rejects_non_objects(raw):
    with pytest.raises(ValueError):
        extract_json(raw)


# ---------------------------------------------------------------- generate_structured
class Out(BaseModel):
    name: str = Field(min_length=3)
    n: int


class Scripted:
    name = "scripted"

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    async def complete(self, system, user, **kw):
        self.prompts.append(user)
        return self.replies.pop(0)


async def test_valid_first_try_makes_one_call():
    llm = Scripted('{"name": "abc", "n": 1}')
    out = await generate_structured(llm, "s", "u", Out)
    assert out == Out(name="abc", n=1) and len(llm.prompts) == 1


async def test_invalid_then_valid_retries_once_with_the_error_in_the_prompt():
    llm = Scripted('{"name": "x"}', '{"name": "good", "n": 2}')
    out = await generate_structured(llm, "s", "base prompt", Out)
    assert out.n == 2 and len(llm.prompts) == 2
    assert llm.prompts[0] == "base prompt"
    assert "previous reply was invalid" in llm.prompts[1] and "base prompt" in llm.prompts[1]


async def test_two_failures_raise_output_error():
    llm = Scripted("garbage", '{"name": "x"}')
    with pytest.raises(LLMOutputError):
        await generate_structured(llm, "s", "u", Out)
    assert len(llm.prompts) == 2


async def test_custom_validator_failure_triggers_retry():
    def must_be_positive(o: Out) -> None:
        if o.n <= 0:
            raise ValueError("n must be positive")

    llm = Scripted('{"name": "abc", "n": 0}', '{"name": "abc", "n": 5}')
    out = await generate_structured(llm, "s", "u", Out, validator=must_be_positive)
    assert out.n == 5 and "n must be positive" in llm.prompts[1]
