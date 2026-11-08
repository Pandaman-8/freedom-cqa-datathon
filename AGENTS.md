# AGENTS.md — required context for Codex

This repository contains the Java/Vanilla application and separate Python ML service for a 24-hour CQA hackathon. Work on the existing
`plan.json`; do not create a replacement plan or start dependent tasks without authorization.
Read the assigned task and `docs/INTEGRATION_CONTRACT.md` before changing a shared boundary.
Also read `README.md`, `docs/requirements.md`, `docs/architecture.md` and `docs/api-contract.md`
before application changes. These documents describe the target application; historical
audits and task evidence can describe earlier states. Use current source and
docs/RELEASE_READINESS.md for verification scope; never treat old evidence as a new run.

## Sources of truth

1. Organizer's **CQA_Hackathon_Student_Guide_v3** and **CQA_Chat_Quality_Checklist**.
   `data/official/student_guide_v3.pdf` is available locally and private;
   `data/official/chat_quality_checklist.pdf` remains unavailable at T18 verification.
   Do not claim full official verification until it is supplied and checked.
2. Initial checklist in `backend/app/seed/chat_quality.json`: preserve all eight criteria,
   exact levels and N/A rules; its fidelity remains provisional pending that PDF.
3. `contracts/*.schema.json`, `contracts/fixtures/manifest.json` and
   `docs/INTEGRATION_CONTRACT.md`: one language-neutral contract, two implementations.
   Embedded schemas in `plan.json` must stay identical; run the drift check after edits.
4. Current tasks/acceptance criteria in `plan.json`; historical evidence in `docs/CODEX_AUDIT.md`.
   The legacy Python scorer/tests are behavioral references, not proof of passing Java tests.

When sources are silent, state an assumption instead of inventing an organizer rule.

## Approved architecture

- **Farhat — Fullstack:** Java 21, Spring Boot MVC, JDBC/SQLite; HTML5, CSS3 and Vanilla
  JavaScript. Java serves static assets and `/api` on 127.0.0.1:8080. Current source pins
  Spring Boot 3.5.16, SQLite JDBC 3.53.4.0 and Maven 3.9.11; no global Maven is required.
- **Nurtas — ML:** independent Python/FastAPI HTTP service on 127.0.0.1:8001; prompts,
  model/provider integration, evidence extraction and validation. Run one worker;
  Python does not own the Fullstack domain API or SQLite.
- Browser → Java REST API → Java storage/scoring/review or Python ML HTTP.
  Java calls `POST /v1/evaluate`, JSON/UTF-8, contract **2.0.0**. `/v1` is the HTTP route
  generation, not an alternative JSON envelope version.
- Java alone owns target SQLite persistence and deterministic scoring. Python returns
  answers, grounded evidence and diagnostics; never authoritative numeric totals.
- Target locations: `server/` (including `src/main/resources/static/`) and `ml-service/`.
  Legacy `backend/` and `frontend/` remain references. Do not delete them or build the new
  Fullstack as a gateway to the old Python domain API.
- No React, JSX or Vite in the target frontend. No JPA/Hibernate, distributed queue,
  authentication or production deployment scope for the local demo.

## Domain and integrity invariants

- Pure scoring uses configured discrete levels/weights. N/A only when `allow_na` is true;
  exclude that weight and normalize the applicable weights. C08 is a separate weightless
  gross-violation flag, never a numeric penalty. Preserve `cqa-score/1` semantics.
- Preserve original text/order, labels (`operator`, `client`, `bot`, `system`) and timestamps.
  Chats use MM:SS; calls use ISO 8601 with a time zone. Repeated timestamps do not merge
  turns. Use positional `m0001`-style IDs, extending beyond four digits as needed.
  A bot greeting does not count as an operator greeting.
- Evidence references an existing ID and a nonblank exact substring, without translation,
  trimming the quote or Unicode normalization. Omitted actions cite real surrounding
  context and explain the omission; do not invent absence quotes. Grounding is necessary
  but does not prove semantic relevance.
- Checklist edits append versions. Pin the full conversation/checklist before ML, validate
  response identity/version, and never re-read latest during save. No database transaction
  while awaiting HTTP inference.
- Original answers/score snapshots are immutable. Reviewer decisions are separate, atomic
  and revision-checked; final results use the pinned scorer/version.
- Strict JSON Schema is necessary but insufficient: both implementations check composition,
  criterion/kind/levels/N/A, identity echoes and exact evidence using the same fixtures.
- Python owns retries: at most two provider attempts in 65 seconds. Java HTTP deadline
  is 70 seconds; no automatic Java POST replay. Preserve request IDs/status and reconcile
  unknown outcomes before explicit retry. Timeout does not guarantee inference cancellation
  or exactly-once provider billing.

## Ownership and agreement

- Farhat: `server/**`, Vanilla assets, Java DTO/REST/scoring/SQLite/review/tests, build/CI,
  `AGENTS.md`, README and `plan.json`.
- Nurtas: `ml-service/**`, Python schemas conforming to the shared contract, prompts,
  provider adapter, ML tests and quality/cost measurements.
- Farhat edits `contracts/**` and integration specs after joint review. Nurtas does not
  independently redefine JSON or alter scoring math.
