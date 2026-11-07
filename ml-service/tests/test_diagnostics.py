import copy
import json
import logging

import httpx
import pytest
from jsonschema import Draft202012Validator

from app.debug import safe_failure
from app.errors import ServiceError
from app.evaluator import Evaluator
from app.prompt import build_messages
from app.provider import GroqProvider, ProviderReply
from app.structured_output import groq_response_format
from app.validation import Invalid, SCHEMAS, strict_loads, validate_context, validate_shape
from conftest import ScriptedProvider, reply


@pytest.mark.parametrize("raw,code", [
    ('{"answers":[],"answers":[]}', "DUPLICATE_JSON_KEY"),
    ('{"value":NaN}', "NONFINITE_JSON"), ('{"value":1e999}', "NONFINITE_JSON"),
    ('```json\n{}\n```', "INVALID_JSON"), ('{} trailing', "INVALID_JSON"),
])
def test_parser_preserves_safe_reason(raw, code):
    with pytest.raises(Invalid) as raised:
        strict_loads(raw)
    assert raised.value.code == code


@pytest.mark.parametrize("defect,category,code,cid,mid", [
    ("schema", "json_schema", "SCHEMA_INVALID", "S_CLARITY", None),
    ("missing", "criteria_completeness", "CRITERION_MISSING", "S_FLAG", None),
    ("duplicate", "criteria_completeness", "CRITERION_DUPLICATE", "S_HELLO", None),
    ("unknown", "criteria_completeness", "CRITERION_UNKNOWN", None, None),
    ("kind", "answer_type", "ANSWER_KIND", "S_HELLO", None),
    ("level", "allowed_values", "SCALE_LEVEL", "S_CLARITY", None),
    ("na", "na", "NA_FORBIDDEN", "S_HELLO", None),
    ("quote", "evidence_grounding", "EXACT_EVIDENCE", "S_HELLO", "m0003"),
    ("message", "evidence_grounding", "UNKNOWN_MESSAGE", "S_HELLO", None),
])
def test_distinct_validation_stages_with_safe_ids(request_data, output_data, defect, category, code, cid, mid):
    answers = output_data["answers"]
    if defect == "schema": answers[1]["value"] = "10"
    elif defect == "missing": answers.pop()
    elif defect == "duplicate": answers[-1] = copy.deepcopy(answers[0])
    elif defect == "unknown": answers[0]["criterion_id"] = "SECRET_UPSTREAM_TEXT"
    elif defect == "kind": answers[0].update(answer="scale", value=10)
    elif defect == "level": answers[1]["value"] = 9
    elif defect == "na": answers[0].update(answer="na", value=None)
    elif defect == "quote": answers[0]["evidence"][0]["quote"] = "SECRET_UPSTREAM_TEXT"
    elif defect == "message": answers[0]["evidence"][0]["message_id"] = "m9999"
    with pytest.raises(Invalid) as raised:
        validate_shape("provider_output", output_data)
        validate_context("provider_output", output_data, request_data)
    diagnostic = safe_failure(raised.value, request_data, 1)
    assert diagnostic["code"] == code
    assert diagnostic["category"] == category
    assert diagnostic["criterion_id"] == cid and diagnostic["message_id"] == mid
    assert diagnostic["attempt"] == 1
    assert "SECRET_UPSTREAM_TEXT" not in json.dumps(diagnostic)


@pytest.mark.asyncio
async def test_local_logs_and_repair_have_coordinates_but_no_payload(settings, request_data, output_data, caplog):
    original = copy.deepcopy(output_data)
    output_data["answers"][0]["evidence"][0]["quote"] = "SECRET_MODEL_BODY_AND_KEY"
    provider = ScriptedProvider(reply(output_data), reply(original))
    with caplog.at_level(logging.WARNING, logger="ml_service.validation"):
        result = await Evaluator(settings, provider).evaluate(request_data)
    assert result["diagnostics"]["attempt_count"] == 2
    records = [r for r in caplog.records if r.name == "ml_service.validation"]
    assert len(records) == 1
    diagnostic = json.loads(records[0].getMessage().split(" ", 1)[1])
    assert diagnostic == {"category": "evidence_grounding", "code": "EXACT_EVIDENCE",
                          "criterion_id": "S_HELLO", "message_id": "m0003", "attempt": 1,
                          "answer_index": 0, "evidence_index": 0}
    repair = json.loads(provider.messages[1][-1]["content"])["validation_failure"]
    assert repair == diagnostic
    assert "SECRET_MODEL_BODY_AND_KEY" not in caplog.text + json.dumps(repair)
    assert settings.api_key not in caplog.text
    for m in request_data["conversation"]["messages"]:
        assert m["text"] not in caplog.text


