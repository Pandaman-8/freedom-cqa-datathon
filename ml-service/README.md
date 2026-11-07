# Freedom CQA — Python ML service

Independent FastAPI service for T08/T09/T10, contract **2.0.0**, localhost **8001**.
Python 3.11+; tested here on Python 3.14. Java owns persistence, request-status
reconciliation and deterministic scoring. This service returns model answers and
grounded evidence, never authoritative totals. No dependency on `backend/`.

## Run from repository root

```bash
python3 -m venv ml-service/.venv
ml-service/.venv/bin/python -m pip install -r ml-service/requirements-dev.txt
cp ml-service/.env.example ml-service/.env
```

Edit the private `ml-service/.env`: set `GROQ_API_KEY` and, **only after verifying
that the Groq organization is on Free Plan**, set `GROQ_FREE_PLAN_CONFIRMED=true`.
The default candidate is `openai/gpt-oss-20b`; `openai/gpt-oss-120b` is also supported.
Do not paste secrets into chat or commit `.env`. No paid mode is enabled.

```bash
ml-service/.venv/bin/python -m uvicorn app.main:app \
  --app-dir ml-service --env-file ml-service/.env \
  --host 127.0.0.1 --port 8001 --workers 1 --no-access-log
```

Use **one process/worker**: the in-flight limit is process-local. `GET /health`
performs no provider call; 200 means configured and idle, 503 means unavailable or
busy. It does not verify credentials, account billing, quotas or remote availability.
Without a key/Free Plan confirmation, evaluate returns honest **501
EVALUATOR_UNCONFIGURED**, never synthetic successful answers.

```bash
curl -i http://127.0.0.1:8001/health
curl -i --max-time 75 http://127.0.0.1:8001/v1/evaluate \
  -H 'Content-Type: application/json' \
  --data-binary @ml-service/tests/fixtures/kz_public_na/request.json
```

A successful response contains identity echoes, `answers` and `diagnostics`, exactly
as in the published schema. `answers[].value` is a configured discrete level, not
a weighted score. For a protected-action/insult case use
`ml-service/tests/fixtures/kz_protected_violation/request.json`; the changed rubric
case is `ml-service/tests/fixtures/en_protected_violation/request.json`.

The curl fixtures have a fixed request UUID for a single manual smoke. Generate a
new UUID for each intentional new evaluation. This stateless ML service does not
deduplicate calls or persist statuses; Java owns the request ledger. A repeated
direct curl call can run inference again. Never auto-replay a timed-out POST.

Explicit live smoke, once the free account is configured:

```bash
ml-service/.venv/bin/python ml-service/scripts/smoke.py --case kz_public_na
# All six, at most twelve provider attempts total:
ml-service/.venv/bin/python ml-service/scripts/smoke.py
```

The script sends only bundled own synthetic requests to localhost, uses fresh UUIDs,
prints safe metadata and label comparison counts, and stops on an HTTP failure.
Its expected labels are **proposals awaiting human review**, not approved gold.
There is no live model call in pytest or CI.

For a diagnostic probe capped at **one provider attempt**, including no repair/retry:

```bash
PYTHONPATH=ml-service ml-service/.venv/bin/python ml-service/scripts/live_once.py
```

This starts an isolated temporary localhost server on a free port, sends only
`kz_public_na`, prints status/usage without answers, and stops the server. An existing
service on :8001 is untouched. Restart that service separately after code changes.

## Validation and failure behavior

- Strict UTF-8 JSON rejects duplicates, trailing text and nonfinite/overflow numbers.
  Published Draft 2020-12 schemas are loaded directly from `../contracts/`; deploy
  from the repository with that directory present. Pydantic forbids extra fields
  and coercion, while preserving the contract's integer equivalence `2.0 == 2`.
  Runtime floating-point parsing follows the published Python fixture tool's
  binary64 policy; this is not proof of every Java BigDecimal edge case.
