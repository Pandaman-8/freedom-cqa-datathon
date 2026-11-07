"""Offline prompt-policy regressions, NOT measurements of LLM semantic accuracy.

These check the instructions/context actually sent to the provider. Deliberately
wrong but structurally valid replies illustrate the validator's semantic boundary.
The historical live quality failures remain in reports/quality_regressions.py.
"""

import copy
import json

import pytest

from app.prompt import EXPLANATION_GUIDES, build_messages
from app.validation import ROOT, strict_loads, validate_context, validate_shape


def scenario(name):
    folder = ROOT / "tests/fixtures" / name
    return (strict_loads((folder / "request.json").read_bytes()),
            strict_loads((folder / "expected.json").read_bytes()))


def instructions(request, feedback=None):
    return " ".join(build_messages(request, feedback)[0]["content"].split())


def test_clarity_policy_separates_insults_from_understandability():
    request, _ = scenario("kz_protected_violation")
    system = instructions(request)
    assert "Judge each criterion independently" in system
    assert "An insult must not by itself lower a clarity score when the meaning is clear" in system
    assert "according to its own instruction and level descriptions" in system
    assert "Record the insult under the applicable flag" in system


def test_identity_policy_requires_verification_before_action_not_merely_an_action():
    request, _ = scenario("en_protected_violation")
    system = instructions(request)
    assert "yes means its stated condition is satisfied" in system
    assert "an action performed before verification requires no, never yes or na" in system
    assert "A later verification cannot retroactively justify an earlier action" in system
    assert "system verification before the action can support yes" in system
    assert "a connection event, greeting, request to verify, or pending check is not confirmation" in system


def test_answer_explanation_evidence_consistency_policy():
    request, _ = scenario("en_protected_violation")
    system = instructions(request)
    assert "the answer/value, explanation and evidence must support the same conclusion" in system
    assert "never alter or invent a quote to make the answer fit" in system
    assert "cannot accompany yes for verification-before-action" in system


@pytest.mark.parametrize("code,name", [("RU", "Russian"), ("KZ", "Kazakh"), ("EN", "English")])
def test_explanation_language_policy_preserves_literal_transcript(code, name):
    request, _ = scenario(f"{code.lower()}_public_na")
    messages = build_messages(request)
    system = instructions(request)
    context = json.loads(messages[1]["content"])
    assert f"{code} means {name}" in system
    assert "Write every explanation in conversation.language" in system
    assert "English rubric wording does not change the explanation language" in system
    assert "never translate evidence to match the explanation language" in system
    assert messages[0]["content"].endswith(EXPLANATION_GUIDES[code])
    for other in EXPLANATION_GUIDES.keys() - {code}:
        assert EXPLANATION_GUIDES[other] not in messages[0]["content"]
    assert "They are not evidence or preselected answers" in system
    assert "LOCAL_" not in EXPLANATION_GUIDES[code]
    assert context["conversation"]["language"] == code
    assert context["conversation"]["messages"] == request["conversation"]["messages"]


def test_evidence_policy_requires_relevance_and_na_context_not_just_exact_matching():
    request, _ = scenario("kz_public_na")
    system = instructions(request)
    assert "An existing quote is not sufficient unless it supports the selected answer or level" in system
    assert "cite the actual client question that directly establishes the configured na_rule" in system
    assert "is not a substitute for that client quote" in system
    assert "never invent a client question if no such turn exists" in system
    assert "inspect every relevant operator turn in the checked span" in system
    assert "In a short conversation with two operator turns, cite both" in system
    assert "Do not translate, normalize or trim a quote" in system


