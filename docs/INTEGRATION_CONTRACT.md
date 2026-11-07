# Freedom CQA — единый контракт Java ↔ Python ML

**Contract version: 2.0.0. Статус: proposed, требует принятия Farhat и Nurtas в T02 до реализации.** Это замена прежнего проекта 1.0.0 с in-process evaluator. Источник схем/численных политик/примеров — [plan.json](../plan.json), `contracts`; [план](IMPLEMENTATION_PLAN.md) задаёт tasks и merge. Контракт не означает, что HTTP service уже работает.

## Транспорт и совместимость

Java :8080 вызывает **POST `http://127.0.0.1:8001/v1/evaluate`**, UTF-8 `Content-Type: application/json`; успех 200 с EvaluationResult. `GET /health` проверяет readiness без платного model probe и секретов. `/v1` — первое поколение HTTP route; JSON envelope имеет точную версию`2.0.0`, поскольку заменяет старый in-process проект. Сейчас принимается только точная версия; расширения согласуются одновременно на обеих сторонах.

Один JSON Schema Draft2020-12 и один набор synthetic positive/negative fixtures; две реализации: Java DTO/Jackson/Bean Validation и Python strict schemas. Pydantic не является единственным межъязыковым источником истины. Farhat владеет `server/`, Nurtas — `ml-service/`, shared `contracts/` меняет Farhat после reviewNurtas. Любое изменение JSON, endpoints, fields, score semantics, message IDs или validation согласуют **оба до реализации**. Эти будущие каталоги сейчас не создавались.

ML transport может быть FastAPI либо другим HTTP framework по выбору Nurtas; Java зависит только от данного JSON. ML не обращается к SQLite и не рассчитывает totals. Java самостоятельно проверяет ответ, считает результат и сохраняет immutable snapshot. Java serving static Vanilla UI обеспечивает same-origin; browser не вызывает Python/provider и не получает organizer/provider credentials. Оба сервиса для localdemo слушают localhost.

## Вход и immutable context


Java API принимает `conversation_id`, `checklist_key`, **обязательный** `checklist_version`; auto дополнительно требует `request_id` UUID. Загружает точные source/checklist snapshots один раз до model call. Historical version разрешена, даже если latest новее. Backend не держит write transaction во время сетевого запроса. Save получает тот же pinned Checklist, не ищет latest повторно.

`conversation` — безопасная проекция: id, dataset_group_id, conversation_id, channel, language, messages. Message: id, timestamp, speaker, text. `audio_url`, source credentials, DB paths и служебные поля модели не отправляются. Это не разрешение внешней передачи данных: до Q03 real transcripts остаются локально. Own synthetic fixtures можно использовать для первых smoke tests после настройки доступа/бюджета.

Текст, order, role и timestamps не меняются. Чаты MM:SS, звонки ISO8601 с зоной; ID соответствует порядку `m0001`, `m0002`, … (не ограничивать будущие IDs ровно четырьмя цифрами). Повторные timestamps и даже одинаковые turns не объединяются. Bot greeting не операторский; system events могут подтверждать verification в нужном месте последовательности.

Checklist целиком содержит key/version/title/description/sections и все criteria с instruction/kind/weight/levels/allow_na/na_rule. Модель не получает зашитый список C01–C08: новые IDs и формулировки должны работать без изменения кода. Не выводить audio offsets из абсолютных timestamps без привязки к recording origin.

## Ответ модели и результат ML service

Непосредственный structured output модели — JSON-объект с единственным полем `answers`, содержащим все CriterionAnswer. Identity/version/diagnostics добавляет доверенный adapter из входа и SDK; не просит модель угадывать их.

| Поле EvaluationResult | Требование |
|---|---|
| contract_version | `2.0.0`, проверяется сервером |
| request_id | Точное эхо UUID запроса |
| conversation_id | Равен pinned conversation.id (составному внутреннему ID) |
| checklist_key / checklist_version | Равны pinned Checklist; version — integer >=1 |
| answers | Ровно один CriterionAnswer на каждый настроенный ID |
| diagnostics | Типизированная allowlist метаданных SDK; никаких raw prompts/responses |

