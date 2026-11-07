# Freedom CQA — current Java workspace

The approved application is **Java21 + Spring Boot + SQLite**, serving HTML/CSS/Vanilla JS
ES modules at localhost:8080. T07 organizer fetch is closed; T12 provides conversations,
versioned checklist editing, manual evaluations, evidence, original/final scores and review,
pending acceptance/peer review. AI integration remains T13.

Start and verify using [server/README.md](server/README.md), including an isolated synthetic
browser walkthrough. No Node build is required for the target application. The Python ML
service is separate; the legacy instructions below describe the original reference only.

---

# Legacy foundation reference

**Freedom Broker CQA Hackathon · 7–8 November 2026**

Public-safe foundation for the official **Conversation Quality Analytics** task. The app accepts the organizers' DEV / control JSON, displays original conversation turns, stores versioned checklists, calculates scores *deterministically*, and supports per-criterion appeals and human reviews.

> **Status:** Real backend and manual evaluation/review flow are implemented and tested. **AI evaluation is NOT implemented yet** — `/api/evaluations/auto` deliberately returns HTTP `501`, never a fabricated result. The task plan JSON for Codex is intentionally **not** created yet.

## Requirements

- Python 3.11+ (3.12 recommended)
- Node.js 22+ / npm (React/Vite frontend)
- No Docker, PostgreSQL, cloud credentials, or authorization required for the demo

## Quick start — Linux / Arch

Terminal 1:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 (from repository root):

```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173**. FastAPI docs: **http://127.0.0.1:8000/docs**. Use two terminals: Vite does not start the backend automatically.

Convenience scripts from the project root: `bash scripts/run-backend.sh`, `bash scripts/run-frontend.sh`.

### Import official DEV dataset

Upload `invoke.json` through the **Диалоги → Импортировать JSON** control, or use:

```bash
curl -X POST 'http://127.0.0.1:8000/api/datasets/import' \
  -H 'Content-Type: application/json' \
  --data-binary @/absolute/path/to/invoke.json
```

**Do not add the original file to Git.** The provided DEV envelope contains 65 records, including signed audio URLs; the API preserves all timestamps (chat MM:SS, calls ISO 8601), speakers (operator/client/bot/system), and the original transcription. Each turn gets a stable `m0001` evidence ID.

For a public-safe import example, use `examples/synthetic_dataset.json` (2 fictional conversations). The same import endpoint works for all three languages RU/KZ/EN and both channels.

### Test scoring and appeals before ML integration

1. Import the sample or organizer JSON, then select a conversation.
2. Open **Оценивание** and manually select each criterion, justification and an actual supporting message.
3. Save: backend calculates original total, sections and gross-violation flag.
4. In **Результаты / пересмотр**, create an appeal for a criterion and resolve it (confirm/change). Verify old vs final total.
5. In **Чек-лист**, edit a criterion and save **v2**. Future evaluations use v2; historical v1 evaluations keep their original version.

This is a tested **manual QA workflow**. It is not presented as a working AI model.

## What the official scoring engine does

The seeded checklist is a direct transcription of `CQA_Chat_Quality_Checklist.pdf`, pages 1–3. The first seven weights are `10 + 15 + 20 + 20 + 15 + 15 + 5 = 100`. C08 is a **separate, weightless gross-violation flag** and does *not* automatically zero the score.

| ID | Criterion | Input | Weight |
|---|---|---|---|
| C01 | Установление контакта | yes/no | 10 |
| C02 | Выявление потребности | yes/no/N/A | 15 |
| C03 | Идентификация | yes/no/N/A | 20 |
| C04 | Корректная и полная консультация | 0/5/10/15/20/N/A | 20 |
| C05 | Эмпатия | yes/no | 15 |
| C06 | Управление диалогом | 0/4/7/10 | 15 |
| C07 | Завершение | yes/no/N/A | 5 |
| C08 | Грубые ошибки | yes/no flag | 0 |

- Binary yes = full criterion weight, no = 0.
- Scales earn `weight × selected_level / max_level`.
- N/A is allowed **only** for C02/C03/C04/C07 in the default version. The resulting sum is normalized by the sum of *applicable* weights to 100.
- Final total is rounded to **2 decimals**. If no weighted criterion applies, result is null. Exact half-tie rounding is not stated in the organizer PDF; implementation uses standard `ROUND_HALF_UP`.
- 3-minute first-response threshold, tags and attachments are **out of scope** for this checklist.

### Design boundaries

- **Frontend (fullstack teammate):** React + Vite, checklist editor, conversation browser, evidence jumps, appeals and review.
- **Backend (fullstack teammate):** FastAPI, SQLite, strict schemas, import, immutable checklist revisions, deterministic scoring and review history.
- **ML teammate:** implement the `Evaluator` protocol in `backend/app/evaluator.py`, returning one answer per criterion and evidence grounded in `conversation.messages`. Do not compute overall scores in ML.

Read [AGENTS.md](AGENTS.md) before using Codex. Supporting specs: [architecture](docs/architecture.md), [API contract](docs/api-contract.md), [source requirements](docs/requirements.md), and [ML handoff](docs/ml-contract.md).

## Run tests

```bash
cd backend
python -m pip install -r requirements-dev.txt
cd ..
PYTHONPATH=backend python -m pytest -q backend/tests
```

CI runs backend tests and frontend Vite build. All test fixtures and demo conversations in this repository are synthetic.

## Privacy / safety

The official DEV file has 5 real calls and may carry identifiers, sensitive transcription fragments and signed recording URLs. **Never commit the raw DEV, control group, audio URL with `sig`, SQLite database, `.env`, credentials, customer personal data or recording downloads.** They are excluded by `.gitignore`. Deploy this foundation **locally only** until authentication, access controls and privacy review are addressed. No client-side `VITE_*` API keys.

## Publishing to the existing repository

If this archive is your first local checkout and the remote is still empty:

```bash
bash scripts/publish.sh
```

This runs `git push` to `https://github.com/Pandaman-8/freedom-cqa-datathon.git` without force. If the repository already has commits or Git access is denied, stop and reconcile normally. The ChatGPT GitHub app previously returned HTTP 403 on writes; the included script uses **your own** local Git credentials.
