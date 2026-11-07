import copy
import json

import pytest
from pydantic import ValidationError

from app.models import MODELS
from app.prompt import build_messages
from app.validation import (CONTRACTS, ROOT, Invalid, strict_loads, validate_context,
                            validate_shape)

MANIFEST = json.loads((CONTRACTS / "fixtures/manifest.json").read_text())


@pytest.mark.parametrize("case", MANIFEST["cases"], ids=lambda c: c["id"])
def test_published_fixture_layers(case):
    observed = {"parse": False, "schema": None, "context": None}
    try:
        payload = strict_loads((CONTRACTS / case["file"]).read_bytes())
        observed["parse"] = True
    except Invalid:
        payload = None
    if observed["parse"]:
        try:
            validate_shape(case["schema"], payload)
            observed["schema"] = True
        except Invalid:
            observed["schema"] = False
        if observed["schema"]:
            request = strict_loads((CONTRACTS / case["request"]).read_bytes()) if "request" in case else None
            try:
                validate_context(case["schema"], payload, request,
                                 production=case["mode"] == "production", http_status=case.get("http_status"))
                observed["context"] = True
            except Invalid:
                observed["context"] = False
    assert observed == case["expected"]


@pytest.mark.parametrize("path", sorted((ROOT / "tests/fixtures").glob("*/request.json")), ids=lambda p: p.parent.name)
def test_own_synthetic_grounding_and_dynamic_prompt(path):
    request = strict_loads(path.read_bytes())
    expected = strict_loads(path.with_name("expected.json").read_bytes())
    validate_shape("evaluation_request", request)
    validate_context("evaluation_request", request)
    validate_shape("provider_output", expected)
    validate_context("provider_output", expected, request)
    context = json.loads(build_messages(request)[1]["content"])
    assert context["checklist"] == request["checklist"]
    assert context["conversation"] == request["conversation"]
    assert "request_id" not in context


def test_changed_criterion_and_scale_need_no_code(request_data, output_data):
    request_data["checklist"]["version"] += 1
    criterion = copy.deepcopy(request_data["checklist"]["criteria"][1])
    criterion.update(id="ARBITRARY_NEW_RULE", instruction="New criterion supplied by a reviewer.")
    criterion["levels"][3]["value"] = 123.5
    request_data["checklist"]["criteria"].append(criterion)
    answer = copy.deepcopy(output_data["answers"][1])
    answer.update(criterion_id=criterion["id"], value=123.5)
    output_data["answers"].append(answer)
    validate_shape("evaluation_request", request_data)
    validate_context("evaluation_request", request_data)
    validate_context("provider_output", output_data, request_data)
    assert criterion in json.loads(build_messages(request_data)[1]["content"])["checklist"]["criteria"]


def test_positional_ids_extend_past_four_digits(request_data):
    message = request_data["conversation"]["messages"][0]
    request_data["conversation"]["messages"] = [dict(message, id=f"m{i:04d}") for i in range(1, 10002)]
    validate_context("evaluation_request", request_data)


@pytest.mark.parametrize("value", [True, "2"])
def test_pydantic_independently_rejects_integer_coercion(request_data, value):
    request_data["checklist"]["version"] = value
    with pytest.raises(ValidationError):
        MODELS["evaluation_request"].model_validate(request_data)