| Поле CriterionAnswer | Требование |
|---|---|
| criterion_id | Точное совпадение с настроенным ID; no missing/duplicates/unknown |
| answer | `yes`, `no`, `na`, `scale` |
| value | Только конечное число для scale, равное одному configured level; иначе null |
| explanation | Содержательный непустой текст после проверки whitespace |
| evidence | Непустой список существующих message_id и точных непустых цитат |

Binary допускает yes/no и NA только allow_na. Scale допускает scale и разрешённый NA; произвольные 0–100 запрещены. Flag — yes/no, weight0, без NA; yes означает обнаруженное нарушение, а не штраф к total. Числовые строки/boolean вместо числа не принимаются как строгий ML output. JSON должен быть объектом, без markdown fences, trailing prose, дублированных ключей и NaN/Infinity. Не молча вычищать произвольный текст до «похожего JSON».

Exact quote проверяется `quote in source_message.text` без trim/case-fold/перевода/Unicode normalization. При этом полностью пробельная цитата недостаточна. Неизвестный ID или даже одна изменённая буква → invalid output. Пустые сообщения не дают evidence; если весь диалог не содержит пригодного текста, вернуть явную ошибку невозможности оценки, не генерировать ответы.

Для пропущенного действия указываются реальные сообщения/границы проверенного участка, где действие ожидалось, и объяснение отсутствия. Нельзя цитировать выдуманное «оператор не представился». Для NA объясняется именно configured na_rule, подтверждённое контекстом; неопределённость модели не является NA. Несколько сообщений разрешены. Проверка substring необходима, но не доказывает смысл: релевантность проверяют gold fixtures и человек.

У компании нет предоставленной в текущих материалах отдельной нормативной базы ответов. C04 «полнота по диалогу» и внешняя factual correctness различаются. Не придумывать тарифы/регламенты. Q07 уточняет ожидаемый способ проверки; неподтверждённые факты явно отражать в объяснении/allowlisted warning и human review, не выдавать их за проверенные и не заменять произвольным NA. Если criterion требует недоступного входа, сообщить об ограничении/ошибке, а не выдумывать доказательство.


## Java validation, scoring и persistence

Порядок: bounded strict JSON → schema/DTO/context → identity/request/version echo → complete criterion set/kind/levels/NA → exact evidence → pure Java BigDecimal calculate → atomic persistence. Java не доверяет даже уже проверенному Python result. Duplicate JSON keys, unknown fields на любом уровне, числовые строки/bools, NaN/Infinity/overflow, blank explanation/evidence запрещены. `7` и`7.0` — одинаковое числовое значение configured level. Whitespace/Unicode edge cases фиксируются общими fixtures; source text/quotes не нормализуются.

Checklist validation: уникальные IDs sections/criteria, существующие section references, хотя бы один positive-weight criterion. Binary/scale имеют weight>0; flagweight0/noNA/no levels. Scale: минимум 2 уникальных конечных значения, min0/max>0. allow_na требует непустой na_rule. Message IDs уникальны и следуют исходному порядку m0001…; одинаковые timestamps не объединяются. JSON Schema проверяет форму; эти межполевые и grounding правила проверяют обе реализации.

Java переносит текущие правила, а не придумывает новую scoring семантику: raw=w×ratio, W=sum applicable weights, total=100×sum(raw)/W; при W0 null; N/A исключает weight; C08 separate flag безштрафа; section percentages считаются внутри section. Использовать decimal, не binary double; не округлять строки перед суммированием. HALF_UP до 2dec — прежняя implementation assumption, не подтверждённый tie rule организатора. T04 сравнивает 5184 official-seed сочетания и custom scale/rounding/all-NA fixtures с Python/Fraction reference. Python tests не являются Java tests.

Сохраняются original answers/score snapshot, pinned checklist key/version, `scoring_version=cqa-score/1`, origin и allowlisted diagnostics. Original не пересчитывается на GET. Review использует scorer сохранённой версии; unknown version — явная ошибка. Confirm без replacement; change содержит полный CriterionAnswer того же criterion, reason обязателен. Open appeal uniqueness + revision check/conditional update в короткой транзакции; concurrent second resolve409. Re-appeal не стирает прошлое решение.

