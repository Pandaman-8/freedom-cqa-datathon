"""All 72 shared fixtures across their proper wire boundaries.

Requests/provider outputs exercise the deployed /v1/evaluate handler. Result/error
fixtures are outbound payloads, not evaluate requests: replay their unchanged raw
bytes over a test-only ASGI transport and check the service's Java-facing validators.
This is not a Java/Jackson runtime test or an extra application endpoint.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.provider import ProviderReply
from app.validation import (CONTRACTS, Invalid, request_id_of, strict_loads,
                            validate_context, validate_shape)
from conftest import ScriptedProvider, reply

CASES = json.loads((CONTRACTS / "fixtures/manifest.json").read_text())["cases"]


def syntactic_test_output(request):
    """Shape-only test double. Makes no semantic/model-quality claims."""
    message = next(m for m in request["conversation"]["messages"] if m["text"].strip())
    return {"answers": [{
        "criterion_id": c["id"], "answer": "scale" if c["kind"] == "scale" else "no",
        "value": c["levels"][0]["value"] if c["kind"] == "scale" else None,
        "explanation": "Synthetic transport test double, not an AI judgment.",
        "evidence": [{"message_id": message["id"], "quote": message["text"]}],
    } for c in request["checklist"]["criteria"]]}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_shared_fixture_at_its_http_boundary(case, settings):
    raw = (CONTRACTS / case["file"]).read_bytes()
    positive = all(value is True for value in case["expected"].values())
    kind = case["schema"]
    request = strict_loads((CONTRACTS / case["request"]).read_bytes()) if "request" in case else None
    if kind in ("evaluation_request", "provider_output"):
        if kind == "evaluation_request":
            request = strict_loads(raw) if case["expected"]["parse"] else None
            provider = ScriptedProvider(reply(syntactic_test_output(request))) if positive else ScriptedProvider()
        else:
            result = ProviderReply(raw.decode("utf-8"), settings.model, 20, 10)
            provider = ScriptedProvider(result, result)
        with TestClient(create_app(settings, provider)) as client:
            response = client.post("/v1/evaluate", content=raw if kind == "evaluation_request" else json.dumps(request),
                                   headers={"content-type": "application/json"})
        result = strict_loads(response.content)
        assert response.headers["content-type"] == "application/json"
        if positive:
            assert response.status_code == 200
            validate_shape("evaluation_result", result)
            validate_context("evaluation_result", result, request)
            assert len(provider.messages) == 1
        else:
            expected_status = 422 if kind == "evaluation_request" else 502
            assert response.status_code == expected_status
            validate_shape("error", result)
            validate_context("error", result, http_status=expected_status)
            assert result["detail"]["request_id"] == request_id_of(request)
            assert len(provider.messages) == (0 if kind == "evaluation_request" else 2)
            assert "answers" not in result
        return

    # A tiny test-only byte transport models what Java receives. It never calls ML.
    status = case.get("http_status", 200)

    async def replay(scope, receive, send):
        assert scope["type"] == "http"
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": raw})

    client = TestClient(replay)
    try:
        response = client.get("/fixture")
    finally:
        client.close()
    assert response.content == raw
    observed = {"parse": False, "schema": None, "context": None}
    try:
        payload = strict_loads(response.content)
        observed["parse"] = True
    except Invalid:
        pass
    if observed["parse"]:
        try:
            validate_shape(kind, payload)
            observed["schema"] = True
        except Invalid:
            observed["schema"] = False
        if observed["schema"]:
            try:
                validate_context(kind, payload, request, production=case["mode"] == "production",
                                 http_status=response.status_code)
                observed["context"] = True
            except Invalid:
                observed["context"] = False
    assert observed == case["expected"]
