"""Java-facing HTTP checks against the real FastAPI app; no external inference."""

import asyncio
import copy
import json
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import create_app
from app.provider import GroqProvider
from app.validation import SCHEMAS
from conftest import ScriptedProvider, reply


@contextmanager
def adapter_client(settings, handler):
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
    try:
        with TestClient(create_app(settings, GroqProvider(settings, upstream))) as client:
            yield client
    finally:
        asyncio.run(upstream.aclose())


def assert_wire_error(response, request, status, code, retryable):
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    body = json.loads(response.content.decode("utf-8"))
    Draft202012Validator(SCHEMAS["error"]).validate(body)
    assert body["detail"]["request_id"] == request["request_id"]
    assert body["detail"]["code"] == code
    assert body["detail"]["retryable"] is retryable
    assert set(body) == {"detail"}  # No partial answers, scores, diagnostics or debug extras.


@pytest.mark.parametrize("phase", ["provider_output", "evaluation_result"])
def test_sync_validation_cannot_return_success_after_total_deadline(settings, request_data, output_data, monkeypatch, phase):
    import app.evaluator as module
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock.now))
    original = module.validate_shape

    def delayed_validation(kind, payload):
        result = original(kind, payload)
        if kind == phase:
            clock.now = 66.0  # Simulate CPU work with no asyncio yield, no 66-second sleep.
        return result

    monkeypatch.setattr(module, "validate_shape", delayed_validation)
    provider = ScriptedProvider(reply(output_data))
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 504, "EVALUATOR_TIMEOUT", True)
    assert len(provider.messages) == 1


def test_late_provider_return_cannot_bypass_attempt_deadline(settings, request_data, output_data, monkeypatch):
    import app.evaluator as module
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock.now))

    class LateProvider:
        async def complete(self, messages):
            clock.now = 31.0
            return reply(output_data)

    with TestClient(create_app(settings, LateProvider(), max_attempts=1)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 504, "EVALUATOR_TIMEOUT", True)


@pytest.mark.parametrize("body", [b"<html>private upstream rejection</html>", b"x" * (256 * 1024 + 1)])
def test_non_json_client_error_is_not_retried_as_model_output(settings, request_data, body):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(400, content=body)

    with adapter_client(settings, handle) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 502, "EVALUATOR_PROVIDER_ERROR", False)
    assert len(calls) == 1
    assert "private upstream" not in response.text


def test_quoted_utf8_content_type_is_valid_json_transport(settings, request_data, output_data):
    with TestClient(create_app(settings, ScriptedProvider(reply(output_data)))) as client:
        response = client.post("/v1/evaluate", content=json.dumps(request_data),
                               headers={"Content-Type": 'application/json; charset="UTF-8"'})
    assert response.status_code == 200


@pytest.mark.parametrize("status,code,retryable,attempts", [
    (401, "EVALUATOR_AUTH", False, 1), (403, "EVALUATOR_AUTH", False, 1),
    (429, "EVALUATOR_RATE_LIMITED", True, 2),
    (500, "EVALUATOR_PROVIDER_ERROR", True, 2), (502, "EVALUATOR_PROVIDER_ERROR", True, 2),
    (503, "EVALUATOR_PROVIDER_ERROR", True, 2),
    (413, "INPUT_TOO_LARGE", False, 1), (400, "EVALUATOR_PROVIDER_ERROR", False, 1),
])
def test_provider_status_reaches_java_with_safe_envelope(settings, request_data, status, code, retryable, attempts, caplog):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "NEVER_LOG_PROVIDER_SECRET"}},
                              headers={"retry-after": "0"})

    with adapter_client(settings, handle) as client:
        response = client.post("/v1/evaluate", json=request_data)
        assert client.get("/health").json()["ready"] is True
    http_status = 503 if status in (401, 403, 429) else 422 if status == 413 else 502
    assert_wire_error(response, request_data, http_status, code, retryable)
    assert len(calls) == attempts
    assert "NEVER_LOG_PROVIDER_SECRET" not in response.text + caplog.text
    assert settings.api_key not in response.text + caplog.text


@pytest.mark.parametrize("exception,code,status", [
    (httpx.ReadTimeout("secret body"), "EVALUATOR_TIMEOUT", 504),
    (httpx.ConnectTimeout("secret key"), "EVALUATOR_TIMEOUT", 504),
    (httpx.ConnectError("secret url"), "EVALUATOR_PROVIDER_ERROR", 502),
])
def test_transport_failure_after_two_attempts(settings, request_data, exception, code, status):
    calls = []

    def handle(request):
        calls.append(request)
        raise exception

    with adapter_client(settings, handle) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, status, code, True)
    assert len(calls) == 2