Только Java владеет новым явно заданным DB path. Legacy DB не меняется автоматически. Если требуется старая история: explicit export/import, counts/IDs/version checks, reconstructed scores помечаются отдельно; нельзя выдать backfill за исторический snapshot. foreign_keys/busy_timeout задаются накаждом connection. DB transaction не удерживается во время HTTP.

## Публичный Java API и request lifecycle

Существующие 14 endpoints из `plan.json.endpoints_current` — baseline для parity, не подтверждение готовности Java. Согласованные изменения:

| Endpoint | Изменение |
|---|---|
| POST /api/evaluations/manual and /auto | Required checklist_version>=1; /auto also requires request_id UUID. Version missing422/unknown404; exact historical version allowed. |
| PUT /api/checklists/{key} | Required expected_version query; mismatch409; draft body same. |
| POST /api/datasets/fetch | New {group_id}; backend configured URL, preserve other signature query parameters; existing file import remains. |
| GET /api/health | Actual readiness without paid probe/secrets. |
| GET /api/evaluations/{id} | Keep existing fields; additive contract_version/scoring_version/metadata/review_revision; original_score snapshot. |
| GET /api/evaluation-requests/{request_id} | New status resource for timeout/reload/batch reconciliation; fields request_id/status/evaluation_id/error. |

Полный body публичного auto endpoint (отличается от Java→ML request ниже):

```json
{
  "request_id": "11111111-1111-4111-8111-111111111111",
  "conversation_id": "SYNTHETIC:contract-demo",
  "checklist_key": "synthetic-contract",
  "checklist_version": 2
}
```

Java сохраняет unique request_id+payload identity до HTTP. Повторный ID с другим payload409; pending202 и status URL; succeeded возвращает прежнюю evaluation200; failed возвращает записанную safeerror безнового provider call. После crash interrupted pending становится unknown. Browser timeout/abort не гарантирует отмену inference. Java не повторяет POST автоматически; UI сначала читает status и предлагает явную новую попытку с новым UUID и предупреждением о возможной повторной стоимости.

`GET /api/evaluation-requests/{request_id}` возвращает 200 с `request_id`, `status` (pending/succeeded/failed/unknown), `evaluation_id` (только succeeded, иначе null), `error` (safe detail object для failed/unknown, иначе null); неизвестный ID404. Batch фиксирует список conversation IDs и checklistversion, выполняет один запрос за раз, хранит минимальный manifest IDs/status и восстанавливается черезэтотресурс. Original result не сохраняется при invalid/partial response, но status/error ledger сохраняется. Exactly-once provider billing при timeout/crash не обещается.

## Ошибки, лимиты и retries

Единый error envelope на ML и Java (значения message не содержат rawprovider/input):

```json
{
  "detail": {
    "code": "EVALUATOR_TIMEOUT",
    "message": "Evaluation deadline exceeded. Check request status before retrying.",
    "retryable": true,
    "request_id": "11111111-1111-4111-8111-111111111111"
  }
}
```

| HTTP | Codes |
|---|---|
| 422 | INVALID_INPUT / INPUT_TOO_LARGE / UNSUPPORTED_CONTRACT |
| 404 | NOT_FOUND |
| 409 | VERSION_CONFLICT / REVIEW_CONFLICT / REQUEST_ID_CONFLICT |
| 501 | EVALUATOR_UNCONFIGURED |
| 502 | EVALUATOR_INVALID_OUTPUT / EVALUATOR_PROVIDER_ERROR |
| 503 | EVALUATOR_RATE_LIMITED / EVALUATOR_AUTH / PRIVACY_POLICY_UNCONFIGURED / EVALUATOR_BUSY |
| 504 | EVALUATOR_TIMEOUT |
| 413 | PAYLOAD_TOO_LARGE |

ML uses422/413 input,501 configuration,502 invalid/provider,503 busy/rate/auth/policy,504 timeout; Java adds404/409 domain errors. retryable=true means an explicit later attempt may work, never automatic replay. request_id null only if invalid request could not supply valid UUID. Java validates envelope, otherwise maps to safe502; do not forward provider bodies.

