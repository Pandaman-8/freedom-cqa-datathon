"""Reproduce T04 reference hashes using exact Fraction arithmetic, no network/data/ML.

python3 server/src/test/python/scoring_reference.py --check
PYTHONPATH=backend backend/.venv/bin/python -B server/src/test/python/scoring_reference.py --check --legacy

The oracle derives points directly from selected/max and applicable weights; it does
not import or translate the production Java implementation. --legacy additionally
compares every field against the unchanged Python Decimal scorer. Maven consumes the
checked-in hashes and needs neither Python nor Pydantic at test runtime.
"""
import argparse
import hashlib
import itertools
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT / "server/src/test/resources/scoring/seed-reference.tsv"


def rounded(value):
    if value is None:
        return None
    # All domain quantities are nonnegative. Integer arithmetic implements HALF_UP.
    cents, remainder = divmod(value.numerator * 100, value.denominator)
    cents += 2 * remainder >= value.denominator
    return f"{cents // 100}.{cents % 100:02}"


def normalize(value):
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return f"{Decimal(str(value)):.2f}"
    return value


def digest(value):
    canonical = json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def reference(checklist, answers):
    cs = checklist["criteria"]
    applicable = [(c, a) for c, a in zip(cs, answers) if c["weight"] > 0 and a["answer"] != "na"]
    weights = {c["id"]: Fraction(c["weight"]) for c, a in applicable}
    points = {
        c["id"]: weights[c["id"]] * (Fraction(a["value"], max(l["value"] for l in c["levels"]))
                  if c["kind"] == "scale" else int(a["answer"] == "yes"))
        for c, a in applicable
    }
    weight = sum(weights.values(), Fraction())
    gross = [c["id"] for c, a in zip(cs, answers) if c["kind"] == "flag" and a["answer"] == "yes"]
    rows = []
    for c, a in zip(cs, answers):
        cid = c["id"]
        rows.append(dict(criterion_id=cid, answer=a["answer"], value=a["value"], configured_weight=c["weight"],
                         effective_weight=rounded(weights[cid] * 100 / weight) if cid in weights else None,
                         earned_points=rounded(points[cid] * 100 / weight) if cid in points else None,
                         raw_points=rounded(points.get(cid)), is_critical=cid in gross))
    sections = []
    for section in checklist["sections"]:
        ids = [c["id"] for c in cs if c["section_id"] == section["id"]]
        w = sum((weights.get(cid, Fraction()) for cid in ids), Fraction())
        p = sum((points.get(cid, Fraction()) for cid in ids), Fraction())
        sections.append(dict(section_id=section["id"], earned_points=rounded(p), applicable_weight=rounded(w),
                             percent=rounded(p * 100 / w) if w else None))
    return dict(overall_score=rounded(sum(points.values(), Fraction()) * 100 / weight) if weight else None,
                applicable_weight=rounded(weight), max_score=100 if weight else None, critical_violation=bool(gross),
                critical_criterion_ids=gross, criteria=rows, sections=sections)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()
    checklist = json.loads((ROOT / "backend/app/seed/chat_quality.json").read_text())
    if args.legacy:
        from app.schemas import Checklist, CriterionAnswer
        from app.scoring import calculate
        legacy_checklist = Checklist.model_validate(checklist)
    options = []
    for c in checklist["criteria"]:
        choices = [("scale", level["value"]) for level in c["levels"]] if c["kind"] == "scale" else [("yes", None), ("no", None)]
        if c["allow_na"]:
            choices.append(("na", None))
        options.append(choices)
    lines = ["# Exact Fraction oracle; SHA256 of sorted JSON with numeric values formatted to two decimals."]
    for index, combination in enumerate(itertools.product(*options)):
        answers = [dict(criterion_id=c["id"], answer=a, value=v, explanation="Synthetic reference.",
                        evidence=[dict(message_id="m0001", quote="Synthetic")])
                   for c, (a, v) in zip(checklist["criteria"], combination)]
        expected = reference(checklist, answers)
        if args.legacy:
            actual = calculate(legacy_checklist, [CriterionAnswer.model_validate(a) for a in answers])
            assert normalize(actual) == normalize(expected), f"Legacy mismatch at {index}"
        lines.append(f"{index}\t{digest(expected)}")
    assert len(lines) == 5185
    output = "\n".join(lines) + "\n"
    if args.check:
        assert OUTPUT.read_text() == output, "Reference hashes differ"
    else:
        OUTPUT.write_text(output)
    print(f"PASS: 5184 exact Fraction references; all score fields" + ("; legacy Python parity" if args.legacy else ""))


if __name__ == "__main__":
    main()
