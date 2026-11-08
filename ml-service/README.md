# Freedom CQA — Python ML service

Independent FastAPI service for T08/T09/T10, contract **2.0.0**, localhost **8001**.
Python 3.11+; tested here on Python 3.14. Java owns persistence, request-status
reconciliation and deterministic scoring. This service returns model answers and
grounded evidence, never authoritative totals. No dependency on `backend/`.

Current review status: Nurtas accepted all 24 T09 synthetic labels and their evidence;
one human reviewer, peer review pending. See the [T09 report](reports/t09-human-review-report.json)
and the current T09/PR/T13 checklist at the end of this document. Older quality sections
retain their historical status and do not override this later human review.
Current prompt: `cqa-dynamic/4`, with language-specific explanation examples and stricter
evidence instructions. Its live quality has not been measured. The offline-only dynamic
checklist demo proposal and verification scope are described in the final section below.

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

Default `synthetic_only` admits exact conversations registered in the bundled synthetic
fixtures; changing a dataset label cannot authorize real transcripts. Java additionally
restricts its default conversation/checklist pairs. The separate `approved_dataset` mode
uses an exact private source hash, explicit chat IDs, bounded checklist scope, expiry,
revocation, external opt-in and rubric confirmation. See the PR17 update below and the
[shared admission specification](../docs/DYNAMIC_ADMISSION.md). Technical agreement does
not authorize external DEV/CONTROL transfer. Do not add real data to synthetic fixtures.

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
При подготовке PR архив переведён в zero-context diff без изменения предложенного
содержимого, чтобы не хранить whitespace-only context lines.

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
На момент изменения prompt человеческое подтверждение ещё ожидалось; последующий
review Нуртаса зафиксирован в разделе T09 ниже. Expected-файлы не менялись.

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

На момент подготовки prompt ожидался повторный quality evaluation. Этот проход
теперь выполнен и сохранён: 24/24 совпадения меток, 6 HTTP 200, 6 attempts.
Следующая команда оставлена для воспроизводимости; **не запускать заново и не удалять
журнал ради повтора**. Будущие live-вызовы требуют отдельного разрешения:

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

## T09: проверка Нуртаса и готовность Prompt v3 к PR

Исторический источник — локальный `T09_Нуртас_review.json`, предоставленный экспорт
из Downloads; в текущем публичном checkout этого файла нет. Публичный сводный отчёт:
[t09-human-review-report.json](reports/t09-human-review-report.json). Зафиксированный SHA-256 экспорта:
`47debaaa039441359da0d5bd6cd1cfe02f44ef77c3f9274384a6b76c68d2db8a`.
Время создания экспорта: `2026-11-07T16:03:23.688Z`. Единственный human reviewer —
**Нуртас**. Пользователь отдельно подтвердил личную проверку всех 24 меток и отсутствие
повторной проверки вторым участником. Codex сверил файл, но не является вторым human reviewer.

[Отчёт T09](reports/t09-human-review-report.json) содержит все 24 уникальные пары
scenario/criterion, answer/value, ACCEPT, evidence_review=ok и хеши исходных fixtures.
В исходном экспорте ACCEPT выражен через `review_status=good` и `chosen=proposed`;
все значения сопоставлены с expected.json, включая scale:10. Сам экспорт не содержит
хешей fixtures: привязка к текущим байтам выполнена при подготовке этого отчёта.

| Язык | Проверено Нуртасом | ACCEPT | Evidence ok |
|---|---:|---:|---:|
| RU | 8 | 8 | 8 |
| KZ | 8 | 8 | 8 |
| EN | 8 | 8 | 8 |
| Всего | 24 | 24 | 24 |

Часть acceptance criteria T09 о проверке меток человеком теперь имеет подтверждение
одного реального reviewer. Все шесть request.json и шесть expected.json сохранены
побайтно и совпадают с хешами до первого live-прохода. Исторические baseline-отчёты
не переписаны. Peer review **не выполнен**: второй проверки меток нет; подтверждения
проверки shared boundaries и тестов вторым участником также не предоставлено.
Последнее отдельно требуется общим Definition of Done; это не утверждение, будто
T09 требует именно двух независимых разметчиков каждой метки. `gold_status` исходного
файла остаётся `provisional_pending_joint_approval`. Полное закрытие T09/изменение
plan.json или принятие T02 от имени второго участника здесь не выполняются.