Transport deadlines: Python provider connect≤5s, attempt≤30s, всего≤65s и≤2attempts; Java→Python connect≤3s, общий HTTPdeadline≤70s; browser deadline≤75s. **Java POST retries=0**. Retryable=true не включает автоматический повтор в UI/Java. В Python max1 in-flight; busy503. Ошибочный ML envelope/version/echo →Java502, no result save. Connect refused/unavailable →503; timeout→504; upstream auth/policy не ретраятся.

Начальные bounded limits: dataset16MiB; Java→ML request1MiB; ML response256KiB; checklist≤100criteria. Это инженерные defaults, не ограничения жюри. Byte-size overflow413; context/schema issues422; без silent truncation. Проверить CONTROL capacity в T17.


Начальные engineering defaults: connect≤5s, одна попытка≤30s, общий monotonic deadline≤65s, **максимум 2 оплачиваемые попытки всего**. Backoff≤2s; Retry-After соблюдать только если он помещается в остаток deadline, иначе вернуть unavailable. SDK internal retries отключить либо включить в этот общий budget. UI abort не означает, что provider гарантированно отменил оплачиваемый inference: это учитывать в diagnostics, не обещать отмену задним числом.

Retry разрешён для transport timeout,429/5xx и один раз для invalid JSON/schema/evidence с безопасным структурированным feedback. Второй repair/третий call запрещён. Не ретраить auth/permission/context overflow/missing config/privacy. Feedback содержит коды и criterion/message IDs, а не secret URLs или бесконтрольные raw exception dumps. Model result и evidence всё равно проверяются заново.

Diagnostics: provider/model/prompt_version, attempt_count, суммарные input_tokens/output_tokens, estimated_cost_usd, latency_ms, allowlisted warning codes. Данные от SDK/таймера, не от модели. Usage всех оплаченных попыток, включая invalid responses, суммируется. Неизвестный usage/cost=null; latency измеряется на полный вызов с retries. Pricing фиксируется по официальной документации выбранного provider на дату T08; конкретных цен/моделей этот план не выдумывает. При cached token/audio tariffs использовать реальные категории provider, не считать их обычными text tokens молча.

Перед real-data внешними вызовами T08 фиксирует разрешённость передачи/retention, provider, бюджет и секреты на backend. Наличие платных API в FAQ не равно разрешению любого провайдера на любые персональные данные. Не публиковать official PDFs: Guide сам содержит signed API URL. Не log/store raw model prompts/responses в публичные fixtures/CI; локальная БД с результатами реальных диалогов приватна. Если безопасный режим недоступен, показать blocker и работать на собственных synthetic данных, не на fake AI.


## Полный JSON request Java → Python

Это вручную составленная synthetic fixture, не DEV/CONTROL и не реальная model evaluation. Checklist специально имеет произвольные IDs, чтобы проверить динамический rubric. Порядок JSON полей незначим. Все поля обязательны, nullable только по schema.

