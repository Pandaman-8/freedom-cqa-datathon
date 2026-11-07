"""Freedom CQA API. Intentionally local-only; no login is required for the hackathon demo."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import storage
from .evaluator import evaluator
from .schemas import (AppealRequest, AppealResolution, ChecklistDraft,
                      DatasetEnvelope, ManualEvaluationRequest)
from .scoring import ScoringError

app = FastAPI(title="Freedom CQA Foundation", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(storage.StorageConflict)
def handle_conflict(_, error: storage.StorageConflict):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.get("/api/health")
def health():
    return {"status": "ok", "evaluator": "unconfigured", "schema_version": 1}


@app.post("/api/datasets/import")
def import_dataset(payload: DatasetEnvelope):
    if not payload.isSuccess or payload.error:
        raise HTTPException(status_code=422, detail="Dataset envelope indicates an API error")
    return storage.import_dataset(payload.data)


@app.get("/api/conversations")
def list_conversations():
    return storage.list_conversations()


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    item = storage.get_conversation(conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return item


@app.get("/api/checklists")
def list_checklists():
    return storage.list_checklists()


@app.get("/api/checklists/{key}")
def get_checklist(key: str, version: int | None = None):
    result = storage.get_checklist(key, version)
    if result is None:
        raise HTTPException(status_code=404, detail="Checklist not found")
    return result


@app.post("/api/checklists/{key}")
def create_checklist(key: str, draft: ChecklistDraft):
    if key == "chat-quality":
        raise HTTPException(status_code=409, detail="Initial official checklist already exists; use PUT to save a new revision")
    return storage.save_checklist(key, draft, create=True)


@app.put("/api/checklists/{key}")
def update_checklist(key: str, draft: ChecklistDraft):
    try:
        return storage.save_checklist(key, draft)
    except KeyError:
        raise HTTPException(status_code=404, detail="Checklist not found") from None


@app.post("/api/evaluations/manual", status_code=201)
def evaluate_manually(payload: ManualEvaluationRequest):
    try:
        return storage.save_evaluation(payload.conversation_id, payload.checklist_key, payload.answers, "manual")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {exc.args[0]}") from None
    except (ScoringError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


class AutoRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    checklist_key: str = "chat-quality"


@app.post("/api/evaluations/auto", status_code=201)
def evaluate_automatically(payload: AutoRequest):
    conversation = storage.get_conversation(payload.conversation_id)
    checklist = storage.get_checklist(payload.checklist_key)
    if conversation is None or checklist is None:
        raise HTTPException(status_code=404, detail="Conversation or checklist not found")
    try:
        answers = evaluator.evaluate(conversation, checklist)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="AI evaluator is not connected yet") from None
    try:
        return storage.save_evaluation(payload.conversation_id, payload.checklist_key, answers, "model")
    except (ScoringError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/evaluations")
def list_evaluations(conversation_id: str | None = None):
    return storage.list_evaluations(conversation_id)


@app.get("/api/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str):
    evaluation = storage.get_evaluation(evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation


@app.post("/api/evaluations/{evaluation_id}/appeals", status_code=201)
def appeal(evaluation_id: str, payload: AppealRequest):
    try:
        return storage.create_appeal(evaluation_id, payload.criterion_id, payload.comment)
    except KeyError:
        raise HTTPException(status_code=404, detail="Evaluation not found") from None
    except storage.StorageConflict:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/appeals/{appeal_id}/resolve")
def resolve(appeal_id: str, payload: AppealResolution):
    try:
        return storage.resolve_appeal(appeal_id, payload.decision, payload.reason, payload.replacement)
    except KeyError:
        raise HTTPException(status_code=404, detail="Appeal not found") from None
    except storage.StorageConflict:
        raise
    except (ValueError, ScoringError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