- Independent context checks enforce complete criterion sets, composition, discrete
  levels, N/A rules, identity echoes, positional IDs and exact unnormalized evidence.
  Schema-valid evidence does not prove semantic relevance; human review remains needed.
  Text/order/timestamps are preserved, including repeated times and IDs beyond m9999.
- Dynamic prompt includes the full checklist and original conversation. Transcript
  instructions are treated as evidence, not authority. No eight-criterion assumption.
  Unsupported audio-only/factual judgments must not become invented evidence or N/A.
  All results carry `DOMAIN_FACT_UNVERIFIED` because no company KB is provided;
  voice transcripts also carry `AUDIO_NOT_ASSESSED`.
- Groq GPT-OSS requests use `json_schema` with `strict: true`. An internal decoding
  schema derives the same field shapes from the published schema and expresses
  answer/value pairing with `anyOf`, using Groq's supported subset. This is only a
  generation aid: the unchanged full published schema, Pydantic and context checks
  still decide acceptance. No markdown extraction or silent answer correction.
  GPT-OSS uses `include_reasoning=false`, `reasoning_effort=low`; no unsupported
  `reasoning_format` parameter. The prompt retains literal RU/KZ text and enumerates
  each configured criterion's allowed answer/value pairs and all source message IDs.
- Connect ≤5s, each complete streaming read ≤30s, full evaluation ≤65s, at most two
  attempts total, backoff ≤2s. No SDK/HTTP retries below the evaluator. Invalid
  output gets one repair with safe rule codes. Timeout/429/5xx may retry within the
  same budget. Auth, permission, context overflow and missing config do not retry.
  Retry-After is never shortened; if it exceeds budget, return the mapped error.
- Request ≤1 MiB, upstream/result ≤256 KiB, ≤100 criteria. No truncation. Model output
  budget is 4096 tokens; large rubrics may exceed it and fail explicitly. One evaluation
  in flight; others get 503. Cancellation does not prove provider inference stopped.
- Usage sums all attempts, including rejected completions. Missing usage produces null
  aggregates/cost. Confirmed free usage costs 0; it is not a paid-tier estimate.
  No prompts, answers, raw provider exceptions, keys or customer text are logged.

Local `ml_service.validation` warnings now distinguish JSON parsing, JSON Schema,
Pydantic, criterion completeness, answer kind, discrete values, N/A, evidence,
model identity, truncation, refusal and malformed provider envelopes. Each warning
contains only a static category/code, attempt number, known safe criterion/message
IDs (otherwise null), and numeric answer/evidence indices. No quotes, explanations,
raw validation messages, provider bodies or reasoning are logged. Repair receives
the same sanitized coordinates. The public HTTP error JSON is unchanged.

Example local warning payload (not an additional HTTP response field):

```json
{"category":"evidence_grounding","code":"EXACT_EVIDENCE","criterion_id":"LOCAL_GREETING","message_id":"m0002","attempt":1,"answer_index":0,"evidence_index":0}
```

`PROVIDER_TRUNCATED` means the provider reported `finish_reason=length`, not a quote
failure. `SCHEMA_INVALID` means the full canonical schema failed; `EXACT_EVIDENCE`
means the selected quote is not a nonblank exact substring of its source message.
Neither logs nor a substring match establish semantic correctness.

Only exact conversations registered in the bundled synthetic fixtures are admitted;
changing just the dataset label cannot authorize real transcripts. Checklist edits
are accepted dynamically, but must also contain no private data. To add **own
synthetic** text, add a reviewed synthetic request in `tests/fixtures/<case>/request.json`
and restart. This is not a production access-control boundary. Real-data mode is
intentionally unavailable pending policy approval.

## Tests and acceptance limits

```bash
PYTHONPATH=ml-service ml-service/.venv/bin/python -m pytest -q ml-service/tests
```

Tests exercise all 72 published fixtures through this service's own validators,
six RU/KZ/EN scenarios, HTTP envelopes, exact evidence, changed criteria, mocked
provider transport, usage accounting, deadlines, cancellation and concurrency.
Injected model replies exist **only in tests**. For the separate shared artifact
drift check, use the isolated tooling environment from `contracts/README.md`.

