"""Pure, deterministic calculation; never ask an LLM to compute the final score."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .schemas import Checklist, CriterionAnswer


class ScoringError(ValueError):
    pass


def _d(value: float) -> Decimal:
    return Decimal(str(value))


def _round(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate_answers(checklist: Checklist, answers: Iterable[CriterionAnswer]) -> list[CriterionAnswer]:
    answers = list(answers)
    expected = {c.id: c for c in checklist.criteria}
    ids = [answer.criterion_id for answer in answers]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ScoringError("Provide exactly one answer for every configured criterion")
    for answer in answers:
        criterion = expected[answer.criterion_id]
        if criterion.kind in ("binary", "flag") and answer.answer not in {"yes", "no", "na"}:
            raise ScoringError(f"{criterion.id}: expected yes/no or permitted N/A")
        if criterion.kind == "scale" and answer.answer not in {"scale", "na"}:
            raise ScoringError(f"{criterion.id}: expected scale value or permitted N/A")
        if answer.answer == "na" and not criterion.allow_na:
            raise ScoringError(f"{criterion.id}: N/A is not allowed")
        if answer.answer == "scale":
            if answer.value is None or answer.value not in [level.value for level in criterion.levels]:
                raise ScoringError(f"{criterion.id}: score must be one of the configured scale levels")
        elif answer.value is not None:
            raise ScoringError(f"{criterion.id}: value is valid only for scale answers")
    return answers


def calculate(checklist: Checklist, raw_answers: Iterable[CriterionAnswer]) -> dict:
    """Normalize applicable weighted points to 100. Critical flag stays separate.

    Rounding to 2 decimal places is specified by the PDF; half-up is our
    conventional implementation detail because the document does not specify
    how to resolve exact ties (e.g. 0.005).
    """
    answers = validate_answers(checklist, raw_answers)
    by_id = {a.criterion_id: a for a in answers}
    applicable = [c for c in checklist.criteria if c.weight > 0 and by_id[c.id].answer != "na"]
    sum_weights = sum((_d(c.weight) for c in applicable), Decimal(0))
    critical_ids = [c.id for c in checklist.criteria if c.kind == "flag" and by_id[c.id].answer == "yes"]
    rows = []
    earned_total = Decimal(0)
    section_acc = {s.id: {"earned": Decimal(0), "max": Decimal(0)} for s in checklist.sections}
    for criterion in checklist.criteria:
        answer = by_id[criterion.id]
        raw_points = None
        effective_weight = None
        earned = None
        if criterion.weight > 0 and answer.answer != "na":
            maximum = max((lvl.value for lvl in criterion.levels), default=1)
            ratio = (Decimal(1) if answer.answer == "yes"
                     else Decimal(0) if answer.answer == "no"
                     else _d(answer.value) / _d(maximum))
            raw_points = _d(criterion.weight) * ratio
            earned_total += raw_points
            section_acc[criterion.section_id]["earned"] += raw_points
            section_acc[criterion.section_id]["max"] += _d(criterion.weight)
            effective_weight = _d(criterion.weight) * Decimal(100) / sum_weights
            earned = raw_points * Decimal(100) / sum_weights
        rows.append({
            "criterion_id": criterion.id,
            "answer": answer.answer,
            "value": answer.value,
            "configured_weight": criterion.weight,
            "effective_weight": None if effective_weight is None else _round(effective_weight),
            "earned_points": None if earned is None else _round(earned),
            "raw_points": None if raw_points is None else _round(raw_points),
            "is_critical": criterion.kind == "flag" and answer.answer == "yes",
        })
    sections = [{
        "section_id": sid,
        "earned_points": _round(info["earned"]),
        "applicable_weight": _round(info["max"]),
        "percent": _round(info["earned"] * Decimal(100) / info["max"]) if info["max"] else None,
    } for sid, info in section_acc.items()]
    return {
        "overall_score": _round(earned_total * Decimal(100) / sum_weights) if sum_weights else None,
        "applicable_weight": _round(sum_weights),
        "max_score": 100 if sum_weights else None,
        "critical_violation": bool(critical_ids),
        "critical_criterion_ids": critical_ids,
        "criteria": rows,
        "sections": sections,
    }