@pytest.mark.parametrize("code,example", [
    ("RU", "Оператор выполнил действие до проверки личности."),
    ("KZ", "Оператор әрекетті жеке басты тексеруден бұрын орындаған."),
    ("EN", "The operator acted before verifying the client's identity."),
])
def test_selected_language_examples_survive_repair_without_changing_evidence_or_allowed_pairs(code, example):
    request, _ = scenario(f"{code.lower()}_public_na")
    # Mixed-language source and decomposed Unicode must stay literal, independent of prose language.
    request["conversation"]["messages"][1]["text"] += " Help > Guide; cafe\u0301."
    original = copy.deepcopy(request)
    messages = build_messages(request, {"category": "EVIDENCE_QUOTE"})
    assert example in messages[0]["content"]
    assert "check every explanation sentence" in messages[0]["content"]
    assert messages[:2] == build_messages(request)
    context = json.loads(messages[1]["content"])
    assert request == original
    assert context["conversation"] == original["conversation"]
    assert context["allowed_message_ids"] == [m["id"] for m in original["conversation"]["messages"]]
    for criterion, allowed in zip(original["checklist"]["criteria"], context["required_answers"]):
        pairs = allowed["allowed_answer_value_pairs"]
        assert ({"answer": "na", "value": None} in pairs) == criterion["allow_na"]
        if criterion["kind"] == "scale":
            assert {p["value"] for p in pairs if p["answer"] == "scale"} == {level["value"] for level in criterion["levels"]}
        else:
            assert {p["answer"] for p in pairs} == ({"yes", "no", "na"} if criterion["allow_na"] else {"yes", "no"})
            assert all(p["value"] is None for p in pairs)


@pytest.mark.parametrize("verification_first", [True, False], ids=["before-action", "after-action"])
def test_chronology_context_keeps_system_events_and_repeated_timestamps(verification_first):
    request, _ = scenario("en_protected_violation")
    verification = {"speaker": "system", "text": "Identity verification completed."}
    action = {"speaker": "operator", "text": "I changed your account phone number."}
    ordered = [verification, action] if verification_first else [action, verification]
    request["conversation"]["messages"] = [
        dict(turn, id=f"m{i:04d}", timestamp="00:01") for i, turn in enumerate(ordered, 1)
    ]
    validate_shape("evaluation_request", request)
    validate_context("evaluation_request", request)
    before = copy.deepcopy(request)
    messages = build_messages(request)
    assert json.loads(messages[1]["content"])["conversation"]["messages"] == before["conversation"]["messages"]
    assert request == before
    assert "Use original turn order when timestamps repeat" in instructions(request)
    # This tests preservation of chronology, not the model's eventual yes/no decision.


def test_quality_policy_remains_independent_of_criterion_ids():
    request, _ = scenario("en_protected_violation")
    criterion = next(c for c in request["checklist"]["criteria"] if c["id"] == "LOCAL_IDENTITY")
    criterion["id"] = "REVIEWER_DEFINED_VERIFICATION"
    request["checklist"]["version"] += 1
    context = json.loads(build_messages(request)[1]["content"])
    assert context["checklist"] == request["checklist"]
    ids = {a["criterion_id"] for a in context["required_answers"]}
    assert "REVIEWER_DEFINED_VERIFICATION" in ids and "LOCAL_IDENTITY" not in ids
    assert "LOCAL_" not in instructions(request)


def test_repair_keeps_quality_policy_and_original_context():
    request, _ = scenario("kz_public_na")
    initial = build_messages(request)
    repaired = build_messages(request, {"category": "EVIDENCE_QUOTE", "criterion_id": "LOCAL_IDENTITY"})
    assert repaired[:2] == initial
    assert len(repaired) == 3
    assert "the answer/value, explanation and evidence must support the same conclusion" in instructions(request)


@pytest.mark.parametrize("name,criterion_id,changes", [
    ("kz_protected_violation", "LOCAL_CLARITY", {"value": 0}),
    ("en_protected_violation", "LOCAL_IDENTITY", {"answer": "yes"}),
    ("ru_public_na", "LOCAL_GREETING", {"explanation": "The operator greets the client."}),
    ("kz_public_na", "LOCAL_IDENTITY", {
        "evidence": [{"message_id": "m0002", "quote": "Сәлеметсіз бе! Менің атым Әлия."}]}),
], ids=["wrong-clarity", "wrong-identity", "wrong-language", "irrelevant-exact-quote"])
def test_structural_validation_does_not_establish_semantic_quality(name, criterion_id, changes):
    request, output = scenario(name)
    answer = next(a for a in output["answers"] if a["criterion_id"] == criterion_id)
    answer.update(changes)
    # Known semantic defects still satisfy the shared structural/exact-substring rules.
    # No new heuristic validator, fabricated correction, or claim of semantic rejection.
    validate_shape("provider_output", output)
    validate_context("provider_output", output, request)