@pytest.mark.parametrize("upstream_code", ["context_length_exceeded", "context_window_exceeded"])
def test_context_overflow_is_422_without_retry(settings, request_data, upstream_code):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {"code": upstream_code}})

    with adapter_client(settings, handle) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 422, "INPUT_TOO_LARGE", False)
    assert len(calls) == 1


@pytest.mark.parametrize("retry_after", ["3", "60", "99999999"])
def test_retry_after_exceeding_backoff_budget_never_replayed(settings, request_data, retry_after):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": retry_after})

    with adapter_client(settings, handle) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 503, "EVALUATOR_RATE_LIMITED", True)
    assert len(calls) == 1


def test_actual_async_deadline_maps_to_http_504(settings, request_data, monkeypatch):
    monkeypatch.setattr("app.evaluator.TOTAL_SECONDS", 0.02)
    calls = []

    async def handle(request):
        calls.append(request)
        await asyncio.sleep(10)
        raise AssertionError("must be cancelled")

    with adapter_client(settings, handle) as client:
        response = client.post("/v1/evaluate", json=request_data)
        assert client.get("/health").json()["ready"] is True
    assert_wire_error(response, request_data, 504, "EVALUATOR_TIMEOUT", True)
    assert len(calls) == 1


def test_retry_cannot_start_after_budget_consumed_in_backoff(settings, request_data, monkeypatch):
    import app.evaluator as module
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock.now))

    async def late_wakeup(delay):
        clock.now = 66.0

    monkeypatch.setattr(module, "asyncio", SimpleNamespace(timeout=asyncio.timeout, sleep=late_wakeup))
    from app.errors import ServiceError
    provider = ScriptedProvider(ServiceError("EVALUATOR_RATE_LIMITED", retryable=True))
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 504, "EVALUATOR_TIMEOUT", True)
    assert len(provider.messages) == 1


def test_default_limits_are_the_published_contract_values():
    import app.evaluator as module
    from app.main import REQUEST_LIMIT
    from app.provider import RESPONSE_LIMIT
    assert module.ATTEMPT_SECONDS == 30
    assert module.TOTAL_SECONDS == 65
    assert module.MAX_BACKOFF == 2
    assert REQUEST_LIMIT == 1048576 and RESPONSE_LIMIT == 262144


def test_one_mib_request_is_accepted_without_truncation(settings, request_data, output_data):
    from app.main import REQUEST_LIMIT
    raw = json.dumps(request_data).encode()
    raw += b" " * (REQUEST_LIMIT - len(raw))
    with TestClient(create_app(settings, ScriptedProvider(reply(output_data)))) as client:
        response = client.post("/v1/evaluate", content=raw, headers={"content-type": "application/json"})
    assert response.status_code == 200


@pytest.mark.parametrize("count,status", [(100, 200), (101, 422)])
def test_checklist_capacity_http(settings, request_data, output_data, count, status):
    original = request_data["checklist"]["criteria"][0]
    original_answer = output_data["answers"][0]
    request_data["checklist"]["criteria"] = [dict(original, id=f"NEW_{i}") for i in range(count)]
    output_data["answers"] = [dict(original_answer, criterion_id=f"NEW_{i}") for i in range(count)]
    provider = ScriptedProvider(reply(output_data))
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert response.status_code == status
    assert len(provider.messages) == (1 if count == 100 else 0)
    if status == 200:
        assert len(response.json()["answers"]) == count


@pytest.mark.parametrize("raw", [
    '{"answers":[],"answers":[]}', '{"answers":NaN}', '{"answers":Infinity}',
    '{"answers":-Infinity}', '{"answers":1e999}', '{} trailing', '```json\n{}\n```',
])
def test_malformed_model_json_is_502_never_fabricated(settings, request_data, raw):
    from app.provider import ProviderReply
    output = ProviderReply(raw, settings.model, 20, 10)
    provider = ScriptedProvider(output, output)
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 502, "EVALUATOR_INVALID_OUTPUT", True)
    assert len(provider.messages) == 2


@pytest.mark.parametrize("defect", ["missing", "duplicate", "unknown", "boolean", "extra", "na", "flag_na",
                                   "scale", "scale_kind", "message", "quote", "blank", "unicode"])
