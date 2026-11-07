"""Packaged Java + local synthetic organizer HTTP smoke. Never contacts the real organizer.

--serve keeps the verified temporary app alive for browser checks until Enter is pressed.
"""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
JAR = ROOT / "server/target/freedom-cqa-server-0.1.0.jar"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    fixture = json.loads((ROOT / "contracts/fixtures/positive/evaluation_request.json").read_text())
    turns = [{k: v for k, v in m.items() if k != "id"} for m in fixture["conversation"]["messages"]]

    def dataset(group):
        records = []
        for language in ("RU", "KZ", "EN"):
            records.append({"conversation_id": language, "channel": "agent chat", "language": language,
                            "transcript": copy.deepcopy(turns), "audio_url": None})
        return {"error": "", "isSuccess": True, "data": {"dataset_group_id": group, "total_records": 3, "records": records}}

    class Upstream(BaseHTTPRequestHandler):
        requests = []
        conflict = False

        def log_message(self, *_):
            pass

        def do_GET(self):
            query = urlsplit(self.path).query
            assert query.startswith("sig=SYNTHETIC%2B%2f%3D&sp=%2fraw&group_id=")
            group = parse_qs(query)["group_id"][0]
            Upstream.requests.append(group)
            if group == "SLOW":
                time.sleep(4)  # Exposes a visible loading state for the browser check.
            status = 403 if group == "DENIED" else 200
            body = dataset("OTHER" if group == "MISMATCH" else group)
            if group == "DEV" and Upstream.conflict:
                body = dataset("DEV")
                body["data"]["records"][0]["conversation_id"] = "NEW"
                body["data"]["records"][2]["transcript"][0]["text"] = "Synthetic changed source"
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    worker = threading.Thread(target=upstream.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="cqa-t07-smoke-") as temporary:
            directory = Path(temporary)
            database = directory / "storage.sqlite"
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            process = None
            log = (directory / "java.log").open("wb")
            environment = {**os.environ, "CQA_ORGANIZER_URL":
                f"http://127.0.0.1:{upstream.server_port}/signed?sig=SYNTHETIC%2B%2f%3D&sp=%2fraw&group_id=OLD"}

            def http(method, route, body=None, expected=200):
                request = Request(base + route, data=json.dumps(body).encode() if body is not None else None, method=method)
                if body is not None:
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
                process = subprocess.Popen(["java", "-jar", str(JAR), f"--server.port={port}",
                    f"--cqa.db-path={database}", "--spring.main.banner-mode=off", "--logging.level.root=WARN"],
                    env=environment, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
                for _ in range(300):
                    assert process.poll() is None, "Java child exited"
                    try:
                        if http("GET", "/api/health")["status"] == "ok":
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
                        process.kill()
                        process.wait(timeout=5)
                    process = None

            def rows():
                with sqlite3.connect(database) as connection:
                    return connection.execute("SELECT * FROM conversations ORDER BY id").fetchall()

            try:
                start(directory)
                for group in ("DEV", "DEV", "CONTROL"):
                    assert http("POST", "/api/datasets/fetch", {"group_id": group})["imported_records"] == 3
                assert Upstream.requests == ["DEV", "DEV", "CONTROL"]
                assert len(http("GET", "/api/conversations")) == 6
                for group in ("DEV", "CONTROL"):
                    for record in dataset(group)["data"]["records"]:
                        saved = http("GET", "/api/conversations/" + group + ":" + record["conversation_id"])
                        assert saved["transcript"] == record["transcript"]
                        assert saved["messages"] == [{"id": f"m{i:04d}", **turn} for i, turn in enumerate(turns, 1)]
                before = rows()
                assert http("POST", "/api/datasets/fetch", {"group_id": "DENIED"}, 502)["detail"]["code"] == "ORGANIZER_ACCESS_DENIED"
                assert http("POST", "/api/datasets/fetch", {"group_id": "MISMATCH"}, 502)["detail"]["code"] == "ORGANIZER_GROUP_MISMATCH"
                http("POST", "/api/datasets/import", dataset("DEV"))
                conflict = dataset("DEV")
                conflict["data"]["records"][0]["conversation_id"] = "NEW"
                conflict["data"]["records"][2]["transcript"][0]["text"] = "Synthetic changed source"
                assert http("POST", "/api/datasets/import", conflict, 409)["detail"]["code"] == "VERSION_CONFLICT"
                Upstream.conflict = True
                try:
                    assert http("POST", "/api/datasets/fetch", {"group_id": "DEV"}, 409)["detail"]["code"] == "VERSION_CONFLICT"
                finally:
                    Upstream.conflict = False
                assert rows() == before
                stop()
                other = directory / "other-cwd"
                other.mkdir()
                start(other)
                assert rows() == before
                http("POST", "/api/datasets/fetch", {"group_id": "DEV"})
                assert rows() == before
                print("PASS: packaged Java -> synthetic GET upstream; raw signature query preserved; 6 unique conversations (DEV3/CONTROL3).", flush=True)
                print("PASS: repeated fetch/upload idempotency, exact source/message IDs, safe403/mismatch, atomic conflict, SQLite process restart.", flush=True)
                print("REAL ORGANIZER GET: NOT RUN. No real data, provider calls or user SQLite used.", flush=True)
                if args.serve:
                    print("BROWSER_URL=" + base, flush=True)
                    input("Press Enter after browser verification to stop only these test processes.\n")
                log.flush()
                assert b"SYNTHETIC%2B" not in (directory / "java.log").read_bytes()
            finally:
                stop()
                log.close()
    finally:
        upstream.shutdown()
        upstream.server_close()
        worker.join(timeout=3)


if __name__ == "__main__":
    main()
