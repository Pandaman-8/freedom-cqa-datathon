from app.scoring import ScoringError, calculate
from app.schemas import Checklist, CriterionAnswer
from app.storage import SEED_FILE
import json
import pytest


def get_seed():
    return Checklist.model_validate(json.loads(SEED_FILE.read_text(encoding="utf-8")))


def make_answers(checklist):
    return [CriterionAnswer(criterion_id=c.id,
                            answer="scale" if c.kind == "scale" else "no" if c.kind == "flag" else "yes",
                            value=max((lvl.value for lvl in c.levels), default=None) if c.kind == "scale" else None,
                            explanation="Evidence provided", evidence=[{"message_id": "m0001", "quote": "quote"}])
            for c in checklist.criteria]


def test_seed_has_exact_official_criteria_and_weights():
    checklist = get_seed()
    assert len(checklist.criteria) == 8
    assert [c.weight for c in checklist.criteria] == [10, 15, 20, 20, 15, 15, 5, 0]
    assert [x.value for x in checklist.criteria[3].levels] == [0, 5, 10, 15, 20]
    assert [x.value for x in checklist.criteria[5].levels] == [0, 4, 7, 10]
    assert {c.id for c in checklist.criteria if c.allow_na} == {"C02", "C03", "C04", "C07"}


def test_full_score_and_critical_flag_independent():
    c = get_seed()
    answers = make_answers(c)
    assert calculate(c, answers)["overall_score"] == 100
    answers[-1].answer = "yes"
    result = calculate(c, answers)
    assert result["overall_score"] == 100
    assert result["critical_violation"] is True
    assert result["critical_criterion_ids"] == ["C08"]


def test_na_redistributes_and_preserves_scale_proportions():
    c = get_seed()
    answers = make_answers(c)
    by_id = {a.criterion_id: a for a in answers}
    by_id["C03"].answer = "na"  # weight 20 excluded
    by_id["C06"].value = 7   # 7/10 * 15 = 10.5, with weight 80 applicable
    result = calculate(c, answers)
    assert result["overall_score"] == 94.38  # (80-4.5)/80*100 rounded
    c06 = next(row for row in result["criteria"] if row["criterion_id"] == "C06")
    assert c06["raw_points"] == 10.50
    assert c06["earned_points"] == 13.13
    assert result["applicable_weight"] == 80


def test_no_applicable_weight_returns_no_score():
    c = get_seed()
    minimal = c.model_copy(deep=True)
    minimal.criteria = [criterion for criterion in minimal.criteria if criterion.id in {"C03", "C08"}]
    answers = make_answers(minimal)
    answers[0].answer = "na"
    result = calculate(minimal, answers)
    assert result["overall_score"] is None
    assert result["max_score"] is None


def test_invalid_na_and_scale_values_rejected():
    c = get_seed()
    answers = make_answers(c)
    answers[0].answer = "na"
    with pytest.raises(ScoringError, match="N/A"):
        calculate(c, answers)
    answers = make_answers(c)
    answers[3].value = 19  # permitted: 0 / 5 / 10 / 15 / 20
    with pytest.raises(ScoringError, match="scale"):
        calculate(c, answers)


def test_checklist_model_rejects_bad_configuration():
    seed = get_seed().model_dump()
    seed["criteria"][7]["weight"] = 5
    with pytest.raises(ValueError):
        Checklist.model_validate(seed)
