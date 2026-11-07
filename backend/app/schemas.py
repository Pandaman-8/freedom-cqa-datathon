"""Pydantic contracts for official input and configurable evaluations."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Section(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=180)


class ScaleLevel(BaseModel):
    value: float = Field(ge=0)
    description: str = Field(min_length=1)


class Criterion(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    kind: Literal["binary", "scale", "flag"]
    weight: float = Field(ge=0, le=100)
    allow_na: bool = False
    na_rule: str | None = None
    levels: list[ScaleLevel] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_criterion(self):
        if self.allow_na and not self.na_rule:
            raise ValueError("N/A criterion must include a non-empty na_rule")
        if self.kind == "flag":
            if self.weight != 0 or self.allow_na or self.levels:
                raise ValueError("Flag must be weightless, disallow N/A and have no scale")
        elif self.weight <= 0:
            raise ValueError("Weighted criterion must have a positive weight")
        if self.kind == "scale":
            values = [level.value for level in self.levels]
            if len(values) < 2 or len(values) != len(set(values)) or min(values) != 0 or max(values) <= 0:
                raise ValueError("Scale must have unique values, starting at 0 and ending above 0")
        elif self.levels:
            raise ValueError("Non-scale criteria cannot have levels")
        return self


class ChecklistDraft(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    sections: list[Section] = Field(min_length=1)
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_composition(self):
        sections = [s.id for s in self.sections]
        criterion_ids = [c.id for c in self.criteria]
        if len(sections) != len(set(sections)) or len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Section and criterion IDs must be unique")
        if not all(c.section_id in sections for c in self.criteria):
            raise ValueError("All criteria must refer to existing sections")
        if not any(c.weight > 0 for c in self.criteria):
            raise ValueError("Checklist requires at least one weighted criterion")
        return self


class Checklist(ChecklistDraft):
    key: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1)


class SourceMessage(BaseModel):
    timestamp: str = Field(min_length=1)
    speaker: Literal["operator", "client", "bot", "system"]
    text: str


class SourceConversation(BaseModel):
    conversation_id: str = Field(min_length=1)
    channel: Literal["agent chat", "voice call"]
    language: Literal["RU", "KZ", "EN"]
    transcript: list[SourceMessage] = Field(min_length=1)
    audio_url: str | None = None


class SourceData(BaseModel):
    dataset_group_id: str = Field(min_length=1)
    total_records: int = Field(ge=0)
    records: list[SourceConversation]

    @model_validator(mode="after")
    def validate_dataset(self):
        ids = [c.conversation_id for c in self.records]
        if self.total_records != len(ids) or len(ids) != len(set(ids)):
            raise ValueError("Inconsistent total_records or duplicate conversation_id")
        return self


class DatasetEnvelope(BaseModel):
    error: str = ""
    isSuccess: bool
    data: SourceData


class Evidence(BaseModel):
    message_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class CriterionAnswer(BaseModel):
    criterion_id: str
    answer: Literal["yes", "no", "na", "scale"]
    value: float | None = None
    explanation: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class ManualEvaluationRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    checklist_key: str = "chat-quality"
    answers: list[CriterionAnswer] = Field(min_length=1)


class AppealRequest(BaseModel):
    criterion_id: str
    comment: str = Field(min_length=1, max_length=3000)


class AppealResolution(BaseModel):
    decision: Literal["confirm", "change"]
    reason: str = Field(min_length=1, max_length=3000)
    replacement: CriterionAnswer | None = None

    @model_validator(mode="after")
    def require_replacement_on_change(self):
        if self.decision == "change" and self.replacement is None:
            raise ValueError("Change decision requires replacement answer and evidence")
        if self.decision == "confirm" and self.replacement is not None:
            raise ValueError("Confirm decision must not have a replacement answer")
        return self
