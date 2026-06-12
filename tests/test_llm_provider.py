from __future__ import annotations

import asyncio

import pytest

from cogito_agent.llm.openai_compatible import _classify_error, _should_retry


class _TimeoutLike(TimeoutError):
    pass


def test_classify_timeout():
    exc = _TimeoutLike("connection timed out")
    assert _classify_error(exc) == "unknown"


def test_should_retry_on_timeout():
    class FakeTimeout(Exception):
        pass

    assert _should_retry(FakeTimeout("timeout")) is False  # not httpx.TimeoutException


def test_should_retry_unknown():
    assert _should_retry(ValueError("foo")) is False


def test_parse_tool_calls_string_arguments():
    from cogito_agent.llm.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(api_key="sk-test", base_url="https://test", model="test")
    raw = [
        {
            "id": "call_1",
            "function": {"name": "calculator", "arguments": '{"expression": "1+1"}'},
        }
    ]
    calls = provider._parse_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0].name == "calculator"
    assert calls[0].arguments == {"expression": "1+1"}


def test_parse_tool_calls_malformed_json():
    from cogito_agent.llm.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(api_key="sk-test", base_url="https://test", model="test")
    raw = [
        {
            "id": "call_2",
            "function": {"name": "search", "arguments": "not valid json"},
        }
    ]
    calls = provider._parse_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0].name == "search"
    assert calls[0].arguments["__raw_arguments"] == "not valid json"


def test_parse_tool_calls_dict_arguments():
    from cogito_agent.llm.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(api_key="sk-test", base_url="https://test", model="test")
    raw = [
        {
            "id": "call_3",
            "function": {"name": "write", "arguments": {"path": "/tmp/x", "content": "hello"}},
        }
    ]
    calls = provider._parse_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0].name == "write"
    assert calls[0].arguments == {"path": "/tmp/x", "content": "hello"}


def test_provider_rejects_empty_api_key():
    from cogito_agent.llm.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(api_key="", base_url="https://test", model="test")

    async def run():
        with pytest.raises(RuntimeError, match="LLM_API_KEY"):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    asyncio.run(run())


def test_provider_rejects_stream():
    from cogito_agent.llm.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(api_key="sk-test", base_url="https://test", model="test")

    async def run():
        with pytest.raises(NotImplementedError):
            await provider.chat(messages=[{"role": "user", "content": "hi"}], stream=True)

    asyncio.run(run())

