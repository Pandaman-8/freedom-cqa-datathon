"""Local-only SQLite storage. Checklist revisions and original evaluations are immutable."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import os
import sqlite3

from .schemas import Checklist, ChecklistDraft, SourceData, CriterionAnswer
from .scoring import calculate


SEED_FILE = Path(__file__).resolve().parent / "seed" / "chat_quality.json"


class StorageConflict(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _get_db_path() -> Path:
    return Path(os.getenv("CQA_DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "cqa.sqlite")))


@contextmanager
def database():
    path = _get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS checklists (
            key TEXT NOT NULL, version INTEGER NOT NULL,
            payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY (key, version)
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            dataset_group_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            language TEXT NOT NULL, channel TEXT NOT NULL,
            transcript_json TEXT NOT NULL, message_count INTEGER NOT NULL,
            audio_url TEXT, content_hash TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evaluations (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            checklist_key TEXT NOT NULL, checklist_version INTEGER NOT NULL,
            origin TEXT NOT NULL, answers_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (checklist_key, checklist_version) REFERENCES checklists(key, version)
        );
        CREATE TABLE IF NOT EXISTS appeals (
            id TEXT PRIMARY KEY,
            evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
            criterion_id TEXT NOT NULL, comment TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', decision TEXT,
            reason TEXT, replacement_json TEXT,
            created_at TEXT NOT NULL, resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_evals_conversation ON evaluations(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_appeals_evaluation ON appeals(evaluation_id);
        """)
        seed = Checklist.model_validate(json.loads(SEED_FILE.read_text(encoding="utf-8")))
        db.execute("INSERT OR IGNORE INTO checklists(key, version, payload_json, created_at) VALUES (?, ?, ?, ?)",
                   (seed.key, seed.version, _json(seed.model_dump()), utc_now()))
        db.commit()
        yield db
    finally:
        db.close()


def list_checklists() -> list[dict]:
    with database() as db:
        rows = db.execute("""SELECT key, MAX(version) AS version FROM checklists GROUP BY key ORDER BY key""").fetchall()
        return [get_checklist(row["key"], row["version"], db=db).model_dump() for row in rows]


def get_checklist(key: str, version: int | None = None, *, db=None) -> Checklist | None:
    if db is None:
        with database() as conn:
            return get_checklist(key, version, db=conn)
    if version is None:
        row = db.execute("SELECT payload_json FROM checklists WHERE key=? ORDER BY version DESC LIMIT 1", (key,)).fetchone()
    else:
        row = db.execute("SELECT payload_json FROM checklists WHERE key=? AND version=?", (key, version)).fetchone()
    return Checklist.model_validate_json(row[0]) if row else None


def save_checklist(key: str, draft: ChecklistDraft, *, create: bool = False) -> Checklist:
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = get_checklist(key, db=db)
        if create and previous:
            raise StorageConflict("Checklist key already exists")
        if not create and previous is None:
            raise KeyError(key)
        saved = Checklist(key=key, version=previous.version + 1 if previous else 1, **draft.model_dump())
        db.execute("INSERT INTO checklists(key, version, payload_json, created_at) VALUES (?, ?, ?, ?)",
                   (saved.key, saved.version, _json(saved.model_dump()), utc_now()))
        db.commit()
    return saved