See [provider review](config/provider-review.md) for sources, pricing and data policy.
Live model quality/free-account checks, human gold review and Java↔Python integration
remain unverified. T02 joint acceptance is not inferred; `plan.json` and shared files
are unchanged. This work does not claim completion of every T08/T09/T10 acceptance gate.

Initial verification recorded on 2026-11-07 (Python 3.14.8), before the live-output fix:

- `PYTHONPATH=ml-service /tmp/freedom-cqa-ml-validation/bin/python -m pytest -q ml-service/tests`
  → **149 passed, 1 warning in 2.22s**. The warning is Starlette's deprecation of
  its httpx-based TestClient, not a failed assertion. TestClient needed execution
  outside the restricted sandbox because its cross-thread event loop stalled there.
  No external provider calls occurred.
- `/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py` in the
  separate tooling environment → **4 schemas, no plan drift, all 72 fixtures pass**.
- Temporary real Uvicorn process on `127.0.0.1:8001` with the API key explicitly
  cleared: health 503/configured=false; valid synthetic POST 501 with preserved UUID;
  obsolete contract 422; invalid UTF-8 422; request above 1 MiB 413. Server stopped
  after the check. Successful inference HTTP responses were tested with injected
  doubles and a mocked Groq transport, **not a live LLM**.
- `pip check` → no broken requirements. Existing tracked files were unchanged;
  all additions are inside `ml-service/`. No commit, push, merge or reset performed.

Follow-up verification on 2026-11-07:

- Same pytest command: **175 passed, 1 warning in 2.46s**, including regression tests
  for safe validation locations, raw-text/key exclusion, finish reasons, structured
  schema generation without shared-schema mutation, literal Kazakh prompt text,
  exact evidence rejection and the one-attempt probe budget.
- Separate contract validator: **all 72 fixtures pass; no schema/plan drift**.
- Exactly **one live Groq call** through real localhost HTTP using `live_once.py`:
  **HTTP 200**, `openai/gpt-oss-20b`, contract `2.0.0`, four validated answers,
  2485 input / 567 output tokens, estimated Free Plan cost **0 USD**. No retry.
  This confirms this KZ request passed structural and exact-grounding validation;
  it does not establish multilingual accuracy or human-approved gold labels.
- The historical reported 502 cannot be assigned to a specific validator after the
  fact: the previous implementation discarded its reason and no original response
  was available. Confirmed defects were missing diagnostic provenance, merged
  completion failure reasons, and JSON-object-only generation without schema
  enforcement. The successful new probe does not prove which one caused that run.

## T11 integration verification — 2026-11-07

This section records evidence, not a replacement task tracker. The existing
`plan.json` is unchanged; it still records T11 as `planned`. Python technical
acceptance checks below pass. Formal closure additionally requires Farhat's review
and completion evidence in the owner-maintained plan; neither is inferred here.

Three defects were reproduced by six initially failing regression cases and fixed:

1. An asyncio timer cannot run during synchronous code. A late provider completion
   or validation could return HTTP 200 after its 30s/65s limit. Explicit monotonic
   checks now reject late success and prevent another attempt after the total
   deadline, including after a delayed backoff wakeup. The async cancellation timers
   remain. This does not preempt CPU work or guarantee upstream cancellation.
2. An HTTP 400 provider rejection with HTML/invalid JSON or an oversized body was
   misclassified as invalid model output and retried. It now returns safe HTTP 502
   `EVALUATOR_PROVIDER_ERROR` without retry. Explicit `json_validate_failed` repairs,
   timeout/429/5xx retry rules and context/auth mappings are preserved.
3. Valid MIME `application/json; charset="UTF-8"` was rejected. Parameter parsing
   now accepts quoted UTF-8 while still rejecting unsupported encodings/media types.
   JSON parsing, field validation and evidence rules are unchanged.

