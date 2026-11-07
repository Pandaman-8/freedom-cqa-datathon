# AGENTS.md — required context for Codex

This repository is the foundation of a 24-hour CQA hackathon, not a greenfield toy app. Read `README.md`, `docs/requirements.md`, `docs/architecture.md` and `docs/api-contract.md` before editing code.

## Sources of truth (in priority order)

1. Organizer's **CQA_Hackathon_Student_Guide_v3** and **CQA_Chat_Quality_Checklist**.
2. Official initial checklist in `backend/app/seed/chat_quality.json` (8 criteria and exact level values).
3. Current Pydantic contracts in `backend/app/schemas.py`, pure score engine in `backend/app/scoring.py`.
4. This repository's architecture docs and integration tests.

When source documents are silent, mark an assumption openly instead of inventing an organizer rule. Do not create the full task-plan JSON unless specifically requested later.

## Architecture invariants

- Keep `Frontend → FastAPI → storage / evaluator / scoring` separation.
- ML returns answers + grounded evidence; **never** trust an LLM to return or override numeric totals.
- `calculate()` is pure and must be covered by tests. N/A only when `allow_na` is true; redistribute weights among applicable criteria. Scales use the **configured discrete values**, not arbitrary 0–100 values. C08 gross violation is a **separate flag**, not a scoring penalty.
- All original speaker labels (`operator`, `client`, `bot`, `system`) and timestamps must be preserved. Bot greetings do not count as operator greeting. Call timestamps are ISO 8601; chat timestamps are MM:SS. Do not parse all timestamps as a single format.
- Evidence must reference an existing `m0001`-style message ID and an exact substring of its text. For an omitted action, point to the surrounding message showing where the action was expected. Do not hallucinate quotes.
- Checklist edits create new versions. Existing evaluations refer to their original checklist version. Original answers/scores stay immutable; appealed/reviewed final results are derived from reviewer decisions.
- The frontend must remain a normal HTML/CSS/JS component-capable UI (no authentication needed for demo). CORS errors should be solved via backend proxy, not by leaking credentials in browser code.
- Do not use real customer transcripts as test fixtures or commit signed `audio_url`s. Never print/store secrets in logs.

## Roles / independent work

- Fullstack: `frontend/`, `backend/app/main.py`, `backend/app/storage.py`, `backend/app/scoring.py`, API schemas.
- ML: `backend/app/evaluator.py` or a future `backend/app/ml/` module. Do not directly change scoring math without discussing with fullstack.
- Both: agree on `CriterionAnswer` schema before changing it; share example real grounded answers (synthetic text only in commits).

## Commands to run after changes

```bash
PYTHONPATH=backend python -m pytest -q backend/tests
cd frontend && npm install && npm run build
```

If offline and npm installation fails, report that frontend build is **unverified** (never report a green frontend build based solely on JSX syntax).

## Intentional unfinished parts

- AI evaluator is explicitly **unconfigured** (HTTP 501). Replace with a real model adapter only after agreement on prompt, validation, costs, retries, privacy and evidence testing.
- The source PDF is titled **chat quality**, while the dataset includes **voice calls**. Do not invent separate call scoring rules; mark differences for organizer clarification.
- Source PDF does not specify exact ties in 2-decimal rounding; `ROUND_HALF_UP` is an implementation choice.
- No planned `plan.json` yet. It will be created during a later Codex planning session by user request.
