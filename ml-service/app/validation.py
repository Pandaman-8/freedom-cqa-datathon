"""Independent runtime validation; never import the offline fixture checker."""

import json
import math
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from .models import MODELS

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT.parent / "contracts"
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
SCHEMAS = {name: json.loads((CONTRACTS / f"{name}.schema.json").read_text()) for name in MODELS}
VALIDATORS = {name: Draft202012Validator(schema) for name, schema in SCHEMAS.items()}
STATUS_CODES = {
    422: {"INVALID_INPUT", "INPUT_TOO_LARGE", "UNSUPPORTED_CONTRACT"},
    404: {"NOT_FOUND"}, 409: {"VERSION_CONFLICT", "REVIEW_CONFLICT", "REQUEST_ID_CONFLICT"},
    501: {"EVALUATOR_UNCONFIGURED"},
    502: {"EVALUATOR_INVALID_OUTPUT", "EVALUATOR_PROVIDER_ERROR"},
    503: {"EVALUATOR_RATE_LIMITED", "EVALUATOR_AUTH", "PRIVACY_POLICY_UNCONFIGURED", "EVALUATOR_BUSY"},
    504: {"EVALUATOR_TIMEOUT"}, 413: {"PAYLOAD_TOO_LARGE"},
}


class Invalid(ValueError):
    """Only static safe rule codes; never include rejected customer/provider data."""

    def __init__(self, code, *, criterion_id=None, message_id=None,
                 answer_index=None, evidence_index=None):
        super().__init__(code)
        self.code = code
        self.criterion_id = criterion_id
        self.message_id = message_id
        self.answer_index = answer_index
        self.evidence_index = evidence_index


def require(condition, code, **location):
    if not condition:
        raise Invalid(code, **location)


def strict_loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def constant(_):
        raise Invalid("NONFINITE_JSON")

    def finite(value):
        if isinstance(value, float):
            require(math.isfinite(value), "NONFINITE_JSON")
        elif isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)

    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="strict")
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        finite(value)
        return value
    except Invalid:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Invalid("INVALID_JSON") from None


def validate_shape(kind, payload):
    try:
        error = next(VALIDATORS[kind].iter_errors(payload), None)
        if error is not None:
            # Never expose ValidationError.message/instance/schema or arbitrary property names.
            raise shape_error("SCHEMA_INVALID", payload, list(error.absolute_path))
        return MODELS[kind].model_validate(payload)
    except ValidationError as error:
        first = error.errors(include_input=False, include_url=False)[0]
        raise shape_error("PYDANTIC_INVALID", payload, list(first["loc"])) from None
    except RecursionError:
        raise Invalid("SCHEMA_INVALID") from None


def shape_error(code, payload, path):
    location = {}
    if isinstance(payload, dict) and len(path) >= 2 and path[0] == "answers" and type(path[1]) is int:
        index = path[1]
        answers = payload.get("answers")
        if isinstance(answers, list) and 0 <= index < len(answers):
            location["answer_index"] = index
            answer = answers[index]
            if isinstance(answer, dict):
                location["criterion_id"] = answer.get("criterion_id")
                evidence = answer.get("evidence")
                if len(path) >= 4 and path[2] == "evidence" and type(path[3]) is int:
                    ei = path[3]
                    location["evidence_index"] = ei
                    if isinstance(evidence, list) and 0 <= ei < len(evidence) and isinstance(evidence[ei], dict):
                        location["message_id"] = evidence[ei].get("message_id")
    return Invalid(code, **location)


def validate_request(payload):
    checklist = payload["checklist"]
    sections = [s["id"] for s in checklist["sections"]]
    criteria = checklist["criteria"]
    require(len(set(sections)) == len(sections), "DUPLICATE_SECTION")
    require(len({c["id"] for c in criteria}) == len(criteria), "DUPLICATE_CRITERION")
    require(any(c["weight"] > 0 for c in criteria), "NO_WEIGHTED_CRITERIA")
    for c in criteria:
        require(c["section_id"] in sections, "UNKNOWN_SECTION")
        require(not c["allow_na"] or bool((c["na_rule"] or "").strip()), "NA_RULE_REQUIRED")
        values = [level["value"] for level in c["levels"]]
        if c["kind"] == "flag":
            require(c["weight"] == 0 and not c["allow_na"] and not values, "FLAG_COMPOSITION")
        else:
            require(c["weight"] > 0, "POSITIVE_WEIGHT_REQUIRED")
        if c["kind"] == "scale":
            require(len(values) >= 2 and len(set(values)) == len(values)
                    and min(values) == 0 and max(values) > 0, "SCALE_COMPOSITION")
        else:
            require(not values, "NON_SCALE_LEVELS")
    messages = payload["conversation"]["messages"]
    require(all(m["id"] == f"m{i:04d}" for i, m in enumerate(messages, 1)), "MESSAGE_ORDER")


def validate_answers(answers, request):
    criteria = {c["id"]: c for c in request["checklist"]["criteria"]}
    seen = set()
    for index, answer in enumerate(answers):
        cid = answer["criterion_id"]
        require(cid in criteria, "CRITERION_UNKNOWN", answer_index=index)
        require(cid not in seen, "CRITERION_DUPLICATE", criterion_id=cid, answer_index=index)
        seen.add(cid)
    for cid in criteria:
        require(cid in seen, "CRITERION_MISSING", criterion_id=cid)
    messages = {m["id"]: m["text"] for m in request["conversation"]["messages"]}
    for index, a in enumerate(answers):
        c = criteria[a["criterion_id"]]
        location = {"criterion_id": a["criterion_id"], "answer_index": index}
        if a["answer"] == "na":
            require(c["allow_na"] and c["kind"] != "flag", "NA_FORBIDDEN", **location)
        elif c["kind"] == "scale":
            require(a["answer"] == "scale", "ANSWER_KIND", **location)
            require(a["value"] in [l["value"] for l in c["levels"]], "SCALE_LEVEL", **location)
        else:
            require(a["answer"] in ("yes", "no"), "ANSWER_KIND", **location)
        for ei, e in enumerate(a["evidence"]):
            evidence_location = dict(location, message_id=e["message_id"], evidence_index=ei)
            require(e["message_id"] in messages, "UNKNOWN_MESSAGE", **evidence_location)
            require(bool(e["quote"].strip()) and e["quote"] in messages[e["message_id"]],
                    "EXACT_EVIDENCE", **evidence_location)


def validate_context(kind, payload, request=None, *, production=True, http_status=None):
    if kind == "evaluation_request":
        validate_request(payload)
    elif kind in ("evaluation_result", "provider_output"):
        require(request is not None, "REQUEST_REQUIRED")
        validate_request(request)
        if kind == "evaluation_result":
            expected = {"contract_version": request["contract_version"], "request_id": request["request_id"],
                        "conversation_id": request["conversation"]["id"],
                        "checklist_key": request["checklist"]["key"],
                        "checklist_version": request["checklist"]["version"]}
            require(all(payload[k] == v for k, v in expected.items()), "IDENTITY_ECHO")
            require(not production or payload["diagnostics"]["attempt_count"] >= 1, "PRODUCTION_ATTEMPTS")
        validate_answers(payload["answers"], request)
    else:
        detail = payload["detail"]
        require(detail["code"] in STATUS_CODES.get(http_status, set()), "ERROR_STATUS")
        require(request is None or detail["request_id"] == request["request_id"], "ERROR_IDENTITY")


def request_id_of(payload):
    value = payload.get("request_id") if isinstance(payload, dict) else None
    return value if isinstance(value, str) and UUID.fullmatch(value) else None