- **Any change to JSON, endpoints, field names, score semantics, message IDs or validation
  requires Farhat and Nurtas agreement BEFORE implementation.** Never silently change
  schemas, seed or fixtures to make tests pass.
- T02 is still **ready** in plan.json: no joint acknowledgment is recorded there. It stays ready until both participants explicitly accept the same artifact revision.
  Preparing artifacts, passing checks or authorizing this task is not joint approval.
  Record actual acknowledgment evidence; never invent it.
- Separate worktrees/clones and databases for independent work. Shared fixtures first,
  then Java/Python branches, then joint HTTP integration. No destructive reset/force-push
  of another participant's work. Do not delegate unless explicitly requested.

## Verification

T02 uses an isolated tooling environment, not a backend/service environment:

```bash
python3 -m venv /tmp/freedom-cqa-t02-validation
/tmp/freedom-cqa-t02-validation/bin/python -m pip install -r contracts/requirements.txt
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
```

This checks four Draft 2020-12 schemas, drift from `plan.json`, transport metadata,
documented examples and all fixture expectations. Parser-negative files intentionally
fail strict JSON decoding. See `contracts/README.md` for details and limits.

Current target checks (use isolated environments, temporary SQLite and no provider keys):

```bash
./server/mvnw -f server/pom.xml clean verify
node --experimental-default-type=module --test server/src/test/js/*.test.mjs
python3 server/src/test/python/scoring_reference.py --check
GROQ_API_KEY= GROQ_FREE_PLAN_CONFIRMED=false PYTHONPATH=ml-service ml-service/.venv/bin/python -B -m pytest -q ml-service/tests
ml-service/.venv/bin/python -B server/src/test/python/release_smoke.py --ml-python "$PWD/ml-service/.venv/bin/python"
python3 -B scripts/check-public-safety.py
```

Also verify real browser and Java↔Python HTTP workflows. Never report
those checks as passed based on fixtures, legacy Python tests or a build. The legacy
React build is not a prerequisite for the new Vanilla frontend.

## Data protection and open requirements

- Committed fixtures are synthetic only. Never commit DEV/CONTROL transcripts, recordings,
  signed URLs, credentials, `.env` or SQLite files; never log raw secrets/customer text.
  The guide PDF itself contains a signed API URI and must not be published.
- Organizer credentials belong in Java configuration; provider secrets in Python.
  Use same-origin/backend integration, never browser credentials to work around CORS.
- Successful fetch/upload archives exact JSON bytes in private `dataset-sources/` beside
  SQLite, or absolute `CQA_DATASET_SOURCE_DIR`. Directory0700/files0600, hash filenames;
  use the archived path/hash for approval v2, never serialize DB records to reconstruct a source.
  Archive failure must prevent the conversation commit; no raw-source download API exists.
- Agree provider/data policy/budget before real-data external inference; until then use
  own synthetic data or an authorized local model. No fake successful AI fallback.
- Default Java synthetic_only policy permits exactly six bundled conversation/checklist pairs;
  Python independently checks conversation fingerprints. Group names alone grant nothing.
  New conversation IDs/text or rubric versions require separate reviewed approval; never
  expand or mock these policies to turn a release-test failure into a success.
- BETA adds explicit Java approved_dataset mode with a private expiring, endpoint-bound grant:
  exact dataset hash/explicit chat IDs, provider/model and bounded checklist_scope; see docs/DYNAMIC_ADMISSION.md.
  Approval v2 technical format was accepted in the current user task. Java external inference opt-in
  defaults false; UI confirmation and matching Python admission metadata are required. A valid new
  rubric inside scope needs no grant edit. Nurtas admission v2 branch through b03ecf8 is integrated;
  Python uses ML_EXTERNAL_TRANSFER_AUTHORIZED and ML_ADMISSION_URL. Shared grants are private0600
  with UTC/Z expiry; Python first-phase restrictions include DEV chats only and at most15 IDs.
  This is not DEV transfer consent. Never manufacture approvals or treat model choice as consent.
- Release tests may inject an offline provider through Python's existing test seam, with
  external networking forbidden. This is test infrastructure, not a runtime fake mode or
  evidence of model quality. Distinguish 65 operations over six approved inputs from 65
  distinct inputs; account for policy-blocked items explicitly.
- Python without provider configuration returns health503/evaluate501; Java health is
  liveness only. Java without an ML URL returns501 before ledger claim. Do not claim
  readiness or real model success from a process start, a health check or a fixture result.
- Batch recovery uses browser-local manifest + Java ledger, Web Locks, the same origin and
  SQLite. Reload never starts POST automatically; unknown/pending are not silent retries.
- T16/T18 evidence does not close T02/T09/T14/T15/T17/T21 or authorize further live runs.
  Keep unverified official rules, dynamic AI, real-data permission and peer review explicit.
- Do not invent voice scoring or infer diction/intonation from transcript alone. Clarify
  applicability with organizers. Company factual correctness needs reference material;
  model uncertainty is not automatic N/A.
- Two-decimal HALF_UP tie rounding is an implementation convention, not a verified
  organizer rule. Preserve it pending explicit agreement.