| T11 acceptance criterion | Verification | Result |
|---|---|---|
| Reject missing/unknown/duplicate criteria, forged/blank quotes, extra fields, duplicate keys and nonfinite numbers | Shared raw fixtures plus `/v1/evaluate` negative model-output tests, including Unicode and numeric types | PASS |
| Shared fixtures through Python transport and Java-facing JSON checks; no fabricated N/A | All 72 fixtures at their proper wire boundaries, independent final-schema checks, changed rubrics, allowed/forbidden N/A, flags, exact identity echoes | PASS on Python side |
| Timeout/429/auth/version/size failures have agreed safe errors and request IDs | Real FastAPI handler + Groq adapter + MockTransport; bounded attempt counts, deadlines, Retry-After, input/output limits, busy recovery | PASS |

Fixture coverage is explicit: all **72** run through application validators.
Additionally, `test_fixture_transport.py` executes **22 request + 4 provider-output**
fixtures through the actual `/v1/evaluate` route. The other **38 result + 8 error**
fixtures are outbound documents, so their unchanged bytes are replayed using a
test-only ASGI HTTP transport and checked by the service's Java-facing validators.
They are not POST input payloads. This tests Python wire behavior, not Java/Jackson.

Additional HTTP coverage includes 100/101 criteria, exactly/above 1 MiB request
and 256 KiB provider-response boundaries, final envelope size after metadata,
scale N/A, custom discrete levels, weightless flags, wrong quote characters,
malformed model JSON, 401/403/429/5xx, context overflow and connection/timeout errors.
The existing missing-key, readiness and concurrency checks are retained. Tests use
short real async timers and a controlled monotonic clock to exercise the 65s boundary
without sleeping for 65 seconds; separate assertions fix the production constants.

Results from the repository root, Python 3.14.8:

```text
PYTHONPATH=ml-service /tmp/freedom-cqa-ml-validation/bin/python -m pytest -q ml-service/tests
304 passed, 1 warning in 11.11s

/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
PASS: 4 schemas; no plan drift; all 72 fixtures (16 positive, 23 schema, 28 context, 5 parser).
```

The pytest warning is the previously observed Starlette/httpx TestClient deprecation.
`pip check` reports no broken requirements. HTTP tests ran outside the restricted
sandbox for TestClient's cross-thread event loop. An autouse test guard rejects both
real sync/async httpx transports and fails teardown even if the application catches
that exception. All provider tests use doubles/MockTransport; **zero live Groq calls**
were made for T11, and the private `.env` was not read or changed.

Ready for joint Java ↔ Python HTTP integration on the authorized synthetic fixtures.
Actual Java execution, Jackson parity, persistence/request-ledger behavior and peer
acceptance remain separate checks. The synthetic-only data policy remains in effect.
No shared schemas, contracts, Java files, scoring or plan contents were modified.

## Проверка качества на шести синтетических сценариях — 2026-11-07

**Вывод: транспорт готов к совместному T13 E2E; качество ещё не готово к приёмке.**
Один разрешённый проход `openai/gpt-oss-20b`, prompt `cqa-dynamic/2`, contract 2.0.0:
6 HTTP 200, 6 provider attempts, без повторов и без DEV/реального аудио. Во время
первого прогона код сервиса, prompt и исходные `expected.json` не менялись. Этот
раздел фиксирует baseline `cqa-dynamic/2`; последующие изменения описаны ниже отдельно.

Разметка всех 24 ответов проверена Codex по тексту и критериям **до live-вызовов**
и зафиксирована с SHA-256 исходников в [предварительном разборе](reports/synthetic-quality-review.json).
Она логична: общий вопрос → IDENTITY=na; защищённое действие без проверки → no;
оскорбление → отдельный flag=yes; понятная формулировка → CLARITY=10 независимо
от вежливости. В EN заменён GREETING на CLOSING: прощания нет, N/A запрещён.
Эта проверка выполнена ассистентом, **не человеком**. Подтверждение человека запрошено,
но не получено; ниже — соответствие независимо разобранной предварительной разметке,
а не сертифицированная accuracy относительно human-approved gold.