**24/24 ACCEPT — одобрение конечного набора эталонных меток, не доказательство общей
точности модели.** Отдельный сохранённый проход v3 совпал с ними на 24/24 против
22/24 у v2. Это одна малая синтетическая выборка; реальный DEV/CONTROL, длинные
контексты, звук и полный официальный checklist этим не проверены.
`evidence_review=ok` относится к проверенным эталонам, не означает автоматического
принятия всех live-ответов. У v3 сохраняются 16 английских объяснений вместо RU/KZ;
в `kz_public_na` обоснование GROSS покрывает одну операторскую реплику, а IDENTITY=na
подкреплено косвенно ответом о часах работы. Эти замечания не изменяют принятые метки.

Prompt v3 готов к **PR на review с перечисленными ограничениями**, а не к заявлению
о завершённой качественной приёмке или автоматическому merge. Проверен diff от
локального main для ветки `codex/ml-prompt-v3`, базовый HEAD `219fab2`; удалённая
ветка не обновлялась. Runtime в этой доработке не менялся. Проверки:

- Полный offline pytest: **326 passed, 1 warning in 11.13s**. Warning — существующая
  депрекация httpx/Starlette TestClient; реальный HTTP блокируется тестовой фикстурой.
- Контрактный валидатор: **72/72**, все четыре схемы равны plan.json, drift отсутствует.
- Финальный `git diff main --check` проходит. У архивного proposal.patch убраны
  whitespace-only context lines без изменения предложенного содержимого.
- Проверены публичные ML-файлы и изменённые blobs единственного коммита ветки:
  шаблоны ключей/токенов, private keys, подписанные URL, credential assignments и
  совпадения с локально настроенными секретами. Значения секретов не выводились.
  Секретов и клиентских данных в проверенном содержимом не обнаружено; это scoped
  inspection, не математическая гарантия отсутствия любых возможных секретов.
- `.env` и `.quality-run/` исключены из Git и не отслеживаются. В публичные отчёты
  не скопированы полные live-ответы, DEV/CONTROL, записи звонков или закрытые материалы.

Новых Groq-вызовов не было. Общий контракт, plan.json, server/, Java scoring и исходные
expected не менялись. Peer review и актуализация статусов плана остаются отдельными
действиями владельцев; PR/commit/push/merge в этой работе не выполнялись.

## T13: технический checklist для совместной интеграции

Это **подготовленный checklist, не выполненный E2E**. T13 зависит от T05, T10, T11,
T12; полный DoD и T02 joint approval проверяются отдельно. Ответственность за Java
реализацию и тесты остаётся у Фархата. Контракт 2.0.0 не требует изменений.

Разрешённые входы — только точные шесть fixtures, перечисленные в отчёте T09:

| Сценарий | Что проверить в полном пути UI → Java → Python → модель → Java → SQLite → UI |
|---|---|
| ru_public_na | GREETING=yes, IDENTITY=na, CLARITY=10, GROSS=no; нормализация N/A в Java |
| kz_public_na | Те же метки; сохранение казахского Unicode; отдельное ревью смысла evidence |
| en_public_na | Те же метки; точный переход UI к message_id и цитате |
| ru_protected_violation | GREETING=no, IDENTITY=no, CLARITY=10, GROSS=yes; bot/system и повторные ISO timestamps; только текст звонка |
| kz_protected_violation | Те же метки; понятность отдельно от грубости; цитаты без перевода |
| en_protected_violation | LOCAL_CLOSING=no, IDENTITY=no, CLARITY=10, GROSS=yes; checklist version 2, изменённый ID |

- [ ] Согласовать отдельный будущий live E2E и его бюджет; наличие checklist не даёт
  нового разрешения на Groq. Только `openai/gpt-oss-20b`, подтверждённый Free Plan,
  синтетические transcripts и rubric. DEV/CONTROL, реальные звонки/PII не отправлять.
- [ ] Проверить готовность T05/T10/T11/T12 и документированные совместные решения T02.
  Подготовить отдельную тестовую SQLite; импортировать в Java точные conversations
  и checklist snapshots из fixtures. Сохранить исходные ID, роли, порядок, язык,
  timestamps, key/version и rubric; не подменять v1/v2 на latest.
- [ ] Java обслуживает UI и `/api` на 8080; один Python worker — на 8001. Health не
  вызывает модель. Ключ находится только в Python-конфигурации, отсутствует в браузере,
  Java payload, access logs и публичных отчётах.
- [ ] Для каждого нового разрешённого E2E создать свежий request_id. UI передаёт в
  Java explicit checklist_version; Java один раз фиксирует полные snapshots до HTTP,
  сохраняет request ledger и не удерживает DB-транзакцию во время inference.
