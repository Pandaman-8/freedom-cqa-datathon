"""One explicit synthetic KZ HTTP probe, at most ONE upstream attempt, no replay.

Run from repository root: PYTHONPATH=ml-service <venv>/bin/python ml-service/scripts/live_once.py
Loads the private .env, requires confirmed Free Plan, never prints model text or secrets.
Starts a temporary localhost server on a free port; leaves an existing :8001 untouched.
"""

import asyncio
import json
import socket
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from dotenv import load_dotenv


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env", override=False)
    from app.config import Settings
    from app.errors import ServiceError
    from app.main import create_app
    from app.validation import strict_loads, validate_context, validate_shape

    settings = Settings.from_env()
    settings.check()
    if settings.model != "openai/gpt-oss-20b":
        raise SystemExit("Probe requires the explicitly requested openai/gpt-oss-20b model.")
    payload = strict_loads((root / "tests/fixtures/kz_public_na/request.json").read_bytes())
    payload["request_id"] = str(uuid4())
    app = create_app(settings, max_attempts=1)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0,
                                         access_log=False, log_level="warning"))

    class OneCallGuard:
        def __init__(self, delegate):
            self.delegate = delegate
            self.calls = 0

        async def complete(self, messages):
            if self.calls:
                raise ServiceError("EVALUATOR_PROVIDER_ERROR")
            self.calls += 1
            return await self.delegate.complete(messages)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        thread = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[sock])), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise SystemExit("Temporary local server failed to start; no POST sent.")
                time.sleep(0.05)
            guard = OneCallGuard(app.state.evaluator.provider)
            app.state.evaluator.provider = guard
            with httpx.Client(timeout=70, trust_env=False, follow_redirects=False) as client:
                # Exactly one local POST. HTTPTransport has retries=0 by default.
                response = client.post(f"http://127.0.0.1:{port}/v1/evaluate", json=payload)
            result = strict_loads(response.content)
            summary = {"http_status": response.status_code, "provider_attempts": guard.calls,
                       "contract_version": "2.0.0", "model": settings.model}
            if response.status_code == 200:
                validate_shape("evaluation_result", result)
                validate_context("evaluation_result", result, payload)
                summary.update(answers=len(result["answers"]), validated=True,
                               input_tokens=result["diagnostics"]["input_tokens"],
                               output_tokens=result["diagnostics"]["output_tokens"],
                               estimated_cost_usd=result["diagnostics"]["estimated_cost_usd"])
            else:
                validate_shape("error", result)
                validate_context("error", result, payload, http_status=response.status_code)
                summary["code"] = result["detail"]["code"]
            print(json.dumps(summary))
            return 0 if response.status_code == 200 else 1
        finally:
            server.should_exit = True
            thread.join(timeout=5)


if __name__ == "__main__":
    try:
        status = main()
    except Exception:
        # Unknown outcomes must never trigger an automatic replay or raw exception dump.
        print("Probe stopped; outcome may be unknown. No automatic retry. See safe local diagnostics.")
        status = 1
    raise SystemExit(status)
