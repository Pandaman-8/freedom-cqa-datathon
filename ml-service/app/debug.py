"""Allowlisted local diagnostics; no raw exceptions, content, paths or upstream bodies."""

import json
import logging
import re

LOGGER = logging.getLogger("ml_service.validation")
CATEGORIES = {
    "INVALID_JSON": "json_parsing", "DUPLICATE_JSON_KEY": "json_parsing",
    "NONFINITE_JSON": "json_parsing", "SCHEMA_INVALID": "json_schema",
    "PYDANTIC_INVALID": "pydantic", "CRITERION_MISSING": "criteria_completeness",
    "CRITERION_DUPLICATE": "criteria_completeness", "CRITERION_UNKNOWN": "criteria_completeness",
    "ANSWER_KIND": "answer_type", "SCALE_LEVEL": "allowed_values", "NA_FORBIDDEN": "na",
    "UNKNOWN_MESSAGE": "evidence_grounding", "EXACT_EVIDENCE": "evidence_grounding",
    "IDENTITY_ECHO": "identity", "RESULT_TOO_LARGE": "size",
    "PROVIDER_RESPONSE_TOO_LARGE": "size", "PROVIDER_JSON": "provider_envelope",
    "PROVIDER_ENVELOPE": "provider_envelope", "PROVIDER_SCHEMA_REJECTED": "provider_schema",
    "PROVIDER_TRUNCATED": "completion_length", "PROVIDER_REFUSAL": "refusal",
    "PROVIDER_CHOICES": "provider_envelope", "PROVIDER_FINISH": "provider_envelope",
    "PROVIDER_CONTENT": "provider_content", "PROVIDER_MODEL": "provider_model",
    "PROVIDER_COMPLETION_INVALID": "provider_content",
}
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}\Z")
MESSAGE_ID = re.compile(r"m[0-9]{4,}\Z")


def safe_failure(error, request, attempt):
    code = error.code if error.code in CATEGORIES else "VALIDATION_FAILED"
    cid, mid = error.criterion_id, error.message_id
    known_criteria = {c["id"] for c in request["checklist"]["criteria"]}
    known_messages = {m["id"] for m in request["conversation"]["messages"]}
    # Never log arbitrary model strings pretending to be IDs, even if syntactically valid.
    cid = cid if isinstance(cid, str) and cid in known_criteria and IDENTIFIER.fullmatch(cid) else None
    mid = mid if isinstance(mid, str) and mid in known_messages and MESSAGE_ID.fullmatch(mid) else None
    return {"category": CATEGORIES.get(code, "validation"), "code": code,
            "criterion_id": cid, "message_id": mid, "attempt": attempt,
            "answer_index": error.answer_index, "evidence_index": error.evidence_index}


def report_failure(error, request, attempt):
    diagnostic = safe_failure(error, request, attempt)
    LOGGER.warning("ml_validation_failure %s", json.dumps(diagnostic, ensure_ascii=True))
    return diagnostic
