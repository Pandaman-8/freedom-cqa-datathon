"""T06 packaged-JAR smoke: synthetic data, temporary SQLite, own child process only."""
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[4]
JAR = ROOT / "server/target/freedom-cqa-server-0.1.0.jar"


def main():
    with tempfile.TemporaryDirectory(prefix="cqa-t06-smoke-") as temporary:
        directory = Path(temporary)
        database = directory / "storage/review.sqlite"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        process = None
        log = (directory / "java.log").open("wb")

        def http(method, route, body=None, expected=200):
            payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
            request = Request(base + route, data=payload, method=method)
            if payload is not None:
                request.add_header("Content-Type", "application/json")
            try:
                with urlopen(request, timeout=20) as response:
                    status, content = response.status, response.read()
            except HTTPError as error:
                status, content = error.code, error.read()
            assert status == expected, f"HTTP {status}, expected {expected}"
            return json.loads(content)

        def start(cwd):
            nonlocal process
            process = subprocess.Popen(
                ["java", "-jar", str(JAR), f"--server.port={port}", f"--cqa.db-path={database}",
                 "--spring.main.banner-mode=off", "--logging.level.root=WARN"],
                cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(300):
                assert process.poll() is None, "Child Java process exited during startup"
                try:
                    assert http("GET", "/api/health")["service"] == "freedom-cqa-java"
                    return
                except (URLError, ConnectionError):
                    time.sleep(0.1)
            raise AssertionError("Startup deadline exceeded")

        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process = None

        def snapshots():
            with sqlite3.connect(database) as connection:
                return (connection.execute("SELECT * FROM evaluations ORDER BY id").fetchall(),
                        connection.execute("SELECT * FROM conversations ORDER BY id").fetchall())

        try:
            start(directory)
            fixture = json.loads((ROOT / "contracts/fixtures/positive/evaluation_request.json").read_text())
            answers = json.loads((ROOT / "contracts/fixtures/positive/provider_output.json").read_text())["answers"]
            draft = {k: v for k, v in fixture["checklist"].items() if k not in ("key", "version")}
            http("POST", "/api/checklists/synthetic-review", draft)
            transcript = [{k: v for k, v in m.items() if k != "id"} for m in fixture["conversation"]["messages"]]
            http("POST", "/api/datasets/import", {"error": "", "isSuccess": True, "data": {
                "dataset_group_id": "SYNTHETIC-REVIEW", "total_records": 1, "records": [{
                    "conversation_id": "example", "channel": "agent chat", "language": "EN", "audio_url": None,
                    "transcript": transcript}]}})
            manual = {"conversation_id": "SYNTHETIC-REVIEW:example", "checklist_key": "synthetic-review",
                      "checklist_version": 1, "answers": answers}
            original = http("POST", "/api/evaluations/manual", manual, 201)
            route = "/api/evaluations/" + original["id"]
            assert original["original_score"]["overall_score"] == 100
            before = snapshots()
            appeal_body = {"criterion_id": "S_CLARITY", "comment": "Synthetic review request."}
            appeal = http("POST", route + "/appeals", appeal_body, 201)
            opened = http("GET", route)
            assert opened["review_status"] == "appealed" and opened["review_revision"] == 1
            assert opened["final_score"] == original["original_score"]
            duplicate = http("POST", route + "/appeals", appeal_body, 409)
            assert duplicate["detail"]["code"] == "REVIEW_CONFLICT"
            replacement = {**answers[1], "value": 7, "explanation": "Synthetic changed clarity assessment."}
            decision = {"decision": "change", "reason": "Synthetic review reason.", "replacement": replacement}
            resolve = "/api/appeals/" + appeal["id"] + "/resolve"
            assert http("POST", resolve + "?expected_revision=0", decision, 409)["detail"]["code"] == "REVIEW_CONFLICT"
            changed = http("POST", resolve + "?expected_revision=1", decision)
            assert changed["review_status"] == "reviewed" and changed["review_revision"] == 2
            assert changed["final_score"]["overall_score"] == 77.5
            assert changed["original_answers"] == original["original_answers"]
            assert changed["original_score"] == original["original_score"]
            assert changed["appeals"][0]["replacement"] == replacement
            assert snapshots() == before
            draft["criteria"][1]["id"] = "S_REPLACED_IN_V2"
            draft["criteria"][1]["weight"] = 50
            assert http("PUT", "/api/checklists/synthetic-review?expected_version=1", draft)["version"] == 2
            assert http("GET", route) == changed and changed["checklist_version"] == 1
            assert http("GET", "/api/evaluations") == [changed]
            auto = {k: v for k, v in manual.items() if k != "answers"}
            auto["request_id"] = str(uuid.uuid4())
            assert http("POST", "/api/evaluations/auto", auto, 501)["detail"]["code"] == "EVALUATOR_UNCONFIGURED"
            stop()
            other = directory / "different-cwd"
            other.mkdir()
            start(other)
            assert http("GET", route) == changed and snapshots() == before
            assert http("GET", "/api/evaluations?conversation_id=SYNTHETIC-REVIEW:example") == [changed]
            assert http("POST", resolve + "?expected_revision=2", decision, 409)["detail"]["code"] == "REVIEW_CONFLICT"
            repeated = http("POST", route + "/appeals", appeal_body, 201)
            confirmed = http("POST", "/api/appeals/" + repeated["id"] + "/resolve?expected_revision=3",
                             {"decision": "confirm", "reason": "Synthetic confirmation of current answer."})
            assert confirmed["final_answers"] == changed["final_answers"]
            assert confirmed["final_score"] == changed["final_score"]
            assert len(confirmed["appeals"]) == 2 and confirmed["review_revision"] == 4
            assert snapshots() == before
            print("PASS: real packaged-JAR HTTP import/manual/create/change/list/detail; score 100 -> 77.50.")
            print("PASS: byte-identical SQLite originals and sources; pinned v1 despite changed v2; auto501.")
            print("PASS: child-process restart, persistent history/final, duplicate/stale/double resolve409, re-appeal confirm.")
            print("PASS: synthetic data only; temporary DB/free loopback port; no external HTTP or ML calls.")
        finally:
            stop()
            log.close()


if __name__ == "__main__":
    main()
