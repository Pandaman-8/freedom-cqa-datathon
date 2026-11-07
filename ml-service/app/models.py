"""Strict typed views; published Draft 2020-12 schemas remain authoritative."""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict


def json_integer(value):
    # JSON Schema integers include 2.0, but never strings or booleans.
    if type(value) is float and value.is_integer():
        return int(value)
    return value


Integer = Annotated[int, BeforeValidator(json_integer)]
Number = int | float


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class Message(StrictModel):
    id: str
    timestamp: str
    speaker: Literal["operator", "client", "bot", "system"]
    text: str


class Conversation(StrictModel):
    id: str
    dataset_group_id: str
    conversation_id: str
    channel: Literal["agent chat", "voice call"]
    language: Literal["RU", "KZ", "EN"]
    messages: list[Message]


class Section(StrictModel):
    id: str
    title: str


class Level(StrictModel):
    value: Number
    description: str


class Criterion(StrictModel):
    id: str
    section_id: str
    title: str
    instruction: str
    kind: Literal["binary", "scale", "flag"]
    weight: Number
    allow_na: bool
    na_rule: str | None
    levels: list[Level]


class Checklist(StrictModel):
    key: str
    version: Integer
    title: str
    description: str
    sections: list[Section]
    criteria: list[Criterion]


class EvaluationRequest(StrictModel):
    contract_version: Literal["2.0.0"]
    request_id: str
    conversation: Conversation
    checklist: Checklist


class Evidence(StrictModel):
    message_id: str
    quote: str


class Answer(StrictModel):
    criterion_id: str
    answer: Literal["yes", "no", "na", "scale"]
    value: Number | None
    explanation: str
    evidence: list[Evidence]


class ProviderOutput(StrictModel):
    answers: list[Answer]


class Diagnostics(StrictModel):
    provider: str
    model: str
    prompt_version: str
    attempt_count: Integer
    input_tokens: Integer | None
    output_tokens: Integer | None
    estimated_cost_usd: Number | None
    latency_ms: Integer | None
    warnings: list[Literal["DOMAIN_FACT_UNVERIFIED", "TRANSCRIPTION_AMBIGUOUS",
                           "AUDIO_NOT_ASSESSED", "MODEL_UNCERTAINTY"]]


class EvaluationResult(ProviderOutput):
    contract_version: Literal["2.0.0"]
    request_id: str
    conversation_id: str
    checklist_key: str
    checklist_version: Integer
    diagnostics: Diagnostics


class ErrorDetail(StrictModel):
    code: str
    message: str
    retryable: bool
    request_id: str | None


class ErrorEnvelope(StrictModel):
    detail: ErrorDetail


MODELS = {"evaluation_request": EvaluationRequest, "provider_output": ProviderOutput,
          "evaluation_result": EvaluationResult, "error": ErrorEnvelope}
