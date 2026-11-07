# Architecture / stable extension points

```text
Browser (React / Vite)                  ML teammate module
      │                                  │
      ▼                                  ▼
backend/app/main.py ──────────────► evaluator.py (unconfigured)
      │                                       │
      ├── schemas.py (Pydantic contract) ◄────┘
      ├── storage.py (SQLite, immutable versions)
      └── scoring.py (pure deterministic math)
              ▲
         checklist seed JSON (official 8 rules)
```

## Why these boundaries?

1. The official checklist changes **during judging**, so the evaluator must receive it as **data**, not as hard-coded rule names.
2. Scoring cannot depend on stochastic model arithmetic. ML selects answers and supporting evidence; backend computes the exact score.
3. An appeal must modify **one criterion** in the final result while preserving original answers and original checklist version.
4. The same import endpoint handles DEV and control `group_id`, and stable message IDs disambiguate repeated timestamps.
5. SQLite is adequate for a localhost 24-hour demo. It is not a production database or multi-user security boundary.

## Persistence

- `checklists(key, version, payload_json)` — each version immutable.
- `conversations` — source transcript and audio URL retained locally; any attempt to overwrite existing `(group_id, conversation_id)` with different bytes returns 409 rather than silently invalidating evidence links.
- `evaluations` — append-only original answers, checklist version and evaluator origin.
- `appeals` — separate comments and reviewer decisions; current score is **derived** by replaying accepted replacements against original answers.

## Design for future Codex tasks

Make changes in small PRs by domain (fullstack vs ML). Agree on versioned API contracts *before* adding extra model fields. Add an integration test for each requirement. Later make a separate, user-approved JSON work plan for Codex; this repo currently contains only operational code and initial checklist configuration.

## Explicit known gaps

- Model integration, retries and real AI quality assessment (currently 501).
- Full ASR/audio prosody analysis; audio URLs are displayed for playback/links only.
- Authentication, production deployment, bulk queue, per-item asynchronous processing and prompt-injection defense to be designed if moving beyond localhost demo.
- Jury may apply chat rubric to calls, but no separate official voice-specific rubric was supplied.
