# Freedom CQA — Java foundation and scoring

This module implements application liveness and a static Vanilla JS start page (T03),
strict contract DTOs/validation and deterministic scoring (T04), and persistent SQLite,
JSON import, versioned checklist REST and manual evaluation/history (T05), plus
immutable evaluations and atomic appeals/review (T06), and organizer dataset fetching
with a minimal Vanilla group_id form (T07, pending peer review).
Java-to-ML HTTP integration is not implemented.
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

`src/main/resources/static/` contains index.html, styles.css and the native ES module
js/app.js. It fetches `/api/health` on load and explicit retry, uses textContent for response
text, and handles HTTP failures, malformed health responses, network errors and a5s timeout.
Future modules can extend the static directory without a bundler. Planned features are
labelled as unimplemented; no fake evaluations or customer statistics are displayed.

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

All routes use the Java server and JSON. The browser remains the T03 start page.

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
textContent. It is not the T12 conversation viewer, checklist editor or review dashboard.

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
signature expiry and access to the organizer's CONTROL group remain unverified. T07 awaits
its own peer review; T06 approval does not imply approval of the new organizer boundary.
