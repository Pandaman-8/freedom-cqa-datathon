import asyncio
import copy

import pytest

from app.errors import ServiceError
from app.evaluator import Evaluator
from app.provider import ProviderReply
from conftest import ScriptedProvider, reply


@pytest.mark.asyncio
async def test_invalid_evidence_repair_sums_both_attempts(settings, request_data, output_data):
    invalid = copy.deepcopy(output_data)
    invalid["answers"][0]["evidence"][0]["quote"] = "NEVER ECHO THIS PRIVATE PROVIDER TEXT"
    provider = ScriptedProvider(reply(invalid, input_tokens=100), reply(output_data, input_tokens=50))
    result = await Evaluator(settings, provider).evaluate(request_data)
    diagnostics = result["diagnostics"]
    assert diagnostics["attempt_count"] == 2
    assert diagnostics["input_tokens"] == 150 and diagnostics["output_tokens"] == 20
    assert diagnostics["estimated_cost_usd"] == 0
    assert diagnostics["latency_ms"] >= 0
    assert "EXACT_EVIDENCE" in provider.messages[1][-1]["content"]
    assert "PRIVATE PROVIDER TEXT" not in str(provider.messages[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [ServiceError("EVALUATOR_TIMEOUT", retryable=True),
                                     ServiceError("EVALUATOR_RATE_LIMITED", retryable=True),
                                     ProviderReply("broken JSON", "openai/gpt-oss-20b", None, 7)])
async def test_unknown_attempt_usage_is_not_reported_as_zero(settings, request_data, output_data, first):
    provider = ScriptedProvider(first, reply(output_data))
    result = await Evaluator(settings, provider).evaluate(request_data)
    assert result["diagnostics"]["input_tokens"] is None
    assert result["diagnostics"]["estimated_cost_usd"] is None
    assert result["diagnostics"]["attempt_count"] == 2


@pytest.mark.asyncio
async def test_no_third_attempt_or_fake_fallback(settings, request_data):
    provider = ScriptedProvider(ProviderReply("{}", settings.model, 10, 2), ProviderReply("{}", settings.model, 10, 2))
    with pytest.raises(ServiceError, match="EVALUATOR_INVALID_OUTPUT"):
        await Evaluator(settings, provider).evaluate(request_data)
    assert len(provider.messages) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [ServiceError("EVALUATOR_AUTH"), ServiceError("INPUT_TOO_LARGE"),
                                      ServiceError("EVALUATOR_RATE_LIMITED", retryable=True, retry_after=60)])
async def test_nonretryable_and_long_retry_after(settings, request_data, failure):
    provider = ScriptedProvider(failure)
    with pytest.raises(ServiceError):
        await Evaluator(settings, provider).evaluate(request_data)
    assert len(provider.messages) == 1


@pytest.mark.asyncio
async def test_attempt_deadline_and_cancellation(settings, request_data, monkeypatch):
    monkeypatch.setattr("app.evaluator.ATTEMPT_SECONDS", 0.01)
    monkeypatch.setattr("app.evaluator.TOTAL_SECONDS", 1)
    class Slow:
        calls = 0
        cancelled = 0
        async def complete(self, messages):
            self.calls += 1
            try:
                await asyncio.sleep(10)
            finally:
                self.cancelled += 1
    provider = Slow()
    with pytest.raises(ServiceError, match="EVALUATOR_TIMEOUT"):
        await Evaluator(settings, provider).evaluate(request_data)
    assert provider.calls == provider.cancelled == 2


@pytest.mark.asyncio
async def test_overall_monotonic_deadline(settings, request_data, monkeypatch):
    monkeypatch.setattr("app.evaluator.TOTAL_SECONDS", 0.02)
    class Slow:
        async def complete(self, messages):
            await asyncio.sleep(10)
    with pytest.raises(ServiceError, match="EVALUATOR_TIMEOUT"):
        await Evaluator(settings, Slow()).evaluate(request_data)


@pytest.mark.asyncio
async def test_pinned_checklist_not_mutated_during_inference(settings, request_data, output_data):
    original = copy.deepcopy(request_data)
    class EditDuringInference:
        async def complete(self, messages):
            request_data["checklist"]["version"] = 99
            request_data["checklist"]["criteria"].clear()
            return reply(output_data)
    result = await Evaluator(settings, EditDuringInference()).evaluate(request_data)
    assert result["checklist_version"] == original["checklist"]["version"]
    assert len(result["answers"]) == len(original["checklist"]["criteria"])