@pytest.mark.asyncio
async def test_single_attempt_probe_never_retries(settings, request_data, caplog):
    provider = ScriptedProvider(ProviderReply(None, settings.model, 100, 4096, "PROVIDER_TRUNCATED"))
    with pytest.raises(ServiceError, match="EVALUATOR_INVALID_OUTPUT"):
        await Evaluator(settings, provider, max_attempts=1).evaluate(request_data)
    assert len(provider.messages) == 1
    assert '"category": "completion_length"' in caplog.text and '"attempt": 1' in caplog.text


@pytest.mark.parametrize("budget", [0, 3, True, "1"])
def test_invalid_attempt_budget_rejected(settings, budget):
    with pytest.raises(ValueError):
        Evaluator(settings, ScriptedProvider(), max_attempts=budget)


@pytest.mark.asyncio
@pytest.mark.parametrize("choice,code", [
    ({"finish_reason": "length", "message": {"content": "private truncated text"}}, "PROVIDER_TRUNCATED"),
    ({"finish_reason": "stop", "message": {"refusal": "private refusal"}}, "PROVIDER_REFUSAL"),
    ({"finish_reason": "stop", "message": {"reasoning": "private reasoning"}}, "PROVIDER_CONTENT"),
    ({"finish_reason": "tool_calls", "message": {"content": "private"}}, "PROVIDER_FINISH"),
])
async def test_adapter_retains_distinct_finish_causes(settings, choice, code):
    data = {"model": settings.model, "choices": [choice],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))) as client:
        result = await GroqProvider(settings, client).complete([])
    assert result.invalid_reason == code and result.content is None
    assert result.input_tokens == 20 and result.output_tokens == 10


def test_groq_schema_does_not_mutate_contract_and_keeps_answer_value_pairing(output_data):
    before = copy.deepcopy(SCHEMAS)
    schema = groq_response_format()["json_schema"]["schema"]
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert validator.is_valid(output_data)
    for answer, value in [("yes", 10), ("scale", None), ("na", 0), ("N/A", None)]:
        invalid = copy.deepcopy(output_data)
        invalid["answers"][0].update(answer=answer, value=value)
        assert not validator.is_valid(invalid)
    assert SCHEMAS == before
    # This is only a provider decoding aid. Canonical rules are still independently enforced.
    blank = copy.deepcopy(output_data)
    blank["answers"][0]["evidence"][0]["quote"] = " "
    with pytest.raises(Invalid):
        validate_shape("provider_output", blank)


def test_kazakh_text_and_dynamic_allowed_pairs_are_literal():
    from app.validation import ROOT
    request = strict_loads((ROOT / "tests/fixtures/kz_public_na/request.json").read_bytes())
    messages = build_messages(request)
    context = json.loads(messages[1]["content"])
    assert "\\u" not in messages[1]["content"]
    assert context["conversation"] == request["conversation"]
    assert context["allowed_message_ids"] == [m["id"] for m in request["conversation"]["messages"]]
    for criterion, guide in zip(request["checklist"]["criteria"], context["required_answers"]):
        assert guide["criterion_id"] == criterion["id"]
        choices = guide["allowed_answer_value_pairs"]
        assert ({"answer": "na", "value": None} in choices) == criterion["allow_na"]
        if criterion["kind"] == "scale":
            assert {c["value"] for c in choices if c["answer"] == "scale"} == {l["value"] for l in criterion["levels"]}
