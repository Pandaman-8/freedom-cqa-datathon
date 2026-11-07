import json

import httpx
import pytest

from app.errors import ServiceError
from app.provider import GroqProvider, retry_after_seconds


@pytest.mark.asyncio
async def test_real_adapter_request_and_response_metadata(settings, output_data):
    calls = []
    async def handle(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["include_reasoning"] is False
        assert body["reasoning_effort"] == "low"
        assert "reasoning_format" not in body  # Unsupported by GPT-OSS.
        assert body["model"] == settings.model and body["stream"] is False
        assert request.headers["authorization"] == "Bearer synthetic-test-key"
        assert request.extensions["timeout"]["connect"] == 5
        return httpx.Response(200, json={"model": settings.model, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output_data)}}], "usage": {"prompt_tokens": 50, "completion_tokens": 25}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await GroqProvider(settings, client).complete([])
    assert json.loads(result.content) == output_data
    assert result.input_tokens == 50 and result.output_tokens == 25
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,code,retryable", [
    (401, {}, "EVALUATOR_AUTH", False), (403, {}, "EVALUATOR_AUTH", False),
    (429, {}, "EVALUATOR_RATE_LIMITED", True), (503, {}, "EVALUATOR_PROVIDER_ERROR", True),
    (413, {}, "INPUT_TOO_LARGE", False),
    (400, {"error": {"code": "context_length_exceeded"}}, "INPUT_TOO_LARGE", False),
    (400, {"error": {"code": "json_validate_failed"}}, "EVALUATOR_INVALID_OUTPUT", True),
    (400, {}, "EVALUATOR_PROVIDER_ERROR", False), (200, [], "EVALUATOR_INVALID_OUTPUT", True),
])
async def test_upstream_status_mapping(settings, status, body, code, retryable):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body, headers={"retry-after": "1"}))) as client:
        with pytest.raises(ServiceError) as raised:
            await GroqProvider(settings, client).complete([])
    assert raised.value.code == code
    assert raised.value.retryable == retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b'\xff', b'{"x":NaN}', b'{} trailing', b"x" * (256 * 1024 + 1)])
async def test_upstream_invalid_bytes_and_size(settings, raw):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw))) as client:
        with pytest.raises(ServiceError, match="EVALUATOR_INVALID_OUTPUT"):
            await GroqProvider(settings, client).complete([])


@pytest.mark.asyncio
async def test_truncated_completion_retains_usage_for_repair(settings):
    body = {"model": settings.model, "usage": {"prompt_tokens": 17, "completion_tokens": 4096},
            "choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as client:
        result = await GroqProvider(settings, client).complete([])
    assert result.content is None and result.output_tokens == 4096
    assert result.invalid_reason == "PROVIDER_TRUNCATED"


@pytest.mark.asyncio
@pytest.mark.parametrize("exception,code", [(httpx.ReadTimeout("private"), "EVALUATOR_TIMEOUT"),
                                          (httpx.ConnectError("private"), "EVALUATOR_PROVIDER_ERROR")])
async def test_transport_errors_safe(settings, exception, code):
    def fail(_):
        raise exception
    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(ServiceError) as raised:
            await GroqProvider(settings, client).complete([])
    assert raised.value.code == code and "private" not in str(raised.value)


@pytest.mark.parametrize("value,expected", [("1.5", 1.5), ("NaN", None), ("Infinity", None),
                                           ("garbage", None), ("-1", 0), (None, None),
                                           ("Wed, 01 Jan 2020 00:00:00 GMT", 0)])
def test_retry_after(value, expected):
    assert retry_after_seconds(value) == expected