| Язык | Сценарии | Верные оценки | Неверные | Проблемы поддержки evidence | Неверный язык объяснений |
|---|---:|---:|---:|---:|---:|
| RU | 2 | 8 | 0 | 1 | 8 |
| KZ | 2 | 7 | 1 | 3 | 8 |
| EN | 2 | 7 | 1 | 1 | 0 |
| Всего | 6 | 22/24 | 2/24 | 5/24 | 16/24 |

### Несовпадения оценок

| Scenario ID | Criterion ID | Expected | Actual | Причина и минимальное исправление |
|---|---|---|---|---|
| kz_protected_violation | LOCAL_CLARITY | scale=10 | scale=0 | Объяснение снижает понятность из-за оскорбления, хотя рубрика явно отделяет её от вежливости. В prompt подчеркнуть независимость критериев и выбор уровня по его описанию. |
| en_protected_violation | LOCAL_IDENTITY | no | yes | Собственные explanation/evidence модели говорят об изменении телефона **без** проверки. Ответ yes противоречит условию «проверка до действия». Добавить контроль полярности и согласованности answer с explanation/evidence. |

Выбор no/na не перепутан: все 3 ожидаемых N/A получены; но EN дал опасный false
compliance yes вместо no. Все 6 critical flags правильны (3 yes, 3 no), без FP/FN.
Все 6 числовых ответов входят в разрешённую шкалу; один выбран семантически неверно.
Смешения bot/operator в этом проходе не обнаружено. Изменённый LOCAL_CLOSING вернулся
с правильным no и объяснением об отсутствии прощания, без подмены старым GREETING.

### Evidence: точность не равна смысловой достаточности

Все **27/27 цитат** — дословные непустые подстроки существующих сообщений.
По смысловой проверке 19/24 обоснований поддерживают свой вывод; у остальных:

| Scenario ID | Criterion ID | Ожидаемое обоснование | Фактическая проблема | Рекомендация |
|---|---|---|---|---|
| ru_public_na | LOCAL_GROSS | Проверенные операторские реплики m0002 и m0004 | Только прощание m0004: неполное покрытие вывода «оскорблений в диалоге нет» | Для этого короткого диалога включить начало и конец проверенного участка |
| kz_public_na | LOCAL_IDENTITY | Публичный вопрос клиента m0001, обосновывающий na_rule | Цитируется приветствие/представление m0002; оно не устанавливает применимость N/A | Сослаться на запрос клиента, а не приветствие |
| kz_public_na | LOCAL_GROSS | Операторские реплики m0002 и m0004 | Только прощание m0004: неполное покрытие | Покрыть оба операторских хода |
| kz_protected_violation | LOCAL_CLARITY | Цитата, подтверждающая выбранное описание уровня | Релевантная и понятная реплика не поддерживает выбранный уровень 0 | Не переносить грубость в независимую шкалу |
| en_protected_violation | LOCAL_IDENTITY | Факт проверки **до** действия для yes | Цитата прямо свидетельствует об отсутствии проверки и поддерживает no | Проверить логическую полярность ответа |

Пять проблем — 2 неполных обоснования, 1 нерелевантное и 2 противоречащих выбранной
оценке. Последние две пересекаются с двумя ошибками labels: их нельзя складывать как
независимые ошибки. Требование покрытия обеих операторских реплик здесь — заранее
объявленная конвенция ревью коротких отрицательных случаев, не новое правило API/жюри.

Все объяснения в `ru_public_na`, `ru_protected_violation`, `kz_public_na` и
`kz_protected_violation` написаны на EN вместо RU/KZ. Это касается каждого из четырёх
критериев этих сценариев: LOCAL_GREETING, LOCAL_IDENTITY, LOCAL_CLARITY, LOCAL_GROSS.
В [полном отчёте](reports/synthetic-quality-results.json) для каждой пары scenario/criterion
приведены expected/actual, тип несовпадения, причина, рекомендуемое исправление,
ID/позиции цитат и отдельная оценка семантики. Полные ответы модели не опубликованы.

### Фактические метрики одного прохода