```json
{
  "contract_version": "2.0.0",
  "conversation": {
    "id": "SYNTHETIC:contract-demo",
    "dataset_group_id": "SYNTHETIC",
    "conversation_id": "contract-demo",
    "channel": "agent chat",
    "language": "EN",
    "messages": [
      {
        "id": "m0001",
        "timestamp": "00:00",
        "speaker": "client",
        "text": "What time does support open?"
      },
      {
        "id": "m0002",
        "timestamp": "00:01",
        "speaker": "bot",
        "text": "Hello! An operator will join."
      },
      {
        "id": "m0003",
        "timestamp": "00:05",
        "speaker": "operator",
        "text": "Hello, I'm Ada. Support opens at 09:00."
      },
      {
        "id": "m0004",
        "timestamp": "00:10",
        "speaker": "client",
        "text": "Thank you."
      },
      {
        "id": "m0005",
        "timestamp": "00:12",
        "speaker": "operator",
        "text": "Happy to help. Goodbye."
      }
    ]
  },
  "checklist": {
    "key": "synthetic-contract",
    "version": 2,
    "title": "Synthetic contract example",
    "description": "Own fixture, not official rubric and not a model evaluation.",
    "sections": [
      {
        "id": "service",
        "title": "Service"
      },
      {
        "id": "critical",
        "title": "Critical"
      }
    ],
    "criteria": [
      {
        "id": "S_HELLO",
        "section_id": "service",
        "title": "Operator introduction",
        "instruction": "Yes if the first operator response greets and introduces the operator. Bot greetings do not count.",
        "kind": "binary",
        "weight": 25,
        "allow_na": false,
        "na_rule": null,
        "levels": []
      },
      {
        "id": "S_CLARITY",
        "section_id": "service",
        "title": "Clear response",
        "instruction": "Choose the configured clarity level. Assess clarity, not external factual correctness of opening hours.",
        "kind": "scale",
        "weight": 75,
        "allow_na": false,
        "na_rule": null,
        "levels": [
          {
            "value": 0,
            "description": "No understandable response."
          },
          {
            "value": 4,
            "description": "Several unclear statements."
          },
          {
            "value": 7,
            "description": "One noticeable ambiguity."
          },
          {
            "value": 10,
            "description": "Clear and coherent response."
          }
        ]
      },
      {
        "id": "S_ID",
        "section_id": "service",
        "title": "Identity verification",
        "instruction": "Yes if required identity verification precedes a protected account action.",
        "kind": "binary",
        "weight": 20,
        "allow_na": true,
        "na_rule": "The customer asks only a general public question; no protected account action is requested.",
        "levels": []
      },
      {
        "id": "S_FLAG",
        "section_id": "critical",
        "title": "Explicit insult",
        "instruction": "Yes if the operator explicitly insults the customer. This is a separate flag, not a numeric penalty.",
        "kind": "flag",
        "weight": 0,
        "allow_na": false,
        "na_rule": null,
        "levels": []
      }
    ]
  },
  "request_id": "11111111-1111-4111-8111-111111111111"
}
```

## Полный JSON response Python → Java

ML adapter копирует identity/version/request_id из входа и diagnostics из SDK; модель возвращает только `{"answers":[...]}`. `attempt_count=0` разрешён только для этой offline fixture. Production successful result имеет>=1 и настоящие provider/model; значение origin задаёт Java. Expected fixture score:100, applicable weight100, gross flagfalse; scorer не входит ML response.

```json
{
  "contract_version": "2.0.0",
  "conversation_id": "SYNTHETIC:contract-demo",
  "checklist_key": "synthetic-contract",
  "checklist_version": 2,
  "answers": [
    {
      "criterion_id": "S_HELLO",
      "answer": "yes",
      "value": null,
      "explanation": "The first operator turn greets and introduces Ada; the bot greeting was not counted.",
      "evidence": [
        {
          "message_id": "m0003",
          "quote": "Hello, I'm Ada."
        }
      ]
    },
    {
      "criterion_id": "S_CLARITY",
      "answer": "scale",
      "value": 10,
      "explanation": "The operator gives one clear, coherent sentence answering the question. This fixture does not verify company opening hours.",
      "evidence": [
        {
          "message_id": "m0003",
          "quote": "Support opens at 09:00."
        }
      ]
    },
    {
      "criterion_id": "S_ID",
      "answer": "na",
      "value": null,
      "explanation": "Only general opening hours are requested; no protected account action requires identification.",
      "evidence": [
        {
          "message_id": "m0001",
          "quote": "What time does support open?"
        }
      ]
    },
    {
      "criterion_id": "S_FLAG",
      "answer": "no",
      "value": null,
      "explanation": "Both operator turns were checked and neither contains an insult. These are real checked turns, not an invented absence quote.",
      "evidence": [
        {
          "message_id": "m0003",
          "quote": "Hello, I'm Ada. Support opens at 09:00."
        },
        {
          "message_id": "m0005",
          "quote": "Happy to help. Goodbye."
        }
      ]
    }
  ],
  "diagnostics": {
    "provider": "synthetic-contract-fixture",
    "model": "not-a-model",
    "prompt_version": "example-only",
    "attempt_count": 0,
    "input_tokens": null,
    "output_tokens": null,
    "estimated_cost_usd": null,
    "latency_ms": null,
    "warnings": []
  },
  "request_id": "11111111-1111-4111-8111-111111111111"
}
```

