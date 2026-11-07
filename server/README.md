# Freedom CQA — Java foundation and scoring

This module implements application liveness and a static Vanilla JS start page (T03),
strict contract DTOs/validation and deterministic scoring (T04), and persistent SQLite,
JSON import, versioned checklist REST and manual evaluation/history (T05).
Appeals, organizer API fetching and ML HTTP integration are not implemented.
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
No latest-version lookup occurs during save or history reads. final_answers/final_score
currently equal the originals, appeals is empty and review_status is evaluated; there is
no reviewer decision. T06 can add separate review tables without rewriting originals.

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