| Scenario ID | HTTP | Attempts | Service latency, ms | Input tokens | Output tokens |
|---|---:|---:|---:|---:|---:|
| ru_public_na | 200 | 1 | 1079 | 2456 | 426 |
| ru_protected_violation | 200 | 1 | 1309 | 2571 | 338 |
| kz_public_na | 200 | 1 | 1369 | 2485 | 456 |
| kz_protected_violation | 200 | 1 | 1317 | 2498 | 462 |
| en_public_na | 200 | 1 | 1293 | 2450 | 461 |
| en_protected_violation | 200 | 1 | 1238 | 2457 | 306 |

Итого **14917 input + 2449 output tokens**, средняя service latency **1267.5 ms**,
диапазон 1079–1369 ms. Между сценариями намеренно выдерживались 35 секунд; они не
включены в service latency. Оценочная стоимость **$0** по локальному подтверждению
Free Plan; это не отдельная проверка биллинга аккаунта.

### Предложение исправления и регрессионные проверки

[Минимальный предлагаемый patch](reports/prompt-quality-proposal.patch) усиливает
четыре инструкции: независимость критериев; полярность binary yes/no; смысл/охват
evidence для N/A и отсутствующего поведения; явный язык объяснений. Предлагается
`cqa-dynamic/3`; модель и контракт остаются прежними. На момент первого отчёта patch
не был применён. Последующая реализация после review описана ниже: patch сохранён
как первоначальное предложение, его не нужно применять поверх текущего prompt.

Offline до live: 304 основных теста и 4 теста ограничителя прогона прошли; общий
валидатор — 72/72 fixtures. Итоговый полный offline-прогон: **308 passed, 1 warning
in 13.75s**; warning — депрекация httpx в Starlette TestClient. Повторный контрактный
валидатор: **72/72**, четыре схемы совпадают с plan.json, drift отсутствует.
Отдельные [quality regression tests](reports/quality_regressions.py)
читают только записанные результаты, без API-вызовов:

```bash
ml-service/.venv/bin/python -m pytest -q ml-service/reports/quality_regressions.py
# Текущий записанный проход: 9 failed, 3 passed.
```

Падают 2 проверки оценок, 1 смысловой проверки N/A evidence, 2 покрытия отрицательного
flag и 4 проверки языка (по сценарию). Проходят critical flags, N/A labels и exact
quotes. Это ожидаемо обнаруженные дефекты модели, **не замаскированные xfail/skip**.
Набор отделён от обычного offline CI и не доказывает улучшения предложенного prompt.
После отдельного разрешённого повторного прогона нужен новый независимый разбор
evidence; нельзя «починить» тесты заменой expected под actual или подменой отчёта.

Сборщик [quality_pass.py](scripts/quality_pass.py) проверяет модель/Free Plan,
SHA-256 ровно шести разрешённых входов, максимум 2 попытки на сценарий и сохраняет
intent до POST. Приватный журнал `.quality-run/` имеет права 0700/0600 и исключён
из Git. Повторный запуск откажет при существующем журнале; без нового разрешения
его нельзя удалять ради повторного прохода. Входы DEV/CONTROL сборщик не читает.

Ограничения: всего шесть коротких случаев; нет успешной проверки личности,
промежуточных уровней 0/4, тонких нарушений и контрастного положительного changed
criterion. RU voice — только вымышленный текст, не проверка интонации. Внешняя
фактическая корректность часов поддержки не установлена. Один проход не измеряет
стабильность, а предварительные labels ещё требуют человека. Поэтому технический
T13 E2E можно начать с явной фиксацией дефектов, но качественную приёмку пока
блокируют две существенные ошибки и недостаточные evidence.

## Изменения prompt после baseline — cqa-dynamic/3

Реальный [prompt](prompts/evaluate-v1.txt) обновлён после проверки предложения.
В отличие от первоначального patch добавлены явная хронология идентификации и
проверка противоречий. Изменения применяются по формулировке переданного критерия,
без привязки к LOCAL_IDENTITY, LOCAL_CLARITY или фиксированному числу критериев:

