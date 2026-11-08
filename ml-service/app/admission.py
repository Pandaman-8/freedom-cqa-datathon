"""Strict, read-only proposed v2 admission for specifically reviewed DEV chats.

This is NOT a data-transfer permission or an active policy. Production is disabled
unless a separate operator decision enables an external-transfer switch. A file's
``approved_by`` fields are attestations, not signatures or proof of organizer consent.

No raw approved source, grant content, private paths, or credentials are logged.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat

from .config import fingerprint
from .errors import ServiceError
from .validation import strict_loads

ADMISSION_PROTOCOL = 2
APPROVAL_LIMIT = 1024 * 1024
DATASET_LIMIT = 16 * 1024 * 1024
EXPECTED_KEYS = frozenset({
    "approval_version", "session_id", "approval_reference", "approved_by",
    "processing_mode", "destination_description", "expires_at", "ml_url",
    "dataset_path", "dataset_sha256", "conversation_ids", "provider", "model",
    "checklist_scope",
})
SCOPE_KEYS = frozenset({"key", "min_version", "max_version", "max_criteria", "require_confirmation"})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}\Z")
LANGUAGES = {"RU", "KZ", "EN"}
SPEAKERS = {"client", "operator", "bot", "system"}


def denied():
    return ServiceError("PRIVACY_POLICY_UNCONFIGURED")


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _version(value):
    return type(value) is int and 1 <= value <= 1_000_000


def _private_read(filename, limit, *, grant=False):
    """Reject symlinked files and oversized reads, without echoing private paths."""
    if not isinstance(filename, str) or not filename or not Path(filename).is_absolute():
        raise denied()
    path = Path(filename)
    try:
        if path.is_symlink():
            raise denied()
        meta = path.stat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > limit:
            raise denied()
        if grant and os.name == "posix":
            # A grant must not be readable or writable by other local users.
            if meta.st_uid != os.getuid() or meta.st_mode & 0o077:
                raise denied()
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise denied()
        return data
    except (OSError, ValueError):
        raise denied() from None


def _expiry(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise denied()
    try:
        expiry = datetime.fromisoformat(value[:-1] + "+00:00")
    except (ValueError, OverflowError):
        raise denied() from None
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise denied()
    return expiry


def _dataset_projections(raw, expected_sha, ids):
    """Derive exactly Java's audio-free Dataset.Conversation.projection()."""
    try:
        if not isinstance(expected_sha, str) or SHA256.fullmatch(expected_sha) is None:
            raise denied()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(actual_sha, expected_sha):
            raise denied()
        envelope = strict_loads(raw)
        if not isinstance(envelope, dict) or envelope.get("isSuccess") is not True or envelope.get("error") != "":
            raise denied()
        data = envelope.get("data")
        if not isinstance(data, dict) or data.get("dataset_group_id") != "DEV":
            raise denied()
        records = data.get("records")
        if (not isinstance(records, list) or not records or type(data.get("total_records")) is not int
                or data["total_records"] != len(records)):
            raise denied()
        seen = set()
        result = {}
        for record in records:
            if not isinstance(record, dict):
                raise denied()
            rid = record.get("conversation_id")
            if not _string(rid) or rid in seen:
                raise denied()
            seen.add(rid)
            full_id = "DEV:" + rid
            if full_id not in ids:
                continue
            if (record.get("channel") != "agent chat" or record.get("language") not in LANGUAGES
                    or record.get("audio_url") is not None):
                raise denied()  # Real voice calls and audio locators are excluded.
            turns = record.get("transcript")
            if not isinstance(turns, list) or not turns:
                raise denied()
            messages = []
            for index, turn in enumerate(turns, start=1):
                if (not isinstance(turn, dict) or not _string(turn.get("timestamp"))
                        or turn.get("speaker") not in SPEAKERS or not isinstance(turn.get("text"), str)):
                    raise denied()
                messages.append({"id": f"m{index:04d}", "timestamp": turn["timestamp"],
                                 "speaker": turn["speaker"], "text": turn["text"]})
            result[full_id] = fingerprint({
                "id": full_id, "dataset_group_id": "DEV", "conversation_id": rid,
                "channel": record["channel"], "language": record["language"], "messages": messages,
            })
        if set(result) != ids:
            raise denied()
        return result
    except ServiceError:
        raise
    except (TypeError, ValueError, KeyError, RecursionError):
        raise denied() from None


