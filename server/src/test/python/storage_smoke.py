"""Local T05 smoke; synthetic by default, explicit private dataset optional.

Runs only a child Java process on loopback against an isolated temporary database.
Never prints transcripts, identifiers, audio URLs, response bodies or server logs.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[4]
JAR = ROOT / "server/target/freedom-cqa-server-0.1.0.jar"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path)
    args = parser.parse_args()
    dataset_path = args.dataset.resolve() if args.dataset else None
    if dataset_path and not dataset_path.is_file():
        raise SystemExit("Dataset file absent; DEV smoke not run.")
    with zipfile.ZipFile(JAR) as jar:
        assert jar.read("BOOT-INF/classes/db/seed/chat_quality.json") == (ROOT / "backend/app/seed/chat_quality.json").read_bytes()
    with tempfile.TemporaryDirectory(prefix="cqa-t05-smoke-") as private:
        directory = Path(private)  # tempfile creates mode 0700.
        database = directory / "storage/cqa.sqlite"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        process = None
        log = (directory / "java.log").open("wb")

        def http(method, route, body=None, expected=200, raw=False):
            payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode() if body is not None else None
            req = Request(base + route, data=payload, method=method)
            if payload is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urlopen(req, timeout=20) as response:
                    status, content = response.status, response.read()
            except HTTPError as error:
                status, content = error.code, error.read()
            assert status == expected, f"Unexpected HTTP status: {status}; expected {expected}"
            return content if raw else json.loads(content)

        def start(cwd):
            nonlocal process
            process = subprocess.Popen(
                ["java", "-jar", str(JAR), f"--server.port={port}", f"--cqa.db-path={database}",
                 "--cqa.ml-url=", "--spring.main.banner-mode=off", "--logging.level.root=WARN"],
                cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(150):
                assert process.poll() is None, "Java process exited during startup"
                try:
                    assert http("GET", "/api/health")["service"] == "freedom-cqa-java"
                    return
                except (URLError, ConnectionError):
                    time.sleep(0.1)
            raise AssertionError("Java startup deadline exceeded")

        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()  # Only the child created here, never an unrelated process.
                    process.wait(timeout=5)
                process = None

        try:
            start(directory)
            assert b"Freedom CQA" in http("GET", "/", raw=True)
            assert b"fetch('/api/health'" in http("GET", "/js/app.js", raw=True)
            assert b"@media" in http("GET", "/styles.css", raw=True)
            seed = http("GET", "/api/checklists/chat-quality?version=1")
            request = json.loads((ROOT / "contracts/fixtures/positive/evaluation_request.json").read_text())
            answers = json.loads((ROOT / "contracts/fixtures/positive/provider_output.json").read_text())["answers"]
            checklist = request["checklist"]
            draft = {k: v for k, v in checklist.items() if k not in ("key", "version")}
            http("POST", "/api/checklists/synthetic-smoke", draft)
            source = request["conversation"]
            transcript = [{k: v for k, v in m.items() if k != "id"} for m in source["messages"]]
            synthetic = {"error": "", "isSuccess": True, "data": {"dataset_group_id": "SYNTHETIC-SMOKE",
                "total_records": 1, "records": [{"conversation_id": "example", "channel": "agent chat", "language": "EN",
                                                 "transcript": transcript, "audio_url": None}]}}
            http("POST", "/api/datasets/import", synthetic)
            http("POST", "/api/datasets/import", synthetic)
            manual = {"conversation_id": "SYNTHETIC-SMOKE:example", "checklist_key": "synthetic-smoke",
                      "checklist_version": 1, "answers": answers}
            saved = http("POST", "/api/evaluations/manual", manual, expected=201)
            assert saved["original_score"]["overall_score"] == 100
            assert saved["scoring_version"] == "cqa-score/1"
            updated = http("PUT", "/api/checklists/synthetic-smoke?expected_version=1", {**draft, "title": "Updated synthetic rubric"})
            assert updated["version"] == 2
            http("PUT", "/api/checklists/synthetic-smoke?expected_version=1", draft, expected=409)
            assert http("GET", "/api/checklists/synthetic-smoke?version=1")["title"] == draft["title"]
            assert http("GET", "/api/evaluations/" + saved["id"]) == saved
            auto = {k: v for k, v in manual.items() if k != "answers"}
            auto["request_id"] = str(uuid.uuid4())
            error = http("POST", "/api/evaluations/auto", auto, expected=501)
            assert error["detail"]["code"] == "EVALUATOR_UNCONFIGURED"
            assert error["detail"]["request_id"] == auto["request_id"]
            assert len(http("GET", "/api/evaluations")) == 1
            totals = None
            dataset = None
            if dataset_path:
                body = dataset_path.read_bytes()
                dataset = json.loads(body)["data"]
                records = dataset["records"]
                totals = dict(conversations=len(records), messages=sum(len(r["transcript"]) for r in records),
                              languages=dict(Counter(r["language"] for r in records)),
                              channels=dict(Counter(r["channel"] for r in records)))
                assert totals == {"conversations": 65, "messages": 1268,
                                  "languages": {"RU": 35, "KZ": 15, "EN": 15},
                                  "channels": {"agent chat": 60, "voice call": 5}}, "Unexpected DEV aggregate counts"
                for _ in range(2):
                    imported = http("POST", "/api/datasets/import", body)
                    assert imported["imported_records"] == 65

            def verify_sources():
                listed = http("GET", "/api/conversations")
                assert len(listed) == (66 if dataset else 1), "Duplicate/missing conversation rows"
                if dataset:
                    selected = [r for r in listed if r["dataset_group_id"] == dataset["dataset_group_id"]]
                    assert len(selected) == 65
                    for record in dataset["records"]:
                        identity = dataset["dataset_group_id"] + ":" + record["conversation_id"]
                        stored = http("GET", "/api/conversations/" + quote(identity, safe=""))
                        for field in ("conversation_id", "language", "channel", "transcript"):
                            assert stored[field] == record[field], "Source field preservation failed"
                        assert stored["audio_url"] == record.get("audio_url"), "Audio reference preservation failed"
                        assert stored["messages"] == [{"id": f"m{i:04d}", **turn} for i, turn in enumerate(record["transcript"], 1)], "Message preservation failed"

            verify_sources()
            stop()
            other_cwd = directory / "different-working-directory"
            other_cwd.mkdir()
            start(other_cwd)
            verify_sources()
            assert http("GET", "/api/checklists/chat-quality?version=1") == seed
            assert http("GET", "/api/checklists/synthetic-smoke")["version"] == 2
            assert http("GET", "/api/evaluations/" + saved["id"]) == saved
            assert len(http("GET", "/api/evaluations?conversation_id=SYNTHETIC-SMOKE:example")) == 1
            assert database.is_file()
            print("PASS: packaged JAR, unchanged packaged seed, health/static, synthetic GET/POST/PUT/manual/501.")
            print("PASS: source/checklist/evaluation persistence after process restart from a different working directory.")
            if totals:
                print("PASS: local DEV import, exact GET preservation and idempotency before/after restart; " + json.dumps(totals, sort_keys=True))
            else:
                print("DEV: not run (no --dataset supplied).")
            print("PASS: isolated temporary DB; own Java child stopped; no external HTTP/ML calls.")
        finally:
            stop()
            log.close()


if __name__ == "__main__":
    main()