- Критерии оцениваются независимо: оскорбление учитывается соответствующим flag,
  но само по себе не снижает понятность, когда рубрика отделяет её от вежливости.
- Для бинарного условия «идентификация до защищённого действия» действие до проверки
  требует no. Поздняя проверка не оправдывает раннее действие. Явное завершённое
  системное подтверждение до действия может поддерживать yes; подключение,
  приветствие, запрос на проверку и pending не считаются подтверждением.
  Сохраняется порядок сообщений, включая одинаковые timestamps.
- Answer/value, explanation и evidence должны поддерживать один вывод. При
  противоречии нужно переоценить исходный контекст, не менять и не выдумывать цитату.
- RU/KZ/EN явно сопоставлены русскому/казахскому/английскому языкам объяснений.
  Язык рубрики не переопределяет язык диалога; цитаты не переводятся.
- Для N/A требуется контекст именно na_rule, а не случайная дословная реплика.
  Для отсутствующего поведения нужен релевантный проверенный участок диалога.

`diagnostics.prompt_version` теперь `cqa-dynamic/3`. Contract 2.0.0, модель
`openai/gpt-oss-20b`, provider adapter, validators, retry/deadline и Java API
не менялись. Все 6 request.json и 6 expected.json совпадают с хешами baseline;
разметка остаётся предварительной, без полученного человеческого подтверждения.

[Новые offline-тесты](tests/test_prompt_quality.py) отдельно проверяют инструкции
для двух ошибок, язык, релевантность evidence, порядок системных подтверждений
до/после действия при одинаковых timestamps, изменённый ID и repair prompt.
HTTP-тесты шести сценариев с mock provider проверяют фактическую передачу нового
prompt и его версию в ответе. Дополнительно тесты явно показывают ограничение:
неверный смысл, язык или релевантность могут пройти структурную/exact-quote проверку.
Это **не доказательство исправления ответов LLM** и не новый семантический валидатор.

Проверки после изменения:

```bash
PYTHONPATH=ml-service /tmp/freedom-cqa-ml-validation/bin/python -m pytest -q ml-service/tests
# 326 passed, 1 warning in 14.03s
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
# 72/72 fixtures; 4 схемы совпадают с plan.json; schema drift отсутствует
ml-service/.venv/bin/python -m pytest -q ml-service/reports/quality_regressions.py
# На неизменённом старом live-отчёте: 9 failed, 3 passed (cqa-dynamic/2).
```

Warning — существующая депрекация httpx в Starlette TestClient. HTTP-тесты выполнялись
вне ограничений sandbox на межпоточный event loop; autouse-фикстура блокирует реальные
HTTP transports. Новых live-вызовов при этой доработке не было. Исторический отчёт и
его ошибки не переписаны и не замаскированы xfail/skip.

Prompt готов к одному повторному quality evaluation, но улучшение качества пока
не измерено. **Следующую команду выполнять только после отдельного разрешения**,
из корня репозитория, с настроенным подтверждённым Groq Free Plan:

```bash
PYTHONPATH=ml-service ml-service/.venv/bin/python ml-service/scripts/quality_pass.py --run-id prompt-v3
```

Команда использует только шесть прежних входов с проверкой SHA-256 и модель 20b,
один POST на сценарий, максимум 2 provider attempts на сценарий (12 за проход).
Общий deadline одного evaluate остаётся 65 секунд. Новый приватный журнал
`.quality-run/synthetic-six-prompt-v3.json` хранит версию и SHA-256 prompt, ответы и
метрики отдельно от baseline. Файл создаётся эксклюзивно до первого POST; повторный
запуск с тем же run-id откажет. Не удалять/переименовывать журнал ради обхода защиты.
После разрешённого прохода нужен новый отдельный разбор оценок и смысла evidence,
с сопоставлением с неизменённой предварительной разметкой и первым отчётом.

Изменений общего Java ↔ Python контракта не требуется; несовместимости по схемам
не обнаружено. Реальное Java E2E здесь не запускалось. Увеличение prompt может
повлиять на tokens/latency и качество; это измеряется будущим разрешённым проходом.
