"""Real Groq HTTP adapter. No SDK or transport-level automatic POST retries."""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from .errors import ServiceError
from .structured_output import groq_response_format
from .validation import Invalid, strict_loads

PROVIDER_URL = "https://api.groq.com/openai/v1/chat/completions"
RESPONSE_LIMIT = 256 * 1024


def retry_after_seconds(value):
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def token_count(value):
    return value if type(value) is int and value >= 0 else None


@dataclass(frozen=True)
class ProviderReply:
    content: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    invalid_reason: str | None = None


class GroqProvider:
    def __init__(self, settings, client):
        self.settings = settings
        self.client = client

    async def complete(self, messages):
        body = {"model": self.settings.model, "messages": messages,
                "response_format": groq_response_format(),
                "include_reasoning": False, "reasoning_effort": "low",
                "temperature": 0, "max_completion_tokens": 4096, "stream": False}
        try:
            async with self.client.stream(
                "POST", PROVIDER_URL,
                headers={"Authorization": f"Bearer {self.settings.api_key}"}, json=body,
                timeout=httpx.Timeout(30.0, connect=5.0),
            ) as response:
                # Never follow redirects carrying credentials. No raw body in errors/logs.
                if response.status_code in (401, 403):
                    raise ServiceError("EVALUATOR_AUTH")
                if response.status_code == 429:
                    raise ServiceError("EVALUATOR_RATE_LIMITED", retryable=True,
                                       retry_after=retry_after_seconds(response.headers.get("retry-after")))
                if response.status_code >= 500:
                    raise ServiceError("EVALUATOR_PROVIDER_ERROR", retryable=True,
                                       retry_after=retry_after_seconds(response.headers.get("retry-after")))
                if response.status_code == 413:
                    raise ServiceError("INPUT_TOO_LARGE")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > RESPONSE_LIMIT:
                        if response.status_code != 200:
                            raise ServiceError("EVALUATOR_PROVIDER_ERROR")
                        raise ServiceError("EVALUATOR_INVALID_OUTPUT", retryable=True,
                                           diagnostic=Invalid("PROVIDER_RESPONSE_TOO_LARGE"))
                try:
                    data = strict_loads(bytes(raw))
                except Invalid:
                    if response.status_code != 200:
                        raise ServiceError("EVALUATOR_PROVIDER_ERROR") from None
                    raise ServiceError("EVALUATOR_INVALID_OUTPUT", retryable=True,
                                       diagnostic=Invalid("PROVIDER_JSON")) from None
                if response.status_code != 200:
                    error = data.get("error") if isinstance(data, dict) else None
                    code = error.get("code") if isinstance(error, dict) else None
                    if code in ("context_length_exceeded", "context_window_exceeded"):
                        raise ServiceError("INPUT_TOO_LARGE")
                    if code == "json_validate_failed":
                        raise ServiceError("EVALUATOR_INVALID_OUTPUT", retryable=True,
                                           diagnostic=Invalid("PROVIDER_SCHEMA_REJECTED"))
                    raise ServiceError("EVALUATOR_PROVIDER_ERROR")
                if not isinstance(data, dict):
                    raise ServiceError("EVALUATOR_INVALID_OUTPUT", retryable=True,
                                       diagnostic=Invalid("PROVIDER_ENVELOPE"))
                usage = data.get("usage")
                usage = usage if isinstance(usage, dict) else {}
                content = None
                invalid_reason = "PROVIDER_CHOICES"
                choices = data.get("choices")
                if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict):
                    choice = choices[0]
                    message = choice.get("message")
                    if choice.get("finish_reason") == "length":
                        invalid_reason = "PROVIDER_TRUNCATED"
                    elif isinstance(message, dict) and message.get("refusal"):
                        invalid_reason = "PROVIDER_REFUSAL"
                    elif choice.get("finish_reason") != "stop":
                        invalid_reason = "PROVIDER_FINISH"
                    elif not isinstance(message, dict) or not isinstance(message.get("content"), str):
                        invalid_reason = "PROVIDER_CONTENT"
                    else:
                        content = message["content"]
                        invalid_reason = None
                return ProviderReply(content, data.get("model"), token_count(usage.get("prompt_tokens")),
                                     token_count(usage.get("completion_tokens")), invalid_reason)
        except httpx.TimeoutException:
            raise ServiceError("EVALUATOR_TIMEOUT", retryable=True) from None
        except httpx.TransportError:
            raise ServiceError("EVALUATOR_PROVIDER_ERROR", retryable=True) from None
