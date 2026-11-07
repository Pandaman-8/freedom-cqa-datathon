"""One six-scenario quality pass, with no outer POST replay and <=2 Groq calls/case.

Only the six reviewed request hashes are accepted; model and Free Plan are checked.
The exclusive private ledger prevents accidental repeat passes after timeout/crash.
Prints metadata only. Returned answers remain in the ignored, mode-0600 ledger for
semantic review; neither prompts nor credentials nor raw upstream errors are saved.
Run from repo root: PYTHONPATH=ml-service <venv>/bin/python ml-service/scripts/quality_pass.py
"""

import argparse
import asyncio
import hashlib
import json
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = tuple(f"{language}_{kind}" for language in ("ru", "kz", "en")
                  for kind in ("public_na", "protected_violation"))
MODEL = "openai/gpt-oss-20b"
SPACING_SECONDS = 35.0  # Avoid a burst; not a guarantee of account-specific quota.
RUN_FILES = {"baseline": "synthetic-six-2026-11-07.json",
             "prompt-v3": "synthetic-six-prompt-v3.json"}


def load_cases():
    from app.validation import strict_loads, validate_context, validate_shape
    review = strict_loads((ROOT / "reports/synthetic-quality-review.json").read_bytes())
    cases = []
    for name in SCENARIOS:
        path = ROOT / "tests/fixtures" / name / "request.json"
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != review["scenarios"][name]["request_sha256"]:
            raise ValueError("Reviewed synthetic request changed; do not send unreviewed data")
        request = strict_loads(raw)
        validate_shape("evaluation_request", request)
        validate_context("evaluation_request", request)
        if request["conversation"]["id"] != "SYNTHETIC:" + name:
            raise ValueError("Unapproved scenario identity")
        request["request_id"] = str(uuid4())
        cases.append((name, request))
    return cases


class AttemptAudit:
    def __init__(self, delegate, records):
        self.delegate = delegate
        self.records = records
        self.current = None

    async def complete(self, messages):
        from app.errors import ServiceError
        if self.current not in SCENARIOS:
            raise ServiceError("PRIVACY_POLICY_UNCONFIGURED")
        attempts = self.records[self.current]["attempts"]
        if len(attempts) >= 2:
            raise ServiceError("EVALUATOR_PROVIDER_ERROR")
        metadata = {"attempt": len(attempts) + 1, "input_tokens": None, "output_tokens": None}
        attempts.append(metadata)
        start = time.monotonic()
        try:
            reply = await self.delegate.complete(messages)
            metadata.update(input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
                            completion_valid_at_adapter=reply.invalid_reason is None)
            return reply
        except ServiceError as exc:
            metadata["code"] = exc.code
            raise
        finally:
            metadata["latency_ms"] = round((time.monotonic() - start) * 1000)


def reserve_ledger(run_id):
    """Each explicitly authorized pass gets one exclusive ledger; never overwrite a run."""
    from app.prompt import PROMPT_VERSION
    if run_id not in RUN_FILES:
        raise ValueError("Unknown quality run")
    if run_id == "prompt-v3" and PROMPT_VERSION != "cqa-dynamic/3":
        raise ValueError("This repeat pass requires prompt cqa-dynamic/3")
    directory = ROOT / ".quality-run"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / RUN_FILES[run_id]
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    return path


def main(run_id="baseline"):
    from app.config import Settings
    from app.main import create_app
    from app.prompt import PROMPT_VERSION, SYSTEM
    from app.validation import strict_loads, validate_context, validate_shape
    load_dotenv(ROOT / ".env", override=False)
    settings = Settings.from_env()
    settings.check()
    if settings.model != MODEL:
        raise ValueError("Only the explicitly approved model is allowed")
    cases = load_cases()
    # Atomic exclusive creation: never resume/replay a run without a new authorization.
    path = reserve_ledger(run_id)
    ledger = {"model": MODEL, "contract_version": "2.0.0",
              "run_id": run_id, "prompt_version": PROMPT_VERSION,
              "system_prompt_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
              "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "scenarios": {}}

    def save():
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(ledger, file, ensure_ascii=True, indent=2, allow_nan=False)
        os.replace(temporary, path)

    save()
    app = create_app(settings, max_attempts=2)
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="warning"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        thread = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("Local server did not start")
                time.sleep(0.05)
            audit = AttemptAudit(app.state.evaluator.provider, ledger["scenarios"])
            app.state.evaluator.provider = audit
            with httpx.Client(timeout=70, trust_env=False, follow_redirects=False) as client:
                for index, (name, request) in enumerate(cases):
                    record = {"request_id": request["request_id"], "language": request["conversation"]["language"],
                              "status": "pending", "attempts": []}
                    ledger["scenarios"][name] = record
                    save()  # Persist intent BEFORE sending; pending/unknown must never be replayed.
                    audit.current = name
                    start = time.monotonic()
                    try:
                        response = client.post(f"http://127.0.0.1:{port}/v1/evaluate", json=request)
                        body = strict_loads(response.content)
                        kind = "evaluation_result" if response.status_code == 200 else "error"
                        validate_shape(kind, body)
                        validate_context(kind, body, request, http_status=response.status_code)
                    except Exception:
                        record.update(status="unknown", latency_ms=round((time.monotonic() - start) * 1000))
                        ledger["status"] = "stopped_unknown"
                        save()
                        print(json.dumps({"scenario": name, "status": "unknown", "replayed": False}), flush=True)
                        return 1
                    record.update(status="succeeded" if response.status_code == 200 else "failed",
                                  http_status=response.status_code, result=body,
                                  latency_ms=round((time.monotonic() - start) * 1000))
                    save()
                    summary = {"scenario": name, "http_status": response.status_code,
                               "attempts": len(record["attempts"]), "latency_ms": record["latency_ms"]}
                    if response.status_code == 200:
                        summary["diagnostics"] = body["diagnostics"]
                    else:
                        summary["code"] = body["detail"]["code"]
                    print(json.dumps(summary), flush=True)
                    if response.status_code != 200 and body["detail"]["code"] in {
                        "EVALUATOR_AUTH", "EVALUATOR_UNCONFIGURED", "PRIVACY_POLICY_UNCONFIGURED",
                        "EVALUATOR_PROVIDER_ERROR", "EVALUATOR_RATE_LIMITED", "EVALUATOR_TIMEOUT",
                    }:
                        ledger["status"] = "stopped_unavailable"
                        save()
                        return 1
                    if index != len(cases) - 1:
                        time.sleep(SPACING_SECONDS)
            ledger["status"] = "complete"
            save()
            return 0
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live synthetic quality pass; requires separate authorization.")
    parser.add_argument("--run-id", choices=tuple(RUN_FILES), default="baseline",
                        help="Use prompt-v3 only after authorization for the second pass. Never delete a ledger.")
    args = parser.parse_args()
    try:
        status = main(args.run_id)
    except FileExistsError:
        print("Quality run already has a ledger; refusing a repeat pass.")
        status = 1
    except Exception:
        print("Quality run unavailable. No automatic replay; inspect configuration and private ledger.")
        status = 1
    raise SystemExit(status)
