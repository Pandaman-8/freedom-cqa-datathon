import json

import httpx
import pytest

from app.config import Settings
from app.provider import ProviderReply
from app.validation import CONTRACTS


@pytest.fixture(autouse=True)
def forbid_external_http(monkeypatch):
    """A test must fail even if application error handling catches an accidental network call."""
    attempted = []

    def blocked_sync(*args, **kwargs):
        attempted.append("sync")
        raise AssertionError("Real HTTP transport is forbidden in ML tests")

    async def blocked_async(*args, **kwargs):
        attempted.append("async")
        raise AssertionError("Real HTTP transport is forbidden in ML tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked_sync)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked_async)
    yield
    assert not attempted, "A test attempted to use a real HTTP transport"


@pytest.fixture
def request_data():
    return json.loads((CONTRACTS / "fixtures/positive/evaluation_request.json").read_text())


@pytest.fixture
def output_data():
    return json.loads((CONTRACTS / "fixtures/positive/provider_output.json").read_text())


@pytest.fixture
def settings():
    return Settings(api_key="synthetic-test-key", free_plan_confirmed=True)


def reply(output, *, input_tokens=20, output_tokens=10, model="openai/gpt-oss-20b"):
    return ProviderReply(json.dumps(output), model, input_tokens, output_tokens)


class ScriptedProvider:
    """Test double only; never imported by application modules."""
    def __init__(self, *steps):
        self.steps = list(steps)
        self.messages = []

    async def complete(self, messages):
        self.messages.append(messages)
        value = self.steps.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
