"""The demo is offline discussion material, never another approved live fixture."""

import json

from fastapi.testclient import TestClient

from app.config import fingerprint, synthetic_fingerprints
from app.main import create_app
from app.prompt import build_messages
from app.validation import ROOT, strict_loads, validate_context, validate_shape
from conftest import ScriptedProvider


def proposal():
    return strict_loads((ROOT / "reports/dynamic-checklist-demo-proposal.json").read_bytes())


def test_demo_versions_are_valid_and_new_criterion_is_driven_only_by_the_rubric():
    demo = proposal()
    assert demo["status"] == "offline_proposal_only"
    assert demo["registered_for_inference"] is False
    assert demo["request_v1"]["conversation"] == demo["request_v2"]["conversation"]
    for version in (1, 2):
        request = demo[f"request_v{version}"]
        output = demo[f"proposed_answers_v{version}"]
        validate_shape("evaluation_request", request)
        validate_context("evaluation_request", request)
        validate_shape("provider_output", output)
        validate_context("provider_output", output, request)
        assert request["checklist"]["version"] == version
        messages = build_messages(request)
        context = json.loads(messages[1]["content"])
        assert context["checklist"] == request["checklist"]
        assert context["conversation"] == request["conversation"]
        ids = {a["criterion_id"] for a in context["required_answers"]}
        assert ("DEMO_STEP_ORDER" in ids) == (version == 2)
        assert ("LOCAL_GREETING" in ids) == (version == 1)
        assert "DEMO_STEP_ORDER" not in messages[0]["content"]
        assert "LOCAL_GREETING" not in messages[0]["content"]
    # Proposed contrasting labels, not actual model results.
    assert demo["proposed_answers_v1"]["answers"][0]["answer"] == "no"
    assert demo["proposed_answers_v2"]["answers"][0]["answer"] == "yes"


def test_demo_is_not_registered_and_http_refuses_it_without_calling_provider(settings):
    demo = proposal()
    assert len(list((ROOT / "tests/fixtures").glob("*/request.json"))) == 6
    assert fingerprint(demo["request_v2"]["conversation"]) not in synthetic_fingerprints()
    provider = ScriptedProvider()
    with TestClient(create_app(settings, provider)) as client:
        for version in (1, 2):
            request = demo[f"request_v{version}"]
            response = client.post("/v1/evaluate", json=request)
            assert response.status_code == 503
            error = response.json()
            validate_shape("error", error)
            validate_context("error", error, request, http_status=503)
            assert error["detail"]["code"] == "PRIVACY_POLICY_UNCONFIGURED"
            assert error["detail"]["request_id"] == request["request_id"]
    assert not provider.messages
