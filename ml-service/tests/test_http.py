import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.provider import GroqProvider
from app.validation import CONTRACTS, ROOT, strict_loads, validate_context, validate_shape
from conftest import ScriptedProvider, reply


def assert_error(response, code, request_id=None):
    payload = response.json()
    validate_shape("error", payload)
    validate_context("error", payload, http_status=response.status_code)
    assert payload["detail"]["code"] == code
    assert payload["detail"]["request_id"] == request_id
    assert response.headers["content-type"].startswith("application/json")


def test_health_never_probes_and_missing_config_is_explicit(request_data):
    provider = ScriptedProvider()
    with TestClient(create_app(Settings(), provider)) as client:
        health = client.get("/health")
        assert health.status_code == 503
        assert health.json()["ready"] is False
        assert "api_key" not in health.text
        assert_error(client.post("/v1/evaluate", json=request_data), "EVALUATOR_UNCONFIGURED", request_data["request_id"])
    assert not provider.messages


@pytest.mark.parametrize("configuration,code", [
    (Settings(api_key="synthetic-test-key", free_plan_confirmed=False), "EVALUATOR_UNCONFIGURED"),
    (Settings(api_key="synthetic-test-key", free_plan_confirmed=True, model="unreviewed-paid-model"), "EVALUATOR_UNCONFIGURED"),
    (Settings(api_key="synthetic-test-key", free_plan_confirmed=True, data_policy="real_data"), "PRIVACY_POLICY_UNCONFIGURED"),
])
def test_cost_and_policy_guards_prevent_any_provider_call(request_data, configuration, code):
    provider = ScriptedProvider()
    with TestClient(create_app(configuration, provider)) as client:
        assert client.get("/health").status_code == 503
        assert_error(client.post("/v1/evaluate", json=request_data), code, request_data["request_id"])
    assert not provider.messages


@pytest.mark.asyncio
async def test_api_through_real_adapter_with_mocked_groq_transport(settings, request_data, output_data):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"model": settings.model,
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output_data)}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 45}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as upstream:
        app = create_app(settings, GroqProvider(settings, upstream))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
                response = await client.post("/v1/evaluate", json=request_data)
    assert response.status_code == 200
    validate_context("evaluation_result", response.json(), request_data)
    assert response.json()["diagnostics"]["input_tokens"] == 123
    assert response.json()["diagnostics"]["output_tokens"] == 45
    assert len(calls) == 1


@pytest.mark.parametrize("path", sorted((ROOT / "tests/fixtures").glob("*/request.json")), ids=lambda p: p.parent.name)
def test_ru_kz_en_synthetic_http_with_injected_test_provider(settings, path):
    request = strict_loads(path.read_bytes())
    output = strict_loads(path.with_name("expected.json").read_bytes())
    provider = ScriptedProvider(reply(output))
    with TestClient(create_app(settings, provider)) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/v1/evaluate", content=path.read_bytes(), headers={"content-type": "application/json; charset=utf-8"})
    assert response.status_code == 200
    validate_shape("evaluation_result", response.json())
    validate_context("evaluation_result", response.json(), request)
    assert response.json()["answers"] == output["answers"]
    assert "AUDIO_NOT_ASSESSED" in response.json()["diagnostics"]["warnings"] if request["conversation"]["channel"] == "voice call" else True


@pytest.mark.parametrize("case", [c for c in json.loads((CONTRACTS / "fixtures/manifest.json").read_text())["cases"]
                                 if c["schema"] == "evaluation_request" and False in c["expected"].values()], ids=lambda c: c["id"])
def test_negative_requests_never_reach_provider(settings, case):
    provider = ScriptedProvider()
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", content=(CONTRACTS / case["file"]).read_bytes(), headers={"content-type": "application/json"})
    assert response.status_code == 422
    validate_shape("error", response.json())
    assert not provider.messages


def test_byte_limits_utf8_duplicates_and_versions(settings, request_data):
    provider = ScriptedProvider()
    with TestClient(create_app(settings, provider)) as client:
        for raw in [b'\xff', b'{"request_id":1,"request_id":2}', b'{"x":NaN}', b'{"x":1e999}', b'{} trailing']:
            assert_error(client.post("/v1/evaluate", content=raw, headers={"content-type": "application/json"}), "INVALID_INPUT")
        oversized = client.post("/v1/evaluate", content=b" " * (1024 * 1024 + 1), headers={"content-type": "application/json"})
        assert oversized.status_code == 413
        assert_error(oversized, "PAYLOAD_TOO_LARGE")
        request_data["contract_version"] = "1.0.0"
        assert_error(client.post("/v1/evaluate", json=request_data), "UNSUPPORTED_CONTRACT", request_data["request_id"])
    assert not provider.messages


def test_private_or_relabelled_transcripts_blocked(settings, request_data):
    provider = ScriptedProvider()
    request_data["conversation"]["messages"][0]["text"] = "Unregistered text even with SYNTHETIC label"
    with TestClient(create_app(settings, provider)) as client:
        assert_error(client.post("/v1/evaluate", json=request_data), "PRIVACY_POLICY_UNCONFIGURED", request_data["request_id"])
    assert not provider.messages


def test_blank_conversation_explicit_error(settings, request_data):
    for message in request_data["conversation"]["messages"]:
        message["text"] = "\u2003\t"
    with TestClient(create_app(settings, ScriptedProvider())) as client:
        assert_error(client.post("/v1/evaluate", json=request_data), "INVALID_INPUT", request_data["request_id"])


def test_http_failures_are_safe_and_do_not_leak(settings, request_data, caplog):
    provider = ScriptedProvider(RuntimeError("SECRET CUSTOMER TEXT https://secret.invalid/?token=private"))
    with TestClient(create_app(settings, provider)) as client:
        response = client.post("/v1/evaluate", json=request_data)
        assert_error(response, "EVALUATOR_PROVIDER_ERROR", request_data["request_id"])
        assert client.get("/health").json()["ready"] is True
    assert "SECRET CUSTOMER" not in response.text + caplog.text
    assert "token=private" not in response.text + caplog.text


@pytest.mark.asyncio
async def test_busy_and_cancellation_release_slot(settings, request_data, output_data):
    started = asyncio.Event()
    finish = asyncio.Event()
    class Blocking:
        calls = 0
        async def complete(self, messages):
            self.calls += 1
            started.set()
            await finish.wait()
            return reply(output_data)
    provider = Blocking()
    app = create_app(settings, provider)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            task = asyncio.create_task(client.post("/v1/evaluate", json=request_data))
            await asyncio.wait_for(started.wait(), 2)
            response = await client.post("/v1/evaluate", json=request_data)
            assert_error(response, "EVALUATOR_BUSY", request_data["request_id"])
            assert (await client.get("/health")).json()["ready"] is False
            assert provider.calls == 1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            finish.set()
            response = await client.post("/v1/evaluate", json=request_data)
            assert response.status_code == 200
            assert provider.calls == 2
