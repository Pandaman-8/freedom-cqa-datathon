"""Explicit local-service smoke on the six bundled own synthetic cases.

The local service uses the real provider. No fallback; no raw prompts/responses logged.
Run only after confirming the Groq Free Plan. Each case can consume two calls.
"""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="Fixture directory name; default runs all six.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "tests/fixtures"
    paths = sorted(root.glob("*/request.json"))
    if args.case:
        paths = [p for p in paths if p.parent.name == args.case]
    if not paths:
        parser.error("Unknown case")
    failed = False
    with httpx.Client(base_url="http://127.0.0.1:8001", timeout=70, trust_env=False) as client:
        try:
            health = client.get("/health")
        except httpx.HTTPError:
            raise SystemExit("Local ML service is unavailable; no evaluation sent.") from None
        if health.status_code != 200:
            raise SystemExit("ML service is not ready. Check configuration using GET /health.")
        for path in paths:
            request = json.loads(path.read_text(encoding="utf-8"))
            request["request_id"] = str(uuid4())
            expected = json.loads(path.with_name("expected.json").read_text(encoding="utf-8"))
            try:
                response = client.post("/v1/evaluate", json=request)
            except httpx.HTTPError:
                # Do not replay unknown outcomes. Java will own the persisted request ledger.
                raise SystemExit(f"Unknown outcome for request {request['request_id']}; no automatic retry.") from None
            body = response.json()
            if response.status_code != 200:
                print(json.dumps({"case": path.parent.name, "status": response.status_code,
                                  "request_id": request["request_id"], "code": body["detail"]["code"]}))
                failed = True
                break
            actual = {a["criterion_id"]: (a["answer"], a["value"]) for a in body["answers"]}
            matched = sum(actual.get(a["criterion_id"]) == (a["answer"], a["value"]) for a in expected["answers"])
            print(json.dumps({"case": path.parent.name, "request_id": request["request_id"],
                              "proposed_labels_matched": matched, "criteria": len(expected["answers"]),
                              "diagnostics": body["diagnostics"]}, ensure_ascii=True))
            failed |= matched != len(expected["answers"])
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
