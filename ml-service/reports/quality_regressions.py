"""Recorded-output quality acceptance tests, intentionally separate from offline unit CI.

Run explicitly: python -m pytest -q ml-service/reports/quality_regressions.py
No model calls. Failures expose known quality defects in this recorded single pass.
Evidence scope and language annotations are Codex review, not human-confirmed gold.
After a separately authorized future run, review its evidence and regenerate the
report before using these acceptance assertions to assess a proposed prompt fix.
"""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = json.loads((ROOT / "reports/synthetic-quality-results.json").read_text())


def row(scenario, criterion):
    return next(r for r in REPORT["criterion_reviews"]
                if r["scenario_id"] == scenario and r["criterion_id"] == criterion)


def test_clarity_must_not_inherit_the_insult_penalty():
    measured = row("kz_protected_violation", "LOCAL_CLARITY")
    assert measured["expected"] == {"answer": "scale", "value": 10}
    assert measured["actual"] == measured["expected"]


def test_protected_action_without_verification_requires_no():
    measured = row("en_protected_violation", "LOCAL_IDENTITY")
    assert measured["expected"] == {"answer": "no", "value": None}
    assert measured["actual"] == measured["expected"]


def test_kz_na_evidence_must_establish_the_public_request():
    measured = row("kz_public_na", "LOCAL_IDENTITY")
    assert measured["actual"]["answer"] == "na"
    assert measured["semantic_evidence_assessment"] == "supported"


@pytest.mark.parametrize("scenario", ["ru_public_na", "kz_public_na"])
def test_absence_evidence_covers_both_operator_turns_in_these_short_fixtures(scenario):
    measured = row(scenario, "LOCAL_GROSS")
    # This is the predeclared review convention for these two-turn cases, not a new API rule.
    assert {e["message_id"] for e in measured["evidence"]} >= {"m0002", "m0004"}


@pytest.mark.parametrize("scenario", ["ru_public_na", "ru_protected_violation",
                                     "kz_public_na", "kz_protected_violation"])
def test_explanation_language_matches_the_dialogue(scenario):
    measured = [r for r in REPORT["criterion_reviews"] if r["scenario_id"] == scenario]
    assert all(r["actual_explanation_language"] == r["expected_explanation_language"] for r in measured)


def test_critical_flags_remain_correct():
    measured = [r for r in REPORT["criterion_reviews"] if r["criterion_id"] == "LOCAL_GROSS"]
    assert len(measured) == 6
    assert all(r["actual"] == r["expected"] for r in measured)


def test_na_labels_remain_correct():
    measured = [r for r in REPORT["criterion_reviews"] if r["expected"]["answer"] == "na"]
    assert len(measured) == 3
    assert all(r["actual"] == r["expected"] for r in measured)


def test_recorded_quote_spans_are_exact_source_substrings():
    count = 0
    for measured in REPORT["criterion_reviews"]:
        request = json.loads((ROOT / "tests/fixtures" / measured["scenario_id"] / "request.json").read_text())
        messages = {m["id"]: m["text"] for m in request["conversation"]["messages"]}
        for evidence in measured["evidence"]:
            quote = messages[evidence["message_id"]][evidence["start_character"]:evidence["end_character"]]
            assert quote.strip()
            assert hashlib.sha256(quote.encode()).hexdigest() == evidence["quote_sha256"]
            count += 1
    assert count == 27
