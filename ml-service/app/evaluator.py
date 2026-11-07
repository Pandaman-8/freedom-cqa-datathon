import asyncio
import copy
import json
import time

from .errors import ServiceError
from .debug import report_failure
from .prompt import PROMPT_VERSION, build_messages
from .provider import RESPONSE_LIMIT
from .validation import Invalid, strict_loads, validate_context, validate_shape

ATTEMPT_SECONDS = 30.0
TOTAL_SECONDS = 65.0
MAX_BACKOFF = 2.0


class Evaluator:
    def __init__(self, settings, provider, *, max_attempts=2):
        if type(max_attempts) is not int or max_attempts not in (1, 2):
            raise ValueError("max_attempts must be 1 or 2")
        self.settings = settings
        self.provider = provider
        self.max_attempts = max_attempts

    async def evaluate(self, request):
        # Pin the full input before the first await; no latest/checklist reload on save.
        start = time.monotonic()
        pinned = copy.deepcopy(request)
        try:
            async with asyncio.timeout(TOTAL_SECONDS):
                return await self._run(pinned, start)
        except TimeoutError:
            raise ServiceError("EVALUATOR_TIMEOUT", retryable=True) from None

    async def _run(self, request, start):
        input_tokens = output_tokens = 0
        feedback = None
        for attempt in range(1, self.max_attempts + 1):
            reply = None
            messages = build_messages(request, feedback)
            self._check_deadline(start)
            attempt_start = time.monotonic()
            try:
                async with asyncio.timeout(ATTEMPT_SECONDS):
                    reply = await self.provider.complete(messages)
            except TimeoutError:
                failure = ServiceError("EVALUATOR_TIMEOUT", retryable=True)
            except ServiceError as exc:
                failure = exc
            else:
                # asyncio timers require a loop yield. A late return must not become success.
                failure = (ServiceError("EVALUATOR_TIMEOUT", retryable=True)
                           if time.monotonic() - attempt_start >= ATTEMPT_SECONDS else None)
            self._check_deadline(start)

            # Missing usage on ANY attempt makes the aggregate unknown, never zero.
            in_count = reply.input_tokens if reply else None
            out_count = reply.output_tokens if reply else None
            input_tokens = None if input_tokens is None or in_count is None else input_tokens + in_count
            output_tokens = None if output_tokens is None or out_count is None else output_tokens + out_count

            if reply is not None and failure is None:
                try:
                    if reply.invalid_reason or reply.content is None:
                        raise Invalid(reply.invalid_reason or "PROVIDER_CONTENT")
                    if reply.model != self.settings.model:
                        raise Invalid("PROVIDER_MODEL")
                    output = strict_loads(reply.content)
                    validate_shape("provider_output", output)
                    validate_context("provider_output", output, request)
                    self._check_deadline(start)
                    warnings = ["DOMAIN_FACT_UNVERIFIED"]  # No external company KB is supplied.
                    if request["conversation"]["channel"] == "voice call":
                        warnings.append("AUDIO_NOT_ASSESSED")
                    result = {
                        "contract_version": request["contract_version"], "request_id": request["request_id"],
                        "conversation_id": request["conversation"]["id"],
                        "checklist_key": request["checklist"]["key"],
                        "checklist_version": request["checklist"]["version"], "answers": output["answers"],
                        "diagnostics": {
                            "provider": "groq", "model": reply.model, "prompt_version": PROMPT_VERSION,
                            "attempt_count": attempt, "input_tokens": input_tokens, "output_tokens": output_tokens,
                            # This service only enables a confirmed free organization; no paid mode.
                            "estimated_cost_usd": 0.0 if self.settings.free_plan_confirmed
                            and input_tokens is not None and output_tokens is not None else None,
                            "latency_ms": int((time.monotonic() - start) * 1000), "warnings": warnings,
                        },
                    }
                    validate_shape("evaluation_result", result)
                    validate_context("evaluation_result", result, request)
                    if len(json.dumps(result, ensure_ascii=True).encode()) > RESPONSE_LIMIT:
                        raise Invalid("RESULT_TOO_LARGE")
                    self._check_deadline(start)
                    result["diagnostics"]["latency_ms"] = int((time.monotonic() - start) * 1000)
                    return result
                except Invalid as exc:
                    failure = ServiceError("EVALUATOR_INVALID_OUTPUT", retryable=True, diagnostic=exc)

            self._check_deadline(start)
            if failure.code == "EVALUATOR_INVALID_OUTPUT":
                feedback = report_failure(failure.diagnostic or Invalid("PROVIDER_COMPLETION_INVALID"),
                                          request, attempt)
            if not failure.retryable or attempt == self.max_attempts:
                raise failure
            delay = failure.retry_after if failure.retry_after is not None else 0.25
            remaining = TOTAL_SECONDS - (time.monotonic() - start)
            # Do not shorten Retry-After or wait beyond the agreed backoff/deadline budget.
            if delay > MAX_BACKOFF or delay + ATTEMPT_SECONDS > remaining:
                raise failure
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _check_deadline(start):
        if time.monotonic() - start >= TOTAL_SECONDS:
            raise ServiceError("EVALUATOR_TIMEOUT", retryable=True)
