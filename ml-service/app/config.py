import hashlib
import json
import os
from dataclasses import dataclass, field

from .errors import ServiceError
from .validation import CONTRACTS, ROOT, strict_loads

FREE_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    model: str = "openai/gpt-oss-20b"
    free_plan_confirmed: bool = False
    data_policy: str = "synthetic_only"
    approval_file: str = field(default="", repr=False)
    admission_ml_url: str = "http://127.0.0.1:8001/v1/evaluate"
    external_transfer_authorized: bool = False

    @classmethod
    def from_env(cls):
        return cls(api_key=os.getenv("GROQ_API_KEY", "").strip(),
                   model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
                   free_plan_confirmed=os.getenv("GROQ_FREE_PLAN_CONFIRMED", "false") == "true",
                   data_policy=os.getenv("ML_DATA_POLICY", "synthetic_only"),
                   approval_file=os.getenv("ML_APPROVAL_FILE", "").strip(),
                   admission_ml_url=os.getenv("ML_ADMISSION_URL", "http://127.0.0.1:8001/v1/evaluate").strip(),
                   external_transfer_authorized=os.getenv("ML_EXTERNAL_TRANSFER_AUTHORIZED", "false") == "true")

    def check(self):
        if not self.api_key or self.model not in FREE_MODELS or not self.free_plan_confirmed:
            raise ServiceError("EVALUATOR_UNCONFIGURED")
        if self.data_policy == "synthetic_only":
            return
        if self.data_policy != "approved_dataset" or not self.external_transfer_authorized:
            raise ServiceError("PRIVACY_POLICY_UNCONFIGURED")
        if self.model != "openai/gpt-oss-20b":
            raise ServiceError("PRIVACY_POLICY_UNCONFIGURED")


def fingerprint(conversation):
    raw = json.dumps(conversation, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def synthetic_fingerprints():
    """Only checked-in synthetic input locations, never data/, env paths or source datasets."""
    paths = list((ROOT / "tests/fixtures").glob("*/request.json"))
    paths += list((CONTRACTS / "fixtures/positive").glob("*.json"))
    approved = set()
    for path in paths:
        data = strict_loads(path.read_bytes())
        if isinstance(data, dict) and "conversation" in data:
            if data["conversation"]["dataset_group_id"] == "SYNTHETIC":
                approved.add(fingerprint(data["conversation"]))
    return frozenset(approved)
