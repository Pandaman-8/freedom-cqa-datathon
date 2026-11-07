# Freedom CQA — Java + Vanilla workspace

This module implements application liveness and a static Vanilla JS start page (T03),
strict contract DTOs/validation and deterministic scoring (T04), and persistent SQLite,
JSON import, versioned checklist REST and manual evaluation/history (T05), plus
immutable evaluations and atomic appeals/review (T06), and organizer dataset fetching
with a Vanilla group_id form (T07, closed after peer approval), plus the T12 Vanilla
workspace for conversations, versioned checklists, manual evaluations and T06 review.
T12 is closed after peer approval. T13 implements the Java ML HTTP client, durable request
ledger and AI UI for verified own synthetic fixtures. T13 is closed after the live Groq
E2E and peer approval reported by Farhat; the saved kz_public_na ledger corroborates that
run (details in plan.json). T14 remains in_progress: model review/manual v2 are verified,
but dynamic v2 AI requires a separately approved fixture and live-run agreement.
The legacy backend/frontend and shared contract2.0.0 are unchanged.

## Requirements and pinned versions

- Java21 JDK (`java -version`, `javac -version`).
- Spring Boot3.5.16, Spring MVC, Validation and JDBC via the Boot BOM.
- SQLite JDBC3.53.4.0.
- Maven3.9.11, Apache Maven Wrapper3.3.4 (`only-script`). No global Maven required.
- First build needs access to Maven Central and a writable Maven cache. Linux needs a
  POSIX shell and curl/wget (or the wrapper's Java downloader), plus unzip or JDK jar.
- No Python service, API keys, dataset, Node.js or frontend build step required.

Spring Boot3.5 was selected for the established MVC/JDBC stack without a major framework
migration. Java21 compatibility is documented in the
[Spring Boot3.5 requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html).
The [official Maven Wrapper](https://maven.apache.org/tools/wrapper/) downloads the pinned
Maven distribution on first use. Wrapper scripts were extracted unchanged from the Apache
3.3.4 distribution in Maven Central and checked against its published SHA1 checksum over HTTPS.

## Build and run

From the repository root:

```bash
./server/mvnw -f server/pom.xml verify
./server/mvnw -f server/pom.xml spring-boot:run
```

Open http://127.0.0.1:8080/. The application binds to127.0.0.1:8080 by default.
Stop it with Ctrl+C. Alternatively, after verify:

```bash
java -jar server/target/freedom-cqa-server-0.1.0.jar
```

On Windows, use `server\mvnw.cmd -f server\pom.xml verify` with Java21 installed.
The Windows wrapper is included but has not been tested on this Linux machine.

## What health means

`GET /api/health` returns200 JSON:

```json
{"status":"ok","service":"freedom-cqa-java","version":"0.1.0"}
```

This is Java liveness only. It does not claim ML, scoring, durable persistence or automatic
assessment readiness. `cqa.version` is filled from the Maven project version during resource
processing. No organizer/provider calls occur during startup or health checks.

SQLite uses one Hikari connection and the absolute default path
`${user.home}/.local/share/freedom-cqa/java/cqa.sqlite`, independent of the working directory.
Override with an **absolute** `CQA_DB_PATH` or `--cqa.db-path=/absolute/path/cqa.sqlite`.
The Java database is separate from the legacy Python database; no legacy history is migrated.

Every connection enables foreign keys, a 5-second busy timeout and WAL. Write transactions
use SQLite IMMEDIATE mode; checklist version checking and insertion occur atomically.
The database directory/schema are created on startup. The seed is packaged unchanged from
`backend/app/seed/chat_quality.json` at build time; startup inserts v1 only if missing and
never resets the latest-version pointer. The packaged JAR does not need a source checkout.
Version numbers are stored as canonical integer text, with an explicit latest pointer, to
preserve the shared DTO's BigInteger range. Original source/checklist/evaluation rows are
protected against UPDATE/DELETE; later reviews must use separate records.

## Frontend and tests

`src/main/resources/static/` is a native ES-module application, served by Java without
npm, a bundler, external fonts/CDNs or authentication. Overview counts come from Java;
conversations, checklists, manual results and appeals use the existing same-origin APIs.
Health indicates Java liveness; AI requires explicit local ML configuration. Detailed T12
architecture, verification and a synthetic manual walkthrough are below.

`FoundationTest` starts a real embedded server on a random port and checks application
context/SQLite driver via SELECT1, health JSON, HTML, and CSS/JS HTTP resources. Browser
checks are separate; Maven tests alone do not prove JavaScript execution or visual layout.
Build output is ignored under `server/target/`. Actual T03 results are recorded only in
`plan.json → tasks[T03].completion_evidence` after verification.

## T04 contract and scoring

`cqa.dto` records preserve contract **2.0.0** field names and explicit nulls. Lists are copied
on construction; decimals use BigDecimal and integral fields use BigInteger (including
mathematically integral JSON such as `2.0`). No new dependency was added.

Use `ContractJson` in a try-with-resources block. Its `readRequest`, `readResult`,
`readProviderOutput` and `readError` methods perform strict decoding, Bean Validation and
context checks. A result requires the pinned request and an explicit validation mode;
production rejects zero provider attempts. Error validation also requires the HTTP status.
Low-level `parse`/`shape`/`read` methods expose the three layers for tests; `read` alone
does **not** check identity, checklist composition or evidence grounding. These rules are
also available in `ContractValidation` for objects constructed directly in Java. Do not
use Spring's default ObjectMapper as a replacement for this boundary codec.

Request/response byte limits are 1 MiB / 256 KiB. Parser failures expose only safe rule
identifiers, without source text or raw Jackson exceptions. Exact quotes and source text
are never normalized. Grounding verifies substrings, not the relevance of ML judgments.

`new ScoringEngine().calculate(checklist, answers)` returns the existing `cqa-score/1`
snapshot fields. It validates checklist/answer composition but cannot ground evidence
without a conversation; validate the complete request/result first. The engine uses
exact ratios of BigDecimal values for nonterminating divisions and rounds only emitted
numbers to two decimals with HALF_UP. Rounded row values are never summed into totals.
It supports dynamic criteria, N/A, independent gross flags and empty section percentages.
ScoringEngine.VERSION identifies the scorer; persistence of this identity is outside T04.

Maven runs all 72 shared fixture expectations at their specified parse/shape/context layers,
DTO round trips, generated missing/unknown/type cases, decimal/Unicode/grounding cases,
custom scales and 5,184 seed combinations. Every field of each seed score is compared
against a checked-in SHA256 reference, generated independently using Python Fraction.
The reference generator can also check every field against the unchanged legacy Python
Decimal implementation:

```bash
python3 server/src/test/python/scoring_reference.py --check
PYTHONPATH=backend backend/.venv/bin/python -B server/src/test/python/scoring_reference.py --check --legacy
./server/mvnw -f server/pom.xml verify -o
```

The first two commands run from the repository root; the legacy check needs its existing
Pydantic environment. Maven reads the reference hashes and does not launch Python, ML,
provider calls or external HTTP. Offline Maven requires previously cached build dependencies;
T03's tests still open a local HTTP port. The independent shared-contract check remains
the command in `contracts/README.md`. No Python ML-service implementation or live HTTP
compatibility is claimed by these tests.

## T05 local REST API

All routes use the Java server and JSON. T12 consumes these existing routes.

| Route | Behavior |
|---|---|
| `POST /api/datasets/import` | Organizer JSON envelope, atomic/idempotent, 16 MiB limit |
| `GET /api/conversations` | All imported conversation summaries |
| `GET /api/conversations/{id}` | Original transcript, positional messages and local audio URL |
| `GET /api/checklists` | Latest version of each checklist |
| `GET /api/checklists/{key}?version=N` | Exact historical version; omit version for latest |
| `POST /api/checklists/{key}` | Create v1 from editable draft fields |
| `PUT /api/checklists/{key}?expected_version=N` | Append version; stale version returns 409 |
| `POST /api/evaluations/manual` | Required conversation_id, checklist_key, checklist_version, answers; returns 201 |
| `GET /api/evaluations?conversation_id=...` | Stored history; omit filter for all evaluations |
| `GET /api/evaluations/{id}` | Stored original answers/score and pinned version, without recalculation |
| `POST /api/evaluations/auto` | Validate request_id/resources/version, then honest 501 EVALUATOR_UNCONFIGURED |

Draft fields are title, description, sections and criteria; key/version are assigned by the
server. Legacy optional defaults remain: absent description/error becomes an empty string,
absent audio_url becomes null. Explicit nulls, extra fields and wrong types are validated.
The import result's imported_records counts accepted input records, including identical
reimports. Changed content (including audio_url) under an existing composite ID returns
409 VERSION_CONFLICT and rolls back the whole import. No organizer URL is fetched.

Other request bodies have a 1 MiB bound; limits count actual bytes, including chunked
requests. Validation errors use 422 INVALID_INPUT, missing resources 404 NOT_FOUND,
conflicts 409 VERSION_CONFLICT and oversized bodies 413 PAYLOAD_TOO_LARGE. Structured
errors use the existing detail envelope and preserve a valid auto request_id after strict
parsing. Unexpected server faults return an empty 500, without inventing a new shared
error code or exposing SQL, paths, source text or URLs. Unknown auto outcomes/request
ledger and HTTP inference are not implemented; auto never saves an evaluation in T05.

Manual saves validate exact evidence against the pinned source/checklist, compute with
T04, and persist original answers, ScoreResult and scoring_version in one short transaction.
No latest-version lookup occurs during save or history reads. Before any review,
final_answers/final_score equal the originals, appeals is empty and review_status is
evaluated. T06 derives the final result from separate decisions as described below.

`StorageApiTest` runs real HTTP against temporary SQLite files, tests rollback, two
concurrent applications updating the same checklist, pool connection replacement,
chunked limits and application restart. `FoundationTest` also uses a temporary file DB.
No automated JUnit test reads DEV/CONTROL or launches Python ML.

```bash
./server/mvnw -f server/pom.xml clean verify
python3 server/src/test/python/scoring_reference.py --check
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
```

The optional local packaged-JAR smoke script creates an isolated private temporary DB,
binds a free loopback port, checks synthetic GET/POST/PUT/manual/501 flows, and restarts
only its own process. With `--dataset` it also imports that local file, checks every stored
source and prints aggregate counts only. It performs no external network requests:

```bash
python3 server/src/test/python/storage_smoke.py
python3 server/src/test/python/storage_smoke.py --dataset data/dev/invoke.json
```

## T06 appeals and review

The existing ML contract 2.0.0, shared fixtures and `cqa-score/1` mathematics are unchanged.
These routes belong exclusively to the Java domain API:

| Route | Request and response |
|---|---|
| `POST /api/evaluations/{id}/appeals` | `{criterion_id,comment}`; 201 with the persisted appeal |
| `POST /api/appeals/{id}/resolve?expected_revision=N` | `{decision,reason,replacement}`; 200 with the complete updated EvaluationView |
| `GET /api/evaluations/{id}` and list | Original snapshot, derived final answers/score, full appeals, review_status and review_revision |

Comment/reason must be nonblank and at most 3,000 Unicode code points; text is preserved.
Strict JSON parsing rejects extra fields, wrong types and duplicate keys. Unknown resources
return 404 NOT_FOUND; invalid payloads/criterion/evidence return 422 INVALID_INPUT.

**Resolve requires `expected_revision` in the query**, obtained from the evaluation GET.
It is a nonnegative signed-64-bit integer. Missing/invalid values return 422; a stale value,
duplicate open appeal or already resolved appeal returns 409 REVIEW_CONFLICT with no writes.
The evaluation revision begins at 0 and increments for every successful create or resolve,
including creation of an appeal on another criterion. The client must reload the evaluation
after a conflict and reconsider its decision; it must not blindly replay with a newer number.
This is an intentional Java write-API compatibility requirement. Legacy JSON body shapes
are preserved; no expected_revision field is added to Python/ML DTOs or shared schemas.

Create returns id, evaluation_id, criterion_id, comment, status, decision, reason,
replacement, created_at, resolved_at, created_revision and resolved_revision. Pending
decision fields are null. Read the evaluation to obtain its current aggregate revision.
History is ordered by created_revision; changes are applied by resolved_revision, independent
of timestamps. If any appeal is open, review_status is appealed; with only resolved appeals
it is reviewed; without appeals it is evaluated. Resolved changes remain effective while
another appeal is open.

Confirm requires null replacement (omission also means null) and confirms the **current**
answer, including prior changes. Change requires a full existing CriterionAnswer for exactly
the appealed criterion. T04 validators check the complete final answer set and exact evidence
against the immutable source and exact historical checklist. Only resolved changes replace
answers. Arbitrary criterion IDs, allowed N/A exclusion, independent critical flags and
HALF_UP scoring are supported. Original answers/score/version/origin are never updated or
recomputed. An unsupported stored scorer version returns an explicit 409 REVIEW_CONFLICT
message, before decoding its score or attempting any recalculation; no fallback is used.

Storage initialization adds only `evaluation_reviews` (evaluation_id FK, revision) and
`appeals` (evaluation FK, criterion, comment, status, decision/reason/replacement JSON,
timestamps and creation/resolution revisions), their indexes and history guards.
No existing T05 table is altered, copied, dropped or backfilled. All old immutable triggers
remain intact. An old evaluation has implicit revision 0 until its first appeal creates a
review row. Initialization is idempotent; legacy Python databases are never migrated.
On a normal application launch the additive schema runs against the configured Java DB;
all automated T06 checks use temporary files, never the user's persistent DB.

A partial unique SQL index permits one open appeal per evaluation/criterion. The same
criterion may be appealed again after resolution. Conditional updates check affected rows;
revision CAS and appeal writes commit in one IMMEDIATE transaction. Failed validation,
duplicates and failed writes roll back everything, including lazy revision-row creation.
SQL triggers prevent deletion or rewriting of completed history. Consistent GET projections
also use the existing transaction template: no revision/history mismatch, but reads briefly
reserve the SQLite writer. This local-demo tradeoff can limit throughput for large histories.
Correctness does not depend on one Hikari connection or a Java process lock.

`ReviewApiTest` covers strict payloads, scoring/evidence, re-appeals, original bytes, pinning,
two independent Spring applications sharing a SQLite file, stale writes, injected SQL
failures and restart. `ReviewMigrationTest` boots over a frozen T05 schema populated with
65 **synthetic** sources and checks every original row and immutable trigger. The T06
packaged-JAR smoke also closes/restarts its own JVM from another working directory:

```bash
python3 server/src/test/python/review_smoke.py
```

No real DEV/CONTROL data, provider calls, ML HTTP integration, reviewer UI or authentication
is involved. Exact-substring grounding cannot establish whether a human decision is
semantically justified. T06 was closed after Nurtas's review on 2026-11-07, as reported by
Farhat; Nurtas did not independently rerun the 5,841 passing JUnit tests. See plan.json.

## T07 organizer fetch and minimal UI

The Java-served page now accepts group_id, shows loading/success/safe errors, accepted
record count, and saved conversation counts grouped by dataset. It uses same-origin
`POST /api/datasets/fetch` and `GET /api/conversations`; external text is rendered with
textContent. T12 retains this workflow in the Загрузка данных screen.

```text
POST /api/datasets/fetch
Content-Type: application/json

{"group_id":"DEV"}
```

Success200 returns the same `Dataset.ImportResult` as upload: dataset_group_id,
imported_records, languages and channels. imported_records counts accepted input rows,
including identical reimports, not only newly inserted rows. The UI refreshes the stored
count separately. Request JSON is strict; group_id must be nonblank and at most200 Unicode
code points (an engineering limit, not an organizer rule). The browser cannot supply a URL.

Configure **only the Java process** with `CQA_ORGANIZER_URL` (Spring property
`cqa.organizer-url`): the complete private signed GET URI supplied by the organizers.
For an interactive Bash launch, enter it without putting it in shell history or arguments:

```bash
read -r -s -p 'Organizer URL: ' CQA_ORGANIZER_URL
export CQA_ORGANIZER_URL
java -jar server/target/freedom-cqa-server-0.1.0.jar
```

Never commit the value, put it in static files, or enable HTTP wire logging with credentials.
Absent configuration leaves startup/health/manual import available; fetch returns503.
URLs must be absolute ASCII HTTP(S) URIs with non-ASCII characters percent-encoded,
without user-info or fragments. Malformed/unsupported URLs fail safely on fetch.

The local Student Guide v3 confirms GET with group_id. The adapter replaces its value
with UTF-8 query encoding, or appends it if absent. Encoded group_id keys are recognized;
duplicate group_id keys collapse to one. Every other query segment stays byte-for-byte
unchanged: order, case of percent escapes, plus signs, duplicate keys and empty values.
No other query parameter is invented or required by the adapter. Retaining a signature
does **not** guarantee that it authorizes another group:401/403 are reported honestly.
All redirects are rejected, including same-origin redirects. No request body, transcript,
audio locator or provider input is sent upstream; only the GET query is sent.

`CQA_ORGANIZER_CONNECT_TIMEOUT_MS` defaults to3000 (bounded1..5000).
`CQA_ORGANIZER_RESPONSE_TIMEOUT_MS` defaults to10000 (bounded1..30000), including headers
and the entire streamed body. The UI waits up to35s, then asks to refresh before retrying.
The adapter makes one application-level request with no application retry loop. A bounded
body subscriber rejects responses over16MiB, including chunked responses without a length;
non-identity Content-Encoding is rejected. Non-success bodies are discarded, not relayed.

Fetch and upload share the T05 parser/defaults and ConversationService.importDataset.
Optional absent error/audio_url keep the existing defaults; explicit nulls and unknown
fields remain strict. Envelope success/error/count/unique IDs/types are validated and the
returned dataset_group_id must exactly match the request. The HTTP wait has no SQLite
transaction. The existing short atomic import preserves all source fields and positional
IDs, accepts identical reimports and returns409 VERSION_CONFLICT for changed source data.
DEV/CONTROL use independent composite identities. The user's persistent DB was not used
for T07 verification; test DEV/CONTROL labels contain only newly synthesized data.

Organizer errors are **Java-only**, scoped to this new domain endpoint. They use the familiar
detail envelope (`code`, fixed safe `message`, `retryable:false`, `request_id:null`) with the
codes below. They are not ML errors and are not additions to shared contract2.0.0 schemas.
Validation422 INVALID_INPUT and storage409 VERSION_CONFLICT retain their existing meaning.

| HTTP | Java organizer codes |
|---|---|
| 503 | ORGANIZER_UNCONFIGURED, ORGANIZER_CONFIGURATION_ERROR, ORGANIZER_UNAVAILABLE, ORGANIZER_RATE_LIMITED |
| 504 | ORGANIZER_TIMEOUT |
| 404 | ORGANIZER_NOT_FOUND (upstream404) |
| 502 | ORGANIZER_ACCESS_DENIED (upstream401/403), ORGANIZER_REDIRECT_REJECTED, ORGANIZER_UPSTREAM_ERROR |
| 502 | ORGANIZER_INVALID_RESPONSE, ORGANIZER_GROUP_MISMATCH, ORGANIZER_RESPONSE_TOO_LARGE |

Responses/logs never include upstream URL, credentials, raw bodies or transcripts. The UI
uses its own fixed allowlist of error messages, so even a proxy body is not displayed.
No automatic retries, Groq calls or Java-to-Python ML requests are introduced.

`OrganizerApiTest` runs against a local synthetic HTTP server, with actual Spring HTTP
and temporary SQLite. `OrganizerUriTest` covers raw-query replacement and invalid URI
configuration. The standalone smoke runs the packaged Java process with a synthetic
organizer, imports6 unique conversations (3 each under synthetic DEV/CONTROL), checks
idempotency/rollback/exact source preservation and closes/restarts Java on the same temp DB:

```bash
python3 -B server/src/test/python/organizer_smoke.py
# Optional: keep that verified synthetic app alive for manual/browser form checks.
python3 -B server/src/test/python/organizer_smoke.py --serve
```

Real organizer GET: **NOT RUN**; it requires explicit permission. Live availability,
signature expiry and access to the organizer's CONTROL group remain unverified. Nurtas
approved T07 after ed21ee0 on 2026-11-07, as explicitly relayed by Farhat in chat; PR5 was
merged as 22d5b21. This is not claimed as a separate GitHub Review.


## T12 Vanilla workspace

Five screens: overview, conversations, checklist editor, results/review, and dataset fetch
or file import. Conversation search and group/language/channel filters run over Java's
current list. Transcript text, Unicode, role, timestamp and message_id remain exact;
long messages wrap. Evidence opens the pinned transcript and focuses an exact message ID,
including when timestamps/text repeat. Source audio offers an HTTP(S) link and a player
that is connected only by explicit user action. No offsets, audio analysis or successful
playback are invented.

The global checklist picker selects key and explicit version (blank means latest).
`GET /api/checklists` supplies latest versions only; historical versions are read by their
number. Sections, arbitrary criterion IDs, wording, binary/scale/flag, weights, levels and
N/A are editable. Each PUT uses an observed latest `expected_version`, even when the draft
started from history. A 409 keeps the draft; **Обновить latest для черновика** explicitly
refreshes its base without resubmitting or overwriting draft fields. Java validates all
composition rules. Non-scale criteria send an empty levels list; flag requires zero weight
and no N/A. Decimal inputs use a period and JSON number notation, not locale commas.

`json.js` retains JSON numeric lexemes as opaque Decimal values, including BigInteger
versions/revisions and long BigDecimal values. Serialization emits numeric JSON tokens,
never numeric strings or silently rounded Number values. Numeric equivalence is used only
to select configured scale levels (7 and 7.0); no score calculation happens in JavaScript.

Manual evaluation requires an explicit answer and explanation for every criterion and at
least one exact, nonblank quote per answer. Choose a source message, then copy its text or
a selected exact fragment; no quote is generated automatically. Java validates, scores and
persists; results are read back with GET. Original/Final show all emitted score fields,
section totals, N/A, critical IDs, contract/scorer versions and review revision. Expand a
criterion for weights, raw/earned points, explanation and evidence. `earned_points` is the
server's normalized contribution; clients never sum rounded rows.

Review uses the evaluation's pinned checklist and source. Create appeal sends criterion_id
and comment; confirm/change sends the loaded review_revision as expected_revision. A 409
reloads the evaluation, retains the decision draft and never replays the POST. If another
reviewer already closed the appeal, its unsent draft is shown separately and cannot resolve
that closed appeal. Current results always come from Java's original/final projection.
T13 Java→Python inference and T14 real-AI appeal/review remain unimplemented by this task.

Modules have separate ownership: api/json transport, state/drafts, safe DOM helpers,
datasets, conversations, checklists, answers, evaluations and review; app.js coordinates
screens. Reads have AbortController deadlines plus generation checks. Mutations have no
automatic retries; pending writes lock context switching and prevent double submits.
An unknown network outcome retains the draft and blocks resending, even after switching
context, until the user explicitly acknowledges checking saved records. This is a local
manual reconciliation aid, not an exactly-once request ledger (T13).

Drafts are scoped by conversation/checklist version or evaluation/appeal and kept in memory
across screen/context changes. beforeunload warns about unsaved drafts/pending/unknown writes.
They are deliberately **not durable across reload/close**, and browsers control whether
beforeunload prompts appear. There is no localStorage/sessionStorage, analytics or transcript
logging. External text uses textContent; errors use fixed messages rather than raw bodies.
The UI loads complete lists, without server pagination or transcript virtualization; very
large datasets/histories can need a later performance task. Client substring checks do not
establish semantic relevance. External audio availability/CORS is unverified.

### Reproducible checks

```bash
./server/mvnw -f server/pom.xml clean verify
python3 server/src/test/python/scoring_reference.py --check
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
python3 -B server/src/test/python/workspace_smoke.py
python3 -B server/src/test/python/organizer_smoke.py
python3 -B server/src/test/python/review_smoke.py
# Optional developer tests; Node22 is not required to build or run the application.
node --experimental-default-type=module server/src/test/js/workspace.test.mjs
```

Restore the isolated contract validator using `contracts/README.md` if needed.
The java-workspace CI job runs Java, scoring reference, the dependency-free JS tests and
synthetic packaged HTTP smokes. Existing ML CI independently validates the 72 contract
fixtures. CI does not run a real browser; a Java build is not proof of UI execution.

### Isolated browser / manual smoke

```bash
python3 -B server/src/test/python/workspace_smoke.py --serve
```

This script first verifies the actual JAR's HTTP flows, then prints **WORKSPACE** and
**BROWSER TESTS** loopback URLs. It owns a temporary SQLite, sets Organizer URL empty, uses
only synthetic RU/KZ/EN text and restarts only its own JVM. It does not open the user's DB.
Open WORKSPACE for manual checks, or BROWSER TESTS and click **Run browser regression**.
The test harness is outside production static assets; its routes exist only in the local
Python test proxy. It tests real Java persistence; only race/error scenarios inject controlled
browser transport delays/failures. No fake success results enter the production UI.

Manual walkthrough:

1. Open **Диалоги**, filter group UI-SYNTHETIC, language KZ/RU/EN and channel. Search by ID.
   Select RU, verify m0001–m0005, repeated 00:01, operator/client/bot/system, literal HTML and
   exact newlines/Unicode. EN is a call with ISO timestamps and an unloaded synthetic audio
   link; do not expect its example.invalid audio to play.
2. Pick `ui-synthetic`, version `1`. In **Чек-листы**, inspect sections and arbitrary IDs.
   Create a new key with a weighted criterion and valid sections; edit levels/wording/N/A,
   save v2, then open v1 and verify history. Saving from history appends after latest.
3. In RU manual evaluation, set WELCOME_X=N/A, CLARITY_X=7, RISK_X=yes. For each, enter an
   explanation, add evidence, choose m0003 and **Взять текст сообщения**. Save once. Expect
   origin manual, overall70, applicable_weight15, raw_points10.50 for CLARITY_X and an
   independent critical flag. Expand Original/Final criteria and jump to m0003.
4. Appeal WELCOME_X and confirm with a reason. Appeal CLARITY_X, choose change and level0,
   retain grounded evidence, and save with a reason. Original remains70, Final becomes0.
   A second window can change review revision; submitting the stale first window must show
   REVIEW_CONFLICT, preserve its draft and require an explicit new decision.
5. Edit a manual/checklist/review draft, switch contexts and return. Verify isolation and
   retention. Double-click submit: one write only. For checklist409, create a competing
   version in another window; refresh latest explicitly, inspect the retained draft, save.
6. In the smoke terminal type `restart` and press Enter. Refresh the browser to verify stored
   checklist versions, evaluations and appeal history survive. Unsaved browser drafts are
   not expected to survive a page reload. Press Enter with an empty line to stop/clean up.
7. At ~390px width check navigation, forms and long-message wrapping. No transcript HTML
   should create image/script elements. AI remains marked unavailable until T13.

Real Organizer GET, real DEV/CONTROL→Groq, audio playback against external providers and
real AI→review were **NOT RUN**. This scope tests manual Java workflows; it does not close
T13/T14 or establish full official checklist-PDF verification.

## T13 Java ML integration

The Java part uses the existing `EvaluationRequest`, `EvaluationResult`, `ContractError`,
`AutoRequest` and evaluation view shapes. The shared contract remains **2.0.0**, Python's
route remains **POST /v1/evaluate**, and Java alone scores/persists. No ML source, schemas,
fixtures, seed or scoring math changed. Local fake HTTP tests establish transport and
persistence behavior, not real model quality or successful Python/provider integration.
The T12 instructions above describe the manual baseline; the AI panel now supplements it.

Java configuration (no provider credentials):

| Variable / Spring property | Default / bounds |
|---|---|
| `CQA_ML_URL` / `cqa.ml-url` | Empty:501; intended value `http://127.0.0.1:8001/v1/evaluate` |
| `CQA_ML_CONNECT_TIMEOUT_MS` / `cqa.ml-connect-timeout-ms` | 3000; clamped1..3000ms |
| `CQA_ML_RESPONSE_TIMEOUT_MS` / `cqa.ml-response-timeout-ms` | 70000; clamped1..70000ms, headers plus entire body |

The first release accepts only explicit HTTP loopback127.0.0.1 URLs with a port and exact
`/v1/evaluate` path; no credentials, query, fragment, redirects or proxy. Startup/health
make no network requests. Missing/invalid URL returns501 without a ledger entry or inference.
Connect refusal maps to503 EVALUATOR_BUSY; connection loss after sending is conservatively
unknown502; deadline is unknown504. Java makes one POST, with no application retry. Python
continues to own its maximum two provider attempts. Browser timeout is75s and never replays.
Request/response bounds are1MiB/256KiB, including streamed bodies and strict UTF-8 decoding.

**First live phase safety gate:** Maven packages the six existing
`ml-service/tests/fixtures/*/request.json` inputs into the JAR. Java compares the entire
conversation projection AND checklist to a bundled fixture pair, excluding only request_id.
The SYNTHETIC group label alone grants nothing. IDs, original text/order/roles/timestamps,
language/channel, checklist wording/weights/levels/version must match. Modified checklist
versions still work in the manual T12 workflow; automatic evaluation rejects them with503
PRIVACY_POLICY_UNCONFIGURED until a separately reviewed policy expansion. This intentionally
stricter Java policy also prevents sending arbitrary private text through checklist fields.
No configurable file path or environment flag can turn the gate into a group-name allowlist.
Audio URLs, import metadata and credentials are absent from the DTO projection.

`POST /api/evaluations/auto` takes the existing four fields: UUID request_id, conversation_id,
checklist_key, checklist_version. It pins immutable source/checklist before HTTP. After strict
shape, identity, complete answers/kind/levels/NA and exact-substring evidence validation
(PRODUCTION mode, attempt_count>=1), Java calculates `cqa-score/1` and writes `origin=model`.
Original answers/score are immutable and remain compatible with existing T06 review. SDK
allowlisted diagnostics and the full pinned request are stored in the private ledger;
the existing public evaluation view shape is preserved. Java does not trust upstream error
messages: it validates status/code/UUID, then returns a fixed safe message.

### Durable request lifecycle

`GET /api/evaluation-requests/{request_id}` returns the already documented four fields:
request_id, status, evaluation_id, error. Unknown IDs404; malformed UUID422. Errors contain
only the fixed safe code/message/retryable/request_id detail. Status reads never call Python.

| Stored status | Repeated POST with identical payload | New inference |
|---|---|---|
| pending | 202 + Location status URL | Never |
| succeeded | 200 + saved evaluation (current review projection, immutable original) | Never |
| failed | Original safe error/status | Never |
| unknown | Recorded safe error/status | Never |

A reused UUID with a different conversation/key/version returns409 REQUEST_ID_CONFLICT,
even if that different context does not exist. A short SQLite IMMEDIATE transaction claims
one unique UUID before any HTTP. Network wait holds no transaction/connection. Success
inserts the evaluation and terminal ledger state atomically; an injected finalization error
rolls back both and records unknown. Ledger identity/context and terminal states cannot be
updated or deleted. Preflight shape/context/privacy/configuration errors occur before claim,
so their UUID status is404 and no network request took place.

**One Java application process owns an ML database.** On startup, previously pending ledger
entries become unknown; they are never submitted again. Do not run multiple Java instances
against an active ML database: a second startup cannot distinguish another process's active
work from a crash. No distributed lease/queue is introduced. Timeout/crash can leave Python
or the provider running; exactly-once billing is not promised. A new UUID is a deliberate
new attempt and can incur another charge. Python has no result lookup endpoint in2.0.0,
so an unknown result cannot automatically be recovered from that service.

The AI panel keeps manual drafts intact. It shows request_id before POST, loading/error/status
and the saved result. After any uncertain response use **Проверить AI статус**; after reload
use **Восстановить последний AI запрос**, or paste a saved UUID. Only the last opaque UUID
is stored in sessionStorage, with no transcript, checklist or credentials. If browser storage
is unavailable, copy the visible UUID. GET reconciliation, reload and context changes never
start inference. A new attempt requires a checked status and acknowledgment of possible
repeat cost, then an explicit new-UUID action and an explicit AI click. Pending IDs cannot
start a new attempt through that control. A new tab does not have the previous tab's UUID;
use the visible ID or stored evaluation history for reconciliation.

### Reproducible isolated verification

```bash
./server/mvnw -f server/pom.xml clean verify
node --experimental-default-type=module server/src/test/js/workspace.test.mjs
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
python3 -B server/src/test/python/auto_smoke.py
# Optional actual browser: open the printed BROWSER TESTS URL and click Run AI browser regression.
python3 -B server/src/test/python/auto_smoke.py --serve
# Existing manual workspace regression remains separate:
python3 -B server/src/test/python/workspace_smoke.py --serve
```

The auto smoke starts only its own fake ML server and packaged JAR with a temporary SQLite,
imports the unchanged `en_public_na` fixture via the real Java APIs, checks model-origin
score100, invalid evidence, duplicate/conflicting UUIDs and unknown timeout, then kills its
own Java while a POST is pending and verifies recovery/no replay after restart. It never
starts Python ML, reads provider secrets or calls Groq. Browser harness/control routes exist
only in the test proxy, outside production static resources. CI runs the same synthetic
packaged smoke; browser runs are local and are reported separately.

### Further live runs require separate agreement

The first Java live E2E is complete: the saved own-synthetic kz_public_na request has
provider groq, model openai/gpt-oss-20b, prompt cqa-dynamic/3, attempt_count1 and Java
original score100. Farhat reported peer approval; this is chat evidence, not a claimed
GitHub Review. PR #8 was merged as ee63dc9f60362570048e398884e61c37ea4bc904.
The T14 run inspected this ledger read-only and did not make another live call.

Before any further live call Nurtas must explicitly confirm service readiness, selected provider/model,
synthetic-only policy, quota/budget/free-plan settings and the allowed attempt count. Secrets
stay exclusively in Python; do not paste or commit them. Start one Python worker according
to ml-service/README.md and confirm `/health` configuration without a model probe. Agree on
one exact published fixture (start with en_public_na), inspect its source and checklist, and
import those exact values into a separate temporary Java SQLite. Then configure Java's
CQA_ML_URL to the loopback8001 route and explicitly authorize one UI request/new UUID.
Check real diagnostics, answers/evidence relevance, Java score and persisted snapshot together.
Record every authorized run separately from fake-server results. The completed T13 run
does not authorize new Groq calls or expand SyntheticPolicy. Real DEV/CONTROL and external
audio remain out of scope for this workflow.

## T14 model appeals and dynamic manual checklist regression

The existing Java review engine and Vanilla UI support model-origin evaluations without
new endpoints or production-code changes. T14 adds ModelReviewApiTest (10 cases) and a
seven-scenario browser regression. The original evaluation row and successful request
ledger stay unchanged; final answers replay resolved decisions using the pinned v1
checklist and cqa-score/1. Confirm records a reason without replacing the current answer.
Change requires a complete, grounded replacement of the appealed criterion. Re-appeals
preserve earlier decisions. A stale expected_revision returns409 without any write;
the UI retains the draft and requires an explicit retry after rereading the revision.

Covered workflow: original100 → clarity change to level4 → final60, with N/A excluded
and applicable_weight75. Changing the separate critical flag does not change that total.
The flag toggles and reduced clarity answer are deliberate workflow probes, not human
gold labels or claims about the model's semantic accuracy. Invalid reason, forged quote,
unknown message, wrong criterion, unsupported level/N/A and invalid flag value fail
atomically. Competing reviewers produce exactly one winner for a shared revision.

Through the UI, append JURY_EXTRA_42 (binary, weight25) to synthetic-local as v2. A manual
v2 evaluation with that answer=no scores75; the reviewed model v1 keeps original100/final60
and four criteria. Historical v1 and both evaluations survive a JVM restart. Source text,
reason and criterion title remain plain text; original and replacement evidence jump to
the exact message ID. No checklist, source fixture, scoring rule or ML prompt is changed.

Reproduce on a **fresh** temporary fixture server for each browser suite:

```bash
./server/mvnw -f server/pom.xml clean verify
node --experimental-default-type=module server/src/test/js/workspace.test.mjs
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
python3 server/src/test/python/scoring_reference.py --check
GROQ_API_KEY= GROQ_FREE_PLAN_CONFIRMED=false PYTHONPATH=ml-service \
  ml-service/.venv/bin/python -B -m pytest -q -p no:cacheprovider ml-service/tests
python3 -B server/src/test/python/auto_smoke.py --serve
```

Open its printed **T14 BROWSER TESTS** URL and click **Run T14 browser regression**.
It drives actual Vanilla forms and Java APIs, with fake ML used only to prepare a saved
model evaluation. The test proxy provides a restart control for its own disposable JVM;
none of these routes are packaged in production. Expect seven PASS lines. The suite
changes its temporary v1 evaluation and appends v2, so restart the fixture server before
rerunning it or running the separate T13 browser suite. Press Enter in the terminal to
remove the temporary database and close the owned processes. Existing T12 regressions
remain available through workspace_smoke.py --serve.

On 2026-11-08 the same seven browser scenarios also passed against an isolated SQLite
backup of the existing **real Groq kz_public_na evaluation**, after exact fixture matching.
The original database was opened read-only and its SHA256 remained unchanged. No new
ML HTTP call occurred; the copied evaluation/ledger retained the original live provenance.
This verifies review of a real saved AI result, not a new live model E2E. Only sanitized
identity/diagnostic evidence is recorded in plan.json; no database or raw model output is
committed. Automated Java/CI tests remain synthetic and provider-free.

**Remaining T14 blocker:** arbitrary v2 AI returns503 PRIVACY_POLICY_UNCONFIGURED before
any ML request or ledger claim. This is verified, not bypassed. To complete dynamic ML
acceptance, Farhat and Nurtas must agree a new own-synthetic conversation+checklist fixture,
review its exact contents and permission to expand the fixture set, and separately approve
the provider/model, attempt budget and live run. Existing fixtures and SyntheticPolicy are
unchanged. T14 stays in_progress until that scenario and peer review are complete.