## Машиночитаемые схемы и совместимость двух реализаций

Полные схемы находятся в `plan.json → contracts.json_schemas`: `evaluation_request`, `evaluation_result`, `provider_output`, `error`. Сейчас они встроены в план, отдельные файлы не создаются. В T02 их переносят в `contracts/` вместе с fixtures без независимых ручных вариантов, а ссылку в plan фиксируют. Java DTO/Python schemas должны принимать/отвергать одинаковые fixtures; генерация DTO допустима, но не заменяет semantic checks. Unknown fields запрещены. Один контракт, две реализации.

Diagnostics: provider/model/prompt_version — nonblankstring; attempt_count integer0..2 (production≥1); tokens/latency неотрицательные integer|null; estimated_cost_usd finite number≥0|null; warnings unique allowlist. `contract_version`, `request_id` и message identity не получаютот LLM. Выбор provider/framework не меняетэтот JSON.

## Contract tests и совместная приёмка

- CT01 complete valid synthetic
- CT02 missing/duplicate/unknown criterion
- CT03 discrete scales/NA/flag
- CT04 unknown ID/forged quote/blank
- CT05 changed arbitrary criterion
- CT06 concurrent checklist edit during model call
- CT07 invalid/empty JSON, timeout, 429, no persistence
- CT08 all-attempt usage/cost and no secrets
- CT09 original/final review immutability
- CT10 bot/operator/system identity, RU/KZ/EN and timestamps
- CT11 Java/Python same strict JSON positive/negative fixtures and HTTP status/error envelopes
- CT12 Wrong request/conversation/checklist/version echo rejected by Java; no result persisted
- CT13 Java BigDecimal vs legacy Python/Fraction5184 cases plus custom scales/all-NA/rounding edges
- CT14 HTTP connection refused/slow/invalid bytes/oversize/version mismatch; no Java POST retries
- CT15 Persisted request lifecycle, reload/batch progress, duplicate intent and unknown outcome

Одинаковые fixtures проверяются Java и Python; HTTP tests добавляют status/content-type/body bytes/timeouts, Unicode и identity mismatches. JUnit/Fraction parity, fileDB restart/concurrent review и browser workflow отдельны. Offline mock provider допустим только в tests, не какготовый AI впродукте. Live own-synthetic E2E и changed-checklist run выполняются после privacy/budget/config. CI не делает платныхвызовов.

## Breaking changes перед реализацией

### BC01

Fullstack runtime/launch changes to Java 21/Maven/8080 + Python ML :8001 + Vanilla static assets; old npm/uvicorn fullstack commands are legacy.

Farhat + Nurtas: ports, env names, framework version, start order. Задачи: T02, T03, T18.

### BC02

In-process Python evaluator/shared Pydantic replaced by HTTP POST /v1/evaluate with contract2.0.0, request_id/full checklist and identity echoes.

Both approve exact request/response/error schema and shared fixtures before implementation. Задачи: T02, T10, T11, T13.

### BC03

Public API requires explicit checklist_version, expected_version on edit and request_id on auto; adds request-status and dataset-fetch endpoints.

Both approve fields/endpoints/status codes; Java and UI merged together. Задачи: T02, T05, T07, T12, T21.

### BC04

Strict no-coercion/extra-field/nonfinite/blank validation rejects previously accepted invalid payloads.

Both approve validators/negative fixtures; no silent repair. Задачи: T02, T04, T11.

### BC05

Java-owned SQLite schema + immutable snapshots + atomic review revisions; no assumed drop-in compatibility with legacy DB.

Both approve source/history preservation and migration approach; default new target DB, old untouched. Задачи: T05, T06.

### BC06

Java BigDecimal scorer is authoritative; Python math retained only as reference. Semantics/IDs/criteria remain unchanged.

Both approve parity evidence and rounding convention; any scoring/message-ID semantic change requires new agreement. Задачи: T02, T04, T16.

### BC07

Network timeout/unknown result handling and no automatic Java POST retry; batch reconciles persisted request state.

Both approve deadlines/retry ownership/error codes and duplicate-charge limitation. Задачи: T02, T13, T21.
