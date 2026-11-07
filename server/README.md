# Freedom CQA — Java foundation and scoring

This module implements application liveness, a static Vanilla JS start page (T03), and
strict contract DTOs/validation plus a pure deterministic scoring engine (T04).
There is no evaluation REST flow, checklist CRUD, appeal, dataset import or ML integration yet.
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

SQLite uses `jdbc:sqlite::memory:` with one Hikari connection to make JDBC autoconfiguration
start without creating data files. No schema, migrations or repositories are implemented.
This is intentionally ephemeral; durable SQLite configuration belongs toT05.

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
