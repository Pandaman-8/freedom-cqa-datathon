import asyncio
import json
from contextlib import asynccontextmanager
from email.message import Message

import httpx
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from .config import Settings, fingerprint, synthetic_fingerprints
from .admission import ApprovedDatasetAdmission, ADMISSION_PROTOCOL
from .errors import ServiceError
from .evaluator import Evaluator
from .provider import GroqProvider
from .validation import Invalid, request_id_of, strict_loads, validate_context, validate_shape

REQUEST_LIMIT = 1024 * 1024


def create_app(settings=None, provider=None, *, max_attempts=2):
    settings = settings or Settings.from_env()
    gate = asyncio.Lock()
    approved = synthetic_fingerprints()
    admission = ApprovedDatasetAdmission(settings)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                     transport=httpx.AsyncHTTPTransport(retries=0)) as client:
            app.state.evaluator = Evaluator(settings, provider or GroqProvider(settings, client),
                                            max_attempts=max_attempts)
            yield

    app = FastAPI(title="Freedom CQA ML", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)

    def error_response(error, request_id):
        payload = error.envelope(request_id)
        validate_shape("error", payload)
        validate_context("error", payload, http_status=error.status)
        return JSONResponse(payload, status_code=error.status)

    @app.get("/health")
    async def health():
        # Readiness is configuration-only; it does not prove credentials/quota/provider availability.
        fields = {"admission_protocol": ADMISSION_PROTOCOL, "admission_mode": settings.data_policy,
                  "admission_sha256": None, "admission_provider": "groq",
                  "admission_model": settings.model}
        try:
            settings.check()
            if settings.data_policy == "approved_dataset":
                fields.update(admission.health_fields())
        except ServiceError as exc:
            code = exc.code
        else:
            code = "EVALUATOR_BUSY" if gate.locked() else None
        return JSONResponse({"configured": code not in ("EVALUATOR_UNCONFIGURED", "PRIVACY_POLICY_UNCONFIGURED"),
                             "ready": code is None, "model": settings.model, "contract_version": "2.0.0",
                             "reason": code, **fields}, status_code=200 if code is None else 503)

    @app.post("/v1/evaluate")
    async def evaluate(request: Request):
        request_id = None
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > REQUEST_LIMIT:
                    raise ServiceError("PAYLOAD_TOO_LARGE")
            payload = strict_loads(bytes(raw))
            request_id = request_id_of(payload)
            content_type = Message()
            content_type["content-type"] = request.headers.get("content-type", "")
            parameters = (content_type.get_params() or [])[1:]
            if (content_type.get_content_type() != "application/json" or len(parameters) > 1
                    or any(name != "charset" or not isinstance(value, str) or value.lower() != "utf-8"
                           for name, value in parameters)):
                raise ServiceError("INVALID_INPUT")
            if isinstance(payload, dict) and "contract_version" in payload and payload["contract_version"] != "2.0.0":
                raise ServiceError("UNSUPPORTED_CONTRACT")
            validate_shape("evaluation_request", payload)
            validate_context("evaluation_request", payload)
            if not any(m["text"].strip() for m in payload["conversation"]["messages"]):
                raise ServiceError("INVALID_INPUT")
            settings.check()
            first_grant_sha = None
            confirmed = request.headers.get("x-cqa-rubric-confirmed")
            if settings.data_policy == "synthetic_only":
                if fingerprint(payload["conversation"]) not in approved:
                    raise ServiceError("PRIVACY_POLICY_UNCONFIGURED")
            else:
                first_grant_sha = admission.authorize(payload, confirmed=confirmed).sha256
            if gate.locked():
                raise ServiceError("EVALUATOR_BUSY", retryable=True)
            async with gate:
                before = None
                if first_grant_sha is not None:
                    def before():
                        # Also recheck immediately before EACH provider attempt.
                        admission.authorize(payload, confirmed=confirmed,
                                            expected_sha256=first_grant_sha)
                result = await app.state.evaluator.evaluate(payload, before_provider_call=before)
            # ASCII JSON keeps original Unicode values exact, including escaped surrogate data.
            return Response(json.dumps(result, ensure_ascii=True, allow_nan=False), media_type="application/json")
        except Invalid:
            return error_response(ServiceError("INVALID_INPUT"), request_id)
        except ServiceError as exc:
            return error_response(exc, request_id)
        except Exception:
            # No exception text or customer/provider input in logs or HTTP output.
            return error_response(ServiceError("EVALUATOR_PROVIDER_ERROR"), request_id)

    return app


app = create_app()