- [ ] Выполнить реальный маршрут через Java `POST /api/evaluations/auto`, далее
  `POST http://127.0.0.1:8001/v1/evaluate`, JSON/UTF-8, contract 2.0.0. Прямой запуск
  quality_pass.py и старые журналы не засчитывать как Java E2E.
- [ ] Java независимо проверяет schema/DTO/context, точные request_id/conversation_id/
  checklist_key/checklist_version, полный набор критериев, answer/value, уровни,
  N/A, flags и дословность evidence по pinned сообщениям. Никакой нормализации цитат
  и доверия к ответу только потому, что его принял Python.
- [ ] Java рассчитывает cqa-score/1 по pinned checklist: N/A исключает вес, flag не
  становится штрафом. Python не возвращает authoritative totals. Java атомарно
  сохраняет answers, original score snapshot, версии и диагностику; GET/reload
  возвращает сохранённый результат, без пересчёта по latest.
- [ ] В UI проверить все 24 answer/value, объяснения, признаки N/A/critical flag,
  message jump, роли и timestamps. Известные RU/KZ English explanations зафиксировать
  как quality limitation. Exact substring и смысловую достаточность проверять раздельно.
- [ ] Офлайн через тестовый HTTP peer/mocks проверить отказ Java при wrong identity,
  missing/duplicate/unknown criterion, лишних полях, неверных типах, NaN/Infinity,
  неправильном N/A/уровне и поддельной цитате. Invalid result не сохраняется как успех.
  Эти отрицательные проверки не отправлять реальной модели и не выдавать за live E2E.
- [ ] Офлайн проверить missing config, 401/403, 429, 5xx, busy, oversize и timeout:
  безопасный согласованный error envelope и request_id; никаких raw upstream ошибок.
  Python ≤2 attempts / ≤65 s; Java connect ≤3 s / deadline ≤70 s; browser ≤75 s.
  Автоматических Java/UI POST retries нет.
- [ ] Проверить `GET /api/evaluation-requests/{request_id}`: pending/succeeded/failed/
  unknown. Повтор того же ID не запускает модель заново; другой payload под тем же ID
  даёт 409. После timeout/reload сначала reconciliation статуса; неопределённый исход
  не превращается в скрытый replay. Timeout не гарантирует отмену inference/billing.
- [ ] Сохранить минимальные доказательства: revisions Java/Python, scenario ID,
  fresh request_id, pinned versions, HTTP/status/evaluation ID, prompt/model,
  attempts, usage, latency, Java validation/save/UI результаты. Секреты, полный raw
  provider output, реальные данные и приватную БД не включать в PR. Оба участника
  отдельно подтверждают shared boundaries и результаты перед закрытием T13.

T13 можно использовать для технической проверки интеграции с известными ограничениями
качества. Его прохождение не закрывает автоматически T14/T15 и не доказывает качество
на длинных/реальных разговорах или звук; без аудио не оценивать дикцию и интонацию.

## После T13: язык объяснений и offline demo — cqa-dynamic/4

Изменения от 2026-11-08 ограничены ML prompt и его offline-проверками. Основание —
сохранённый v3: 24/24 совпадения меток, но все 16 RU/KZ-объяснений на английском;
косвенное обоснование N/A и неполный проверенный участок для GROSS в kz_public_na.
Review T09 Нуртаса относится к 24 эталонным меткам/evidence; эти expected.json и
исходные шесть request.json не менялись. Одобрение не перенесено на новый demo.

В [prompt](prompts/evaluate-v1.txt) усилены прямое написание explanation на нужном
языке, проверка языка каждой фразы и сохранение исходных цитат. [Сборщик](app/prompt.py)
добавляет в system message только короткую инструкцию и два примера для текущего
conversation.language: RU, KZ или EN. Примеры не содержат criterion_id, message_id,
answer/value и не задают готовый ответ. Они иллюстрируют стиль; факты, оценки и
доказательства модель по-прежнему должна выводить из текущих checklist/conversation.
Постперевода, подмены ответа модели и нового семантического валидатора нет.

Для N/A, основанного на запросе клиента, нужно цитировать сам клиентский вопрос,
подтверждающий na_rule; приветствие или ответ оператора о теме не заменяют вопрос.
Для других na_rule используется реальный подтверждающий контекст, без выдуманного
вопроса — в частности, нельзя требовать несуществующую реплику клиента. Перед no
по нарушению модель должна проверить все релевантные реплики оператора; в коротком
диалоге с двумя операторскими репликами цитировать обе, а не одну вежливую фразу.
В длинном участке нужны релевантные примеры, границы и объяснение проверенного охвата.