@dataclass(frozen=True)
class Grant:
    sha256: str
    session_id: str
    model: str
    scope_key: str
    min_version: int
    max_version: int
    max_criteria: int
    require_confirmation: bool
    sources: dict


class ApprovedDatasetAdmission:
    """Load-and-recheck every request; never cache a revoked approval."""

    def __init__(self, settings):
        self.settings = settings

    def load(self):
        s = self.settings
        if (s.data_policy != "approved_dataset" or not s.external_transfer_authorized
                or s.model != "openai/gpt-oss-20b"):
            raise denied()
        raw = _private_read(s.approval_file, APPROVAL_LIMIT, grant=True)
        try:
            obj = strict_loads(raw)
            if not isinstance(obj, dict) or set(obj) != EXPECTED_KEYS:
                raise denied()
            if type(obj["approval_version"]) is not int or obj["approval_version"] != ADMISSION_PROTOCOL:
                raise denied()
            if not _string(obj["session_id"]) or SESSION_ID.fullmatch(obj["session_id"]) is None:
                raise denied()
            if not _string(obj["approval_reference"]) or not _string(obj["destination_description"]):
                raise denied()
            if (obj["approved_by"] != ["Farhat", "Nurtas"]
                    or obj["processing_mode"] != "external_approved"
                    or obj["provider"] != "groq" or obj["model"] != s.model
                    or obj["ml_url"] != s.admission_ml_url):
                raise denied()
            _expiry(obj["expires_at"])
            ids = obj["conversation_ids"]
            if (not isinstance(ids, list) or not (1 <= len(ids) <= 15)
                    or any(not _string(i) or not i.startswith("DEV:") for i in ids)
                    or len(set(ids)) != len(ids)):
                raise denied()
            scope = obj["checklist_scope"]
            if not isinstance(scope, dict) or set(scope) != SCOPE_KEYS:
                raise denied()
            if (not _string(scope["key"]) or not _version(scope["min_version"])
                    or not _version(scope["max_version"])
                    or scope["min_version"] > scope["max_version"]
                    or type(scope["max_criteria"]) is not int or not 1 <= scope["max_criteria"] <= 100
                    or scope["require_confirmation"] is not True):
                raise denied()
            dataset = _private_read(obj["dataset_path"], DATASET_LIMIT)
            sources = _dataset_projections(dataset, obj["dataset_sha256"], set(ids))
            return Grant(hashlib.sha256(raw).hexdigest(), obj["session_id"], obj["model"],
                         scope["key"], scope["min_version"], scope["max_version"],
                         scope["max_criteria"], scope["require_confirmation"], sources)
        except ServiceError:
            raise
        except (KeyError, TypeError, ValueError, RecursionError):
            raise denied() from None

    def authorize(self, request, *, confirmed, expected_sha256=None):
        grant = self.load()
        if expected_sha256 is not None and not hmac.compare_digest(grant.sha256, expected_sha256):
            raise denied()
        try:
            source = request["conversation"]
            checklist = request["checklist"]
            if (confirmed != "true" or grant.sources.get(source["id"]) != fingerprint(source)
                    or checklist["key"] != grant.scope_key
                    or not _version(checklist["version"])
                    or not grant.min_version <= checklist["version"] <= grant.max_version
                    or not isinstance(checklist["criteria"], list)
                    or not 1 <= len(checklist["criteria"]) <= grant.max_criteria):
                raise denied()
            return grant
        except ServiceError:
            raise
        except (KeyError, TypeError, ValueError):
            raise denied() from None

    def health_fields(self):
        grant = self.load()
        # Public health exposes only protocol, mode, model, digest; never private paths/IDs.
        return {"admission_protocol": ADMISSION_PROTOCOL,
                "admission_mode": "approved_dataset", "admission_sha256": grant.sha256,
                "admission_provider": "groq", "admission_model": grant.model}