def test_invalid_model_answers_are_rejected_over_http(settings, request_data, output_data, defect):
    answers = output_data["answers"]
    if defect == "missing": answers.pop()
    elif defect == "duplicate": answers[-1] = copy.deepcopy(answers[0])
    elif defect == "unknown": answers[0]["criterion_id"] = "UNKNOWN_CRITERION"
    elif defect == "boolean": answers[1]["value"] = True
    elif defect == "extra": answers[0]["total"] = 100
    elif defect == "na": answers[0]["answer"] = "na"
    elif defect == "flag_na": answers[3]["answer"] = "na"
    elif defect == "scale": answers[1]["value"] = 9
    elif defect == "scale_kind": answers[1].update(answer="yes", value=None)
    elif defect == "message": answers[0]["evidence"][0]["message_id"] = "m9999"
    elif defect == "quote": answers[0]["evidence"][0]["quote"] = "Operator did not greet"
    elif defect == "blank": answers[0]["evidence"][0]["quote"] = "\u2003\t"
    elif defect == "unicode": answers[0]["evidence"][0]["quote"] = "Нello, I'm Ada."  # Cyrillic Н
    provider = ScriptedProvider(reply(output_data), reply(output_data))
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 502, "EVALUATOR_INVALID_OUTPUT", True)
    assert len(provider.messages) == 2


def test_dynamic_scale_na_flag_and_identity_echo_over_http(settings, request_data, output_data):
    request_data["request_id"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    request_data["checklist"].update(key="dynamic-reviewed", version=37)
    criteria = request_data["checklist"]["criteria"]
    criteria[1].update(id="CUSTOM_SCALE", allow_na=True, na_rule="No operator response.")
    criteria[1]["levels"][-1]["value"] = 123.5
    output_data["answers"][1].update(criterion_id="CUSTOM_SCALE", value=123.5)
    output_data["answers"][3]["answer"] = "yes"  # Flag remains separate, no numeric penalty.
    provider = ScriptedProvider(reply(output_data))
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert response.status_code == 200
    result = response.json()
    Draft202012Validator(SCHEMAS["evaluation_result"]).validate(result)
    assert result["request_id"] == request_data["request_id"]
    assert result["conversation_id"] == request_data["conversation"]["id"]
    assert result["checklist_key"] == "dynamic-reviewed" and result["checklist_version"] == 37
    assert result["answers"] == output_data["answers"]
    assert not {"total", "score", "weights"} & set(result)


@pytest.mark.parametrize("extra_byte", [False, True])
def test_upstream_response_byte_limit_through_http(settings, request_data, output_data, extra_byte):
    from app.provider import RESPONSE_LIMIT
    data = {"model": settings.model, "choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(output_data)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
    raw = json.dumps(data).encode()
    raw += b" " * (RESPONSE_LIMIT + int(extra_byte) - len(raw))
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=raw)

    with adapter_client(settings, handle) as client:
        response = client.post("/v1/evaluate", json=request_data)
    if extra_byte:
        assert_wire_error(response, request_data, 502, "EVALUATOR_INVALID_OUTPUT", True)
        assert len(calls) == 2
    else:
        assert response.status_code == 200 and len(calls) == 1


def test_final_envelope_size_is_checked_after_identity_and_diagnostics(settings, request_data, output_data):
    from app.provider import RESPONSE_LIMIT
    original = output_data["answers"][0]["explanation"]
    length = len(json.dumps(output_data).encode())
    output_data["answers"][0]["explanation"] = "x" * (RESPONSE_LIMIT - 100 - length + len(original))
    assert len(json.dumps(output_data).encode()) < RESPONSE_LIMIT
    provider = ScriptedProvider(reply(output_data), reply(output_data))
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert_wire_error(response, request_data, 502, "EVALUATOR_INVALID_OUTPUT", True)
    assert len(provider.messages) == 2


def test_allowed_scale_na_is_preserved(settings, request_data, output_data):
    request_data["checklist"]["criteria"][1].update(allow_na=True, na_rule="Synthetic applicability rule.")
    output_data["answers"][1].update(answer="na", value=None)
    with TestClient(create_app(settings, ScriptedProvider(reply(output_data)))) as client:
        response = client.post("/v1/evaluate", json=request_data)
    assert response.status_code == 200
    assert response.json()["answers"][1] == output_data["answers"][1]


@pytest.mark.parametrize("content_type", ['application/json; charset="UTF-16"',
                                          'application/json; charset="u t f-8"',
                                          "text/plain", "application/json; unexpected=parameter"])
def test_unsupported_transport_headers_still_rejected(settings, request_data, content_type):
    provider = ScriptedProvider()
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", content=json.dumps(request_data),
                               headers={"content-type": content_type})
    assert_wire_error(response, request_data, 422, "INVALID_INPUT", False)
    assert not provider.messages