def import_dataset(data: SourceData) -> dict:
    lang_count = {lang: 0 for lang in ("RU", "KZ", "EN")}
    channel_count = {channel: 0 for channel in ("agent chat", "voice call")}
    now = utc_now()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        for record in data.records:
            record_id = f"{data.dataset_group_id}:{record.conversation_id}"
            content = record.model_dump()
            signature = sha256(_json(content).encode("utf-8")).hexdigest()
            previous = db.execute("SELECT content_hash FROM conversations WHERE id=?", (record_id,)).fetchone()
            if previous is not None and previous["content_hash"] != signature:
                raise StorageConflict(f"{record_id} was already imported with different data")
            db.execute("""INSERT OR IGNORE INTO conversations (
                id, dataset_group_id, conversation_id, language, channel,
                transcript_json, message_count, audio_url, content_hash, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                record_id, data.dataset_group_id, record.conversation_id,
                record.language, record.channel,
                _json([m.model_dump() for m in record.transcript]),
                len(record.transcript), record.audio_url, signature, now
            ))
            lang_count[record.language] += 1
            channel_count[record.channel] += 1
        db.commit()
    return {"dataset_group_id": data.dataset_group_id, "imported_records": len(data.records),
            "languages": lang_count, "channels": channel_count}


def list_conversations() -> list[dict]:
    with database() as db:
        rows = db.execute("""SELECT id, conversation_id, dataset_group_id, language, channel,
                                  message_count, imported_at FROM conversations
                                  ORDER BY dataset_group_id, conversation_id LIMIT 2000""").fetchall()
        return [dict(row) for row in rows]


def get_conversation(conversation_id: str, *, db=None) -> dict | None:
    if db is None:
        with database() as conn:
            return get_conversation(conversation_id, db=conn)
    row = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["transcript"] = json.loads(data.pop("transcript_json"))
    data["messages"] = [
        {"id": f"m{i:04d}", "timestamp": m["timestamp"], "speaker": m["speaker"], "text": m["text"]}
        for i, m in enumerate(data["transcript"], start=1)
    ]
    return data


def validate_evidence(answers: list[CriterionAnswer], conversation: dict) -> None:
    valid = {m["id"]: m["text"] for m in conversation["messages"]}
    for a in answers:
        for e in a.evidence:
            if e.message_id not in valid or e.quote not in valid[e.message_id]:
                raise ValueError(f"{a.criterion_id}: evidence must quote a real message by ID")


def save_evaluation(conversation_id: str, checklist_key: str, answers: list[CriterionAnswer], origin: str) -> dict:
    with database() as db:
        conversation = get_conversation(conversation_id, db=db)
        if conversation is None:
            raise KeyError(conversation_id)
        checklist = get_checklist(checklist_key, db=db)
        if checklist is None:
            raise KeyError(checklist_key)
        # Also performs strict answer/scale/N/A validation before anything is persisted.
        calculate(checklist, answers)
        validate_evidence(answers, conversation)
        evaluation_id = uuid4().hex
        db.execute("""INSERT INTO evaluations(id, conversation_id, checklist_key,
                      checklist_version, origin, answers_json, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""", (
                          evaluation_id, conversation_id, checklist_key, checklist.version,
                          origin, _json([a.model_dump() for a in answers]), utc_now()))
        db.commit()
    return get_evaluation(evaluation_id)


def _appeals(db, evaluation_id: str) -> list[dict]:
    rows = db.execute("SELECT * FROM appeals WHERE evaluation_id=? ORDER BY created_at, id", (evaluation_id,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["replacement"] = json.loads(item.pop("replacement_json")) if item["replacement_json"] else None
        result.append(item)
    return result


def get_evaluation(evaluation_id: str, *, db=None) -> dict | None:
    if db is None:
        with database() as conn:
            return get_evaluation(evaluation_id, db=conn)
    row = db.execute("SELECT * FROM evaluations WHERE id=?", (evaluation_id,)).fetchone()
    if row is None:
        return None
    checklist = get_checklist(row["checklist_key"], row["checklist_version"], db=db)
    original = [CriterionAnswer.model_validate(a) for a in json.loads(row["answers_json"])]
    current = {a.criterion_id: a for a in original}
    appeals = _appeals(db, evaluation_id)
    for a in appeals:
        if a["status"] == "resolved" and a["decision"] == "change" and a["replacement"]:
            replacement = CriterionAnswer.model_validate(a["replacement"])
            current[replacement.criterion_id] = replacement
    final_answers = [current[a.criterion_id] for a in original]
    return {
        "id": row["id"], "conversation_id": row["conversation_id"],
        "checklist_key": row["checklist_key"], "checklist_version": row["checklist_version"],
        "origin": row["origin"], "created_at": row["created_at"],
        "original_answers": [a.model_dump() for a in original],
        "original_score": calculate(checklist, original),
        "final_answers": [a.model_dump() for a in final_answers],
        "final_score": calculate(checklist, final_answers),
        "appeals": appeals,
        "review_status": "appealed" if any(a["status"] == "open" for a in appeals) else
                         "reviewed" if appeals else "evaluated",
    }


def list_evaluations(conversation_id: str | None = None) -> list[dict]:
    with database() as db:
        if conversation_id:
            rows = db.execute("SELECT id FROM evaluations WHERE conversation_id=? ORDER BY created_at DESC", (conversation_id,)).fetchall()
        else:
            rows = db.execute("SELECT id FROM evaluations ORDER BY created_at DESC LIMIT 200").fetchall()
        return [get_evaluation(row["id"], db=db) for row in rows]


def create_appeal(evaluation_id: str, criterion_id: str, comment: str) -> dict:
    with database() as db:
        evaluation = get_evaluation(evaluation_id, db=db)
        if evaluation is None:
            raise KeyError(evaluation_id)
        if criterion_id not in {a["criterion_id"] for a in evaluation["original_answers"]}:
            raise ValueError("Unknown criterion ID")
        active = db.execute("""SELECT id FROM appeals WHERE evaluation_id=? AND criterion_id=?
                               AND status='open'""", (evaluation_id, criterion_id)).fetchone()
        if active:
            raise StorageConflict("An open appeal for this criterion already exists")
        appeal_id = uuid4().hex
        db.execute("""INSERT INTO appeals(id, evaluation_id, criterion_id, comment, status, created_at)
                      VALUES (?, ?, ?, ?, 'open', ?)""", (appeal_id, evaluation_id, criterion_id, comment, utc_now()))
        db.commit()
        return {"id": appeal_id, "evaluation_id": evaluation_id, "criterion_id": criterion_id,
                "status": "open", "comment": comment}


def resolve_appeal(appeal_id: str, decision: str, reason: str, replacement: CriterionAnswer | None) -> dict:
    with database() as db:
        appeal = db.execute("SELECT * FROM appeals WHERE id=?", (appeal_id,)).fetchone()
        if appeal is None:
            raise KeyError(appeal_id)
        if appeal["status"] != "open":
            raise StorageConflict("Appeal was already resolved")
        evaluation = get_evaluation(appeal["evaluation_id"], db=db)
        if decision == "change":
            if replacement is None or replacement.criterion_id != appeal["criterion_id"]:
                raise ValueError("Replacement must belong to appealed criterion")
            checklist = get_checklist(evaluation["checklist_key"], evaluation["checklist_version"], db=db)
            new_answers = [
                replacement if a["criterion_id"] == replacement.criterion_id else CriterionAnswer.model_validate(a)
                for a in evaluation["final_answers"]
            ]
            calculate(checklist, new_answers)
            conversation = get_conversation(evaluation["conversation_id"], db=db)
            validate_evidence([replacement], conversation)
        db.execute("""UPDATE appeals SET status='resolved', decision=?, reason=?, replacement_json=?,
                      resolved_at=? WHERE id=?""", (
                          decision, reason, _json(replacement.model_dump()) if replacement else None,
                          utc_now(), appeal_id))
        db.commit()
        return get_evaluation(appeal["evaluation_id"], db=db)