Contract 2.0.0, transport, provider/model, retries/deadline, validators, Java scoring
и синтетическая allowlist не изменены. Обновилось только значение существующего
diagnostics.prompt_version: `cqa-dynamic/4`. Исторический quality_pass `--run-id prompt-v3`
на новом prompt намеренно отказывает; его guard не ослаблен, новый live-run не разрешён.

**[Demo proposal](reports/dynamic-checklist-demo-proposal.json)** — один новый полностью
вымышленный RU-диалог про учебное приложение, представленный с двумя версиями рубрики:

| Свойство | Версия 1 | Версия 2 |
|---|---|---|
| Checklist key | synthetic-demo-steps | synthetic-demo-steps |
| Изменяемый criterion_id | LOCAL_GREETING | DEMO_STEP_ORDER |
| Условие | Приветствие и представление в первой реплике оператора | Два конкретных шага в явном порядке |
| Предложенная метка | no: приветствует только бот | yes: оператор перечисляет шаги 1 и 2 |

Conversation `SYNTHETIC:ru_dynamic_steps_proposal` одинаков в обеих версиях. Клиент
просит два шага для открытия учебной справки без доступа к аккаунту. Оператор сразу
даёт нумерованную инструкцию и затем вежливо завершает диалог. Остальные предложенные
ответы: IDENTITY=na с вопросом m0001; CLARITY=10 с инструкцией m0003; GROSS=no с обеими
операторскими репликами m0003/m0005. Они записаны как **предложенная разметка ассистента,
не результат модели и не human-approved gold**. Требуется отдельное человеческое review.
Числовые totals и фиктивные diagnostics отсутствуют.

Demo лежит только в reports/, не в tests/fixtures/, и не зарегистрирован для inference.
До любого live-добавления нужно согласовать с Фархатом расширение Java SyntheticPolicy,
которая сейчас требует ровно шесть fixtures, и согласованную регистрацию с обеих сторон.
В этой работе allowlist не расширялась, Java/UI demo не запускался. Это согласование
нового входа; изменений общего контракта сейчас не требуется.

Offline-проверки проверяют доставку нужных языковых примеров, сохранение mixed-language
текста/Unicode/ID/allowed pairs в первом и repair prompt, v4 diagnostics, строгую
валидность обеих версий demo и предложенных цитат. Отдельная HTTP-проверка требует
503 PRIVACY_POLICY_UNCONFIGURED для demo с нулём обращений к mock provider. Количество
локальных request fixtures остаётся ровно шесть. Эти тесты не доказывают, что LLM
будет всегда соблюдать язык или смысловую релевантность; нужен отдельно разрешённый
будущий live quality evaluation. Новых вызовов Groq в этой доработке не было.

Фактическая проверка этой доработки:

```bash
PYTHONPATH=ml-service /tmp/freedom-cqa-ml-validation/bin/python -m pytest -q ml-service/tests
# 332 passed, 1 warning in 11.09s
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
# 72/72 fixtures; четыре схемы совпадают с plan.json; schema drift отсутствует
```

Warning — прежняя депрекация httpx в Starlette TestClient. Все 12 хешей исходных
request/expected совпали с отчётом T09. Для v4 нет новых измерений latency/tokens
или доказательства улучшения языка модели; Java E2E повторно не выполнялся.

## CONTROL admission v2 update (PR #17)

Technical approval for arbitrary explicitly selected groups/ID counts was relayed by Farhat
from Nurtas in FINAL ACCEPTANCE & CONTROL READINESS. This is not external-transfer consent.
`approved_dataset` derives the group from the SHA-256-verified source and requires every
explicit composite ID to exist. DEV/15 is no longer hardcoded; calls/audio remain excluded.
Both opt-ins, private expiring grant, provider/model/endpoint, scope and rubric confirmation
remain mandatory. Prompt v4 and contract2.0.0 are unchanged.

Operator commands, actual environment names and the private source/grant procedure are in
[README](../README.md#новый-набор-и-approval-v2) and [DYNAMIC_ADMISSION](../docs/DYNAMIC_ADMISSION.md).
The helper makes no provider calls. Existing historical live reports above do not authorize
new DEV/CONTROL transfers or establish current live quality/cost.
