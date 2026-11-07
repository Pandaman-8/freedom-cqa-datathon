"""Offline T02 artifact checks. This is not a Java or Python ML service.

Run with: python contracts/validate.py
Install contracts/requirements.txt in an isolated tooling environment first.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SCHEMAS = ("evaluation_request", "evaluation_result", "provider_output", "error")


class ContextViolation(ValueError):
    """A documented context rule failed after JSON Schema validation."""


def require(condition, rule):
    if not condition:
        raise ContextViolation(rule)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("Non-JSON numeric constant")


def check_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Numeric exponent overflow")
    if isinstance(value, dict):
        for item in value.values():
            check_finite(item)
    elif isinstance(value, list):
        for item in value:
            check_finite(item)


def load(path):
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_pairs,
        parse_constant=reject_constant,
    )
    check_finite(value)
    return value


def validate_request(request):
    """Only already-documented composition rules; no scoring or inference."""
    checklist = request["checklist"]
    sections = [section["id"] for section in checklist["sections"]]
    criteria = checklist["criteria"]
    require(len(set(sections)) == len(sections), "unique_section_ids")
    require(len({c["id"] for c in criteria}) == len(criteria), "unique_criterion_ids")
    require(any(c["weight"] > 0 for c in criteria), "positive_weight_exists")
    for criterion in criteria:
        require(criterion["section_id"] in sections, "existing_section")
        if criterion["allow_na"]:
            require(bool((criterion["na_rule"] or "").strip()), "nonblank_na_rule")
        levels = [level["value"] for level in criterion["levels"]]
        if criterion["kind"] == "flag":
            require(
                criterion["weight"] == 0 and not criterion["allow_na"] and not levels,
                "weightless_flag_without_na_or_levels",
            )
        else:
            require(criterion["weight"] > 0, "positive_nonflag_weight")
        if criterion["kind"] == "scale":
            require(len(levels) >= 2, "at_least_two_scale_levels")
            require(len(set(levels)) == len(levels), "unique_scale_levels")
            require(min(levels) == 0 and max(levels) > 0, "scale_zero_and_positive_max")
        else:
            require(not levels, "non_scale_has_no_levels")
    messages = request["conversation"]["messages"]
    require(
        [m["id"] for m in messages] == [f"m{i:04}" for i in range(1, len(messages) + 1)],
        "ordered_positional_message_ids",
    )


def validate_answers(answers, request):
    criteria = {c["id"]: c for c in request["checklist"]["criteria"]}
    require(
        len(answers) == len(criteria)
        and {a["criterion_id"] for a in answers} == set(criteria),
        "exactly_one_answer_per_configured_criterion",
    )
    messages = {m["id"]: m["text"] for m in request["conversation"]["messages"]}
    for answer in answers:
        criterion = criteria[answer["criterion_id"]]
        if answer["answer"] == "na":
            require(criterion["allow_na"] and criterion["kind"] != "flag", "allowed_na")
        elif criterion["kind"] == "scale":
            require(answer["answer"] == "scale", "scale_answer_kind")
            require(
                answer["value"] in [level["value"] for level in criterion["levels"]],
                "configured_discrete_scale_value",
            )
        else:
            require(answer["answer"] in ("yes", "no"), "binary_or_flag_answer_kind")
        for evidence in answer["evidence"]:
            require(evidence["message_id"] in messages, "existing_message_id")
            require(bool(evidence["quote"].strip()), "nonblank_quote")
            require(
                evidence["quote"] in messages[evidence["message_id"]],
                "exact_quote_without_normalization",
            )


def validate_context(payload, case, request, contract):
    kind = case["schema"]
    if kind == "evaluation_request":
        validate_request(payload)
    elif kind in ("evaluation_result", "provider_output"):
        require(request is not None, "fixture_requires_request_context")
        validate_request(request)
        if kind == "evaluation_result":
            for field, expected in {
                "request_id": request["request_id"],
                "contract_version": request["contract_version"],
                "conversation_id": request["conversation"]["id"],
                "checklist_key": request["checklist"]["key"],
                "checklist_version": request["checklist"]["version"],
            }.items():
                require(payload[field] == expected, "echo_" + field)
            if case["mode"] == "production":
                require(payload["diagnostics"]["attempt_count"] >= 1, "production_attempts")
        validate_answers(payload["answers"], request)
    elif kind == "error":
        detail = payload["detail"]
        codes = contract["failure_policy"]["error_codes"].get(str(case["http_status"]), "")
        require(detail["code"] in codes.split(" / "), "documented_http_status_code_pair")
        if request is not None:
            require(detail["request_id"] == request["request_id"], "error_request_id_echo")


def main():
    plan = load(REPO / "plan.json")
    contract = plan["contracts"]
    manifest = load(ROOT / "fixtures/manifest.json")
    require(contract["version"] == manifest["contract_version"] == "2.0.0", "contract_version")
    require(manifest["transport"]["method"] == "POST", "method")
    require(manifest["transport"]["endpoint"] == "/v1/evaluate", "endpoint")
    for field, value in manifest["transport"].items():
        require(contract["transport"][field] == value, "manifest_transport_" + field)

    validators = {}
    for name in SCHEMAS:
        schema = load(ROOT / (name + ".schema.json"))
        Draft202012Validator.check_schema(schema)
        require(schema == contract["json_schemas"][name], "no_schema_drift_" + name)
        validators[name] = Draft202012Validator(schema)

    cases = manifest["cases"]
    require(len({c["id"] for c in cases}) == len(cases), "unique_fixture_ids")
    require(len({c["file"] for c in cases}) == len(cases), "unique_fixture_files")
    listed = {ROOT / c["file"] for c in cases}
    actual = set((ROOT / "fixtures/positive").glob("*.json")) | set(
        (ROOT / "fixtures/negative").glob("*.json")
    )
    require(listed == actual, "all_fixtures_listed")
    examples = {
        "evaluation_request": contract["example_fixture"]["input"],
        "evaluation_result": contract["example_fixture"]["result"],
        "provider_output": {"answers": contract["example_fixture"]["result"]["answers"]},
        "error": contract["error_example"],
    }
    for name, expected in examples.items():
        require(load(ROOT / "fixtures/positive" / (name + ".json")) == expected, "example_" + name)
    markdown = (REPO / "docs/INTEGRATION_CONTRACT.md").read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", markdown, re.S)]
    for name in ("evaluation_request", "evaluation_result", "error"):
        require(examples[name] in blocks, "markdown_example_" + name)
    require("127.0.0.1:8001/v1/evaluate" in markdown, "markdown_endpoint")

    counts = Counter()
    failures = []
    for case in cases:
        observed = {"parse": False, "schema": None, "context": None}
        try:
            payload = load(ROOT / case["file"])
            observed["parse"] = True
        except (ValueError, UnicodeError):
            payload = None
        if observed["parse"]:
            observed["schema"] = validators[case["schema"]].is_valid(payload)
            if observed["schema"]:
                request = load(ROOT / case["request"]) if "request" in case else None
                if request is not None:
                    validators["evaluation_request"].validate(request)
                try:
                    validate_context(payload, case, request, contract)
                    observed["context"] = True
                except ContextViolation:
                    observed["context"] = False
        if observed != case["expected"]:
            failures.append(f"{case['id']}: expected={case['expected']}, observed={observed}")
        layer = next((k for k, v in case["expected"].items() if v is False), "positive")
        counts[layer] += 1
    if failures:
        raise SystemExit("\n".join(failures))
    print("PASS: 4 Draft 2020-12 metaschemas; extracted schemas equal plan.json.")
    print("PASS: contract 2.0.0, POST /v1/evaluate, manifest and Markdown examples agree.")
    print(f"PASS: {len(cases)} fixtures: {dict(counts)}")
    print("Scope: offline artifacts/context checks only; no Java, ML HTTP, scoring or live-model tests.")


if __name__ == "__main__":
    main()
