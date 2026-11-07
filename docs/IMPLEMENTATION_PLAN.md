# Freedom CQA — план реализации для Farhat и Nurtas

Редакция **java-vanilla-http-ml/2**. Единственный источник статусов/зависимостей/DoD — [plan.json](../plan.json). [Исторический аудит и решение миграции](CODEX_AUDIT.md), [единый HTTP контракт](INTEGRATION_CONTRACT.md). Это обновление существующего плана: реализация не начата.

## Цель, стек и границы

**Java 21 + Spring Boot MVC/JDBC/SQLite**, frontend **HTML5/CSS3/Vanilla JS**, отдельный **Python ML HTTP service**. Java раздаёт static assets и /api на 8080; ML слушает loopback8001. FastAPI разрешён только внутри ML по выбору Nurtas. Java владеет domain logic/DB/scoring; Python возвращает grounded answers, никогда totals.

Полный MVP: DEV/CONTROL import → checklist/version → real AI → scores/weights/sections/evidence/NA → appeal/review → immutable original/derived final → arbitrary criterion через UI → минимальный batch. Без регистрации; organiser credentials только Java, provider key только Python. Legacy исходники сохраняются как reference. Никаких очередей/Redis/JPA/production infrastructure.

Сохраняем **28 задач: P0=21, P1=4, P2=3**. T21 batch поднят в P0. T28 production design заменён необязательной полировкой demo; production-grade задач нет. P2audioT26 пересматривается, если организаторы подтвердят обязательность; до этого не придумывать voice rubric.

## Порядок разработки и немедленный параллелизм

1. T02: Farhat+Nurtas согласуют один JSON Schema, fixtures, HTTP/errors/deadlines и семь breaking changes; фиксируют Spring Boot version. Любые дальнейшие JSON/API/field/scoring/message-ID/validation изменения — только совместно ДО реализации.
2. T01: недостающий rubric/H0/privacy/audio уточняются без повторного полного аудита. До PDF seed provisional; безопасная инженерная работа возможна, G1 не закрывается.
3. После T02 Farhat начинает T03 Java/Vanilla foundation, затем T04 Java DTO/scoring и T05 SQLite/REST/version pinning. Nurtas независимо выполняет T08/T09 и T10/T11 Python HTTP/model/validation. Ему не нужно ждать Java DTO: общие fixtures уже зафиксированы.
4. T12: Vanilla editor/selection/results/evidence/appeal forms. T13: настоящий Java↔Python E2E. T06/T14: atomic appeals, immutable snapshots, reviewer decisions, UI criterion replacement и v1 history.
5. T07/T21: organizer fetch и обязательный минимальный DEV/CONTROL batch. Затем T15/T16/T17 quality/contracts/browser/restart и measured capacity; T18/T19 release/rehearsal; T20 H23–H24 CONTROL/freeze.

Выбор Spring MVC снижает ручную инфраструктуру REST/validation/JDBC/tests; Javalin допустим только при готовом проверенном шаблоне до T03. JDK HttpServer требует лишнего plumbing. Подробное сравнение и официальные ссылки — в аудите. Java 21 есть, mvn/gradle отсутствуют: wrapper download/start smoke включён T03. Java build пока не проверен.

## Frontend без framework

`server/src/main/resources/static/`: index.html, styles.css, native JS modules api/state/datasets/checklist/results/review/batch. Одна страница с views и явным state, DOM templates/textContent, event delegation и same-origin fetch. Стабильные внутренние draft IDs не равны редактируемым criterion IDs. Request tokens/AbortController защищают навигацию; duplicate submits блокируются; forms/errors доступны с клавиатуры. Полные results показывают raw points, исходный и effective weight, normalized contribution, section totals, explanation/NA и original/final. Evidence ведёт к message ID, audio player/link сохраняется; offset нельзя выводить из ISO timestamps без recording origin.

## Время, ресурсы и критический путь

H0 неизвестен; T0 — начало реализации, не официальный старт. Ниже условный resource-feasible график двух участников. T01 требует внешних ответов: его .5 ч — активная сверка, не обещание получить PDF за 30min. Joint занимает обоих. Все оценки активные; внешнее ожидание и inference могут увеличить elapsed time.

| Задача | Исполнитель | От T0, часы | Результат |
|---|---|---|---|
| T02 | Joint | 0–0.5 | Зафиксировать JSON HTTP contract и владение |
| T01 | Joint | 0.5–1 | Сверить недостающий rubric и официальный тайминг |
| T03 | Farhat | 1–2.5 | Создать Java backend и Vanilla frontend foundation |
| T08 | Nurtas | 1–1.5 | Выбрать ML provider, бюджет и data policy |
| T09 | Nurtas | 1.5–2.5 | Перенести synthetic gold и dynamic prompts в ML service |
| T04 | Farhat | 2.5–4.5 | Перенести DTO validation и deterministic scoring в Java |
| T10 | Nurtas | 2.5–4.5 | Реализовать отдельный Python ML HTTP service |
| T05 | Farhat | 4.5–7 | Перенести REST import, checklist versions и evaluation storage |
| T11 | Nurtas | 4.5–5.5 | Проверить сетевой контракт, grounding и ML errors |
| T12 | Farhat | 7–10 | Перенести checklist, results и review UI на Vanilla JS |
| T13 | Joint | 10–10.75 | Пройти настоящий Java↔Python AI E2E |
| T06 | Farhat | 10.75–12.5 | Перенести immutable snapshots и atomic appeals/review |
| T14 | Joint | 12.5–13.25 | Пройти AI appeal/review и замену criterion через UI |
| T07 | Farhat | 13.25–14 | Добавить Java organizer adapter и group_id UI |
| T15 | Nurtas | 13.25–14.25 | Проверить RU/KZ/EN и calls quality |
| T21 | Farhat | 14–15 | Минимальный последовательный DEV/CONTROL batch |
| T16 | Farhat | 15–16.25 | Проверить Java regression, contracts, restart и browser flows |
| T17 | Nurtas | 15–15.75 | Обработать 65 DEV и измерить CONTROL capacity |
| T18 | Farhat | 16.25–17 | Подготовить воспроизводимый Java+ML release |
| T19 | Joint | 17–17.5 | Пройти G1–G7 pre-CONTROL и пятиминутную защиту |
| T20 | Joint | 20.5–21.5 | Выполнить CONTROL batch и стоп-код |

T20 реально приходится на **H23–H24**; строка 20.5–21.5 показывает необходимое окно, а не вычисленный H0. Между rehearsal17.5 и CONTROL20.5 заложено 3 ч резерва. До H23 нужно 20.5 ч остатка; до H24 —21.5 ч. Диапазон rehearsal17.5–24 ч, вместе с reserve/control21.5–28 ч. Риск не уложиться в 24 ч существенный даже при полном дне; без H0 обещания невозможны. Прежняя оценка 11.25/15.25 ч отозвана.

Активная нагрузка: Farhat отдельно 14.5 ч, Nurtas отдельно 6.25 ч, Joint по 4 ч каждому; всего 28.75 человеко-часов. Ресурсный bottleneck — Farhat. T03/T04/T05/T06/T12 включают 10.75 ч переноса Fullstack; это уже внутри оценки, не добавка сверху. Зависимостный critical path без ограничения исполнителей: T02 → T03 → T04 → T05 → T12 → T13 → T21 → T16 → T18 → T19 =13.75 ч до rehearsal; это **не** исполнимый срок одного Fullstack.

Рубежи: mount к 2.5 ч, scorer к 4.5 ч, storage к 7 ч, real AI E2E к 10.75 ч, appeal/editor к 13.25 ч, batch к 15 ч, release к 17 ч, rehearsal к 17.5 ч. Срыв mount/HTTP E2E требует немедленного пересчёта; дополнительные фичи не расходуют резерв. P1/P2 уже исключены. Обязательные workflows/batch не снимаются молча.

## Каталог 28 задач

Точные affected files, inputs/outputs, risks, verification commands и DoD пересмотрены в JSON. Указанные там новые пути — будущие файлы, сейчас не созданные.

| ID | P / owner | Работа | Dependencies | Часы | Acceptance |
|---|---|---|---|---|---|
| T01 | P0 / Joint | Сверить недостающий rubric и официальный тайминг | — | 0.5 | Сверить 8 criteria/levels/NA с отсутствующим PDF; пока недоступен — G1 blocked, seed provisional. Установить H0/H23/H24, audio applicability и источник фактов C04; не выдумывать ответы. |
| T02 | P0 / Joint | Зафиксировать JSON HTTP contract и владение | — | 0.5 | Оба приняли contract2.0.0, endpoint/request/response/errors/validation и breaking changes ДО реализации. Framework/version, JSON Schema и одинаковые positive/negative fixtures согласованы; один контракт, две реализации. |
| T03 | P0 / Farhat | Создать Java backend и Vanilla frontend foundation | T02 | 1.5 | Java 21 wrapper build/test/start проходит; GET /api/health и HTML/ES module открываются на 8080. Pinned Spring Boot MVC/JDBC/SQLite dependencies; legacy source не удаляется; no React/JSX/Vite Fullstack target. |
| T04 | P0 / Farhat | Перенести DTO validation и deterministic scoring в Java | T02, T03 | 2 | BigDecimal port сохраняет 5184 эталонных комбинации, HALF_UP только на итоговом округлении; no binary double arithmetic. N/A/scale/flag/section/all-NA и finite/blank/duplicate validation проверены; нет доверия model totals. Java DTO/Python schemas принимают одинаковые synthetic fixtures, numeric strings/bools rejected. |
| T05 | P0 / Farhat | Перенести REST import, checklist versions и evaluation storage | T04 | 2.5 | REST controllers/SQLite repositories покрывают импорт, list/detail, checklist CRUD/version history и manual/auto lifecycle. Atomic/idempotent import сохраняет все роли/строки/timestamps и positional IDs; duplicate timestamps не объединяются. Pin explicit checklist_version до HTTP; no latest reread; expected_version conflict409; transaction не держится при inference. Java единственный DB writer; required endpoints из endpoints_current имеют parity tests; ML endpoint может оставаться truthful501 до T13. |
| T06 | P0 / Farhat | Перенести immutable snapshots и atomic appeals/review | T05 | 1.75 | Original answers/score/scoring_version неизменны; reviewer reason/replacement отдельны; final derived из pinned version. Concurrent create/resolve защищены SQL constraint + revision/transaction; stale409 не переписывает решение. File DB restart сохраняет результаты; legacy DB не меняется. Если нужен перенос старой истории — counts/IDs/versions сверены и reconstructed scores явно помечены. |
| T07 | P0 / Farhat | Добавить Java organizer adapter и group_id UI | T03, T05 | 0.75 | POST /api/datasets/fetch {group_id} сохраняет upstream signature params; URL/secret только Java env. Envelope validation/atomic import общий с upload; safe errors, no secret in browser/logs. |
| T08 | P0 / Nurtas | Выбрать ML provider, бюджет и data policy | T02 | 0.5 | Provider/model выбран по structured-output/KZ/context smoke; бюджет и actual price source заданы. Real data external inference только в согласованном режиме; до этого own synthetic. |
| T09 | P0 / Nurtas | Перенести synthetic gold и dynamic prompts в ML service | T02 | 1 | Минимум 2 own synthetic cases на RU/KZ/EN + voice/bot/NA/omission/changed criterion; ожидаемые labels размечены человеком. Prompt собирается из полного checklist, без hardcoded8 IDs; C04 factual uncertainty не превращается в NA. |
| T10 | P0 / Nurtas | Реализовать отдельный Python ML HTTP service | T08, T09 | 2 | POST /v1/evaluate и GET /health на 127.0.0.1:8001; strict request/response contract2.0.0. Real provider returns answers only; metadata из SDK; no DB/scoring dependency on legacy backend. Две provider attempts максимум внутри 65s; actual usage всех попыток; configured model/cost, unknown=null. |
| T11 | P0 / Nurtas | Проверить сетевой контракт, grounding и ML errors | T10 | 1 | Missing/unknown/duplicate criterion, forged/blank quotes, extra fields, duplicate JSON keys/nonfinite отвергаются. Общие fixtures проходят Python transport и Java-facing JSON tests; invalid output never converted to fabricated NA. Timeout/429/auth/wrong version/oversize дают согласованные safe errors и request_id. |
| T12 | P0 / Farhat | Перенести checklist, results и review UI на Vanilla JS | T03, T05 | 3 | Выбор key/version, редактор wording/weight/type/levels/NA/sections и произвольного criterion; UI не hardcodes IDs. Result: answer/raw/weight/effective weight/normalized contribution/sections/explanation/NA; original/final и appeals/review forms. Exact message jump + player/link; роли/timestamps сохранены; textContent защищает от transcript HTML. Native ES modules + fetch, pending/error/retry states; базовая защита stale responses/draft leakage/duplicate submits входит P0. Review forms integrated окончательно T14. |
| T13 | P0 / Joint | Пройти настоящий Java↔Python AI E2E | T05, T10, T11, T12 | 0.75 | UI → Java → Python HTTP → real model → validated answers → Java score → SQLite → UI на own synthetic. Java проверяет contract/request/conversation/checklist identity, complete answers и exact quotes независимо от Python. GET request status, timeouts и отсутствие автоматического POST replay проверены; fixture явно не выдаётся за real model. |
| T14 | P0 / Joint | Пройти AI appeal/review и замену criterion через UI | T06, T13 | 0.75 | Real AI→appeal→confirm/change с reason работает; original immutable, final пересчитан Java. Новый arbitrary criterion и version2 оцениваются без code/prompt edits; historyv1 остаётся v1. |
| T15 | P0 / Nurtas | Проверить RU/KZ/EN и calls quality | T14, T09 | 1 | Human labels/safety/role/NA gold assertions проверены; exact substring не считается semantic quality. Voice ISO timestamps/long contexts/audio playback проверены; без звука нет выводов о дикции/интонации. |
| T16 | P0 / Farhat | Проверить Java regression, contracts, restart и browser flows | T07, T14, T04, T21 | 1.25 | JUnit/Maven checks + общие JSON fixtures + two-service E2E и реальный browser workflow проходят. SQLite file restart/concurrent version/review/timeout safe errors и batch resume не теряют original/results. Python legacy tests только reference; отдельно зафиксированы Java/Python/browser результаты. |
| T17 | P0 / Nurtas | Обработать 65 DEV и измерить CONTROL capacity | T15, T08, T01, T21 | 0.75 | Все 65 DEV учтены: result/error/pending без silent skips; required failures не маскируются как complete. Measured seconds/item × CONTROL size и worst-case65s/item, retries/cost budget проверены; inference wall time сверх active estimate учитывается. |
| T18 | P0 / Farhat | Подготовить воспроизводимый Java+ML release | T16 | 0.75 | Fresh checkout: Java wrapper package/start + ML start + static UI доступны по инструкции; pinned deps, env paths. Старые README/AGENTS architecture согласованно обновлены во время реализации; сейчас не изменяются. Public release privacy scan без PDF signature/transcripts/audio/DB/.env; remote visibility проверяется участником. |
| T19 | P0 / Joint | Пройти G1–G7 pre-CONTROL и пятиминутную защиту | T01, T17, T18, T14 | 0.5 | G1–G6 фактически passed; pre-CONTROL часть G7 пройдена; post-CONTROL не выдаётся за готовую заранее. Rehearsal≤300s: dialogue1min, results/evidence/NA2min, appeal1min, criterion1min; model/cost disclosure. |
| T20 | P0 / Joint | Выполнить CONTROL batch и стоп-код | T19 | 1 | На H23 actual CONTROL/group_id, новая checklist version через UI, batch records без silent skips. На H24 freeze согласно правилам, дальнейшие действия через UI; если CONTROL не помещается, сообщить фактический статус. Commit/push только в отдельно разрешённом этапе, не сейчас. |
| T21 | P0 / Farhat | Минимальный последовательный DEV/CONTROL batch | T13, T07 | 1 | P0: snapshot списка conversation IDs и checklist key/version; один in-flight single-item request, progress/success/error/pending. Pause/resume между items, continue после явной ошибки, явный retry failed; reload сверяется с persisted request/results, pending/unknown не запускается повторно молча. Нет отдельной очереди/Redis/workers; batch frontend orchestration над Java single-item API с persisted request ledger. |
| T22 | P1 / Nurtas | Расширить human gold/holdout quality analysis | T15 | 1.5 | Раздельные development/holdout own synthetic cases и criterion-level ошибки; не подменять P0 smoke. |
| T23 | P1 / Farhat | Улучшить Vanilla drafts и навигацию | T12 | 0.75 | Дополнительное восстановление несекретных drafts/keyboard usability; базовые race protections уже P0 в T12. |
| T24 | P1 / Farhat | Обновлять audio locator без смены source identity | T07, T05 | 0.75 | URI-only refresh не меняет message IDs/evaluation history; semantic content conflict остаётся 409. |
| T25 | P1 / Nurtas | Расширить adversarial ML cases | T11, T15 | 0.75 | Transcript prompt injection/semantic misuse probes; strict contract и grounding остаются обязательными P0. |
| T26 | P2 / Nurtas | Уточнённые audio segments/prosody при обязательности | T15, T01 | 3 | Только после ответа Q02; если обязательны — повысить priority и пересчитать сроки; новый evidence формат согласуют оба. |
| T27 | P2 / Farhat | Pagination по результатам измерений | T21 | 1.5 | Все записи доступны без потерь; оптимизация только после подтверждённого ограничения, не blocker малого DEV. |
| T28 | P2 / Farhat | Необязательная полировка доступности demo | T19 | 0.5 | Только после P0/gates и при свободном времени: focus/labels/контраст; никаких production инфраструктурных задач. |

DoD каждой задачи: все AC проверены указанными командами/сценариями, второй участник проверил shared boundaries, совместные изменения заранее согласованы, diff без private data, реальные completion evidence записаны в JSON. Только после этого task может стать done. Имена будущих команд не означают выполненные проверки.

## Владение, contract lock и merge

- **Farhat**: `server/**`, `plan.json`, `README.md`, `AGENTS.md`, `.github/**`.
- **Nurtas**: `ml-service/**`.
- **Joint_approval_Farhat_edits**: `contracts/**`, `docs/INTEGRATION_CONTRACT.md`, `docs/api-contract.md`, `docs/ml-contract.md`, `backend/app/seed/chat_quality.json`.

Любое изменение JSON, API endpoints, названий полей, семантики оценок, message IDs или validation согласуют Farhat и Nurtas ДО реализации. Один language-neutral JSON Schema; Java DTO и Python schemas — две проверяемые реализации.

Отдельный clone/worktree и локальная БД каждого; не переключать branch и не править общие файлы в одном каталоге параллельно.

Порядок merge:

- T02 shared schema/fixtures contract lock
- T03 Java+Vanilla foundation; parallel T08/T09
- T04/T05 Java scorer/DTO/storage; parallel T10/T11 Python HTTP
- T12 UI then T13 real integration
- T06/T14 review+criterion
- T07/T21 P0 batch
- T15/T16/T17 quality/regression/DEV
- T18/T19 release rehearsal; T20 CONTROL

Farhat правит shared schema/fixtures после review Nurtas; Nurtas не меняет Java scorer. У каждого свой clone/worktree/DB. Малые PR, второй reviewer, contract checks до merge. Конфликт согласовать с владельцем; no reset/force-push чужой работы. Legacy backend/frontend не служат местом новой Fullstack реализации. README/AGENTS/CI обновляются только в будущей T18, сейчас разрешены ровно четыре planning файла.

Будущие автоматические checks:

```bash
./server/mvnw -f server/pom.xml verify
PYTHONPATH=ml-service python -m pytest -q ml-service/tests
```

Отдельно browser workflow и live synthetic Java↔Python HTTP E2E после настройки provider/privacy/budget. CI использует synthetic fixtures/mock transport, не оплачиваемые реальные вызовы. Старые 13 Python tests не заменяют Java tests. Maven build не заменяет проверку браузера.

## Минимальный batch — P0/T21

Java single-item API + последовательная browser orchestration; snapshot key/version и полного списка IDs; один in-flight; progress, success/error/pending, pause/resume между items, явный retry failures. Request ledger хранится Java; reload сверяет outcomes, unknown не повторяется автоматически. Batch manifest содержит только IDs/версии/status, не transcript. Нет отдельной distributed queue. Смена editor version не подменяет уже стартовавший batch; новый batch закрепляет новую версию.

T17=.75 ч — активный анализ, inference отдельно. 65×65s≈70.4min без overhead; CONTROL size неизвестен. Замерить average/p95/worst-case и стоимость всех attempts до H23. Если throughput недостаточен — согласовать model/budget/limits заранее и повторить quality, а не скрывать skipped records. G7 требует реальные обязательные результаты.

## Quality gates G1–G7

### G1 — Фундамент и контракт

Задачи: T01, T02, T03, T04, T05.

- Original rubric сверён; без PDF gate не закрывать.
- Java Maven/JUnit tests и Vanilla browser mount passed; legacy tests не заменяют их.
- Farhat/Nurtas приняли один JSON HTTP contract и одинаковые fixtures.

### G2 — Один настоящий автоматический результат

Задачи: T13.

- Own synthetic через UI→real provider→validation→score→persist→UI.
- Origin=model только для настоящего adapter, не fixture.

### G3 — Evidence/scoring/NA

Задачи: T04, T11, T13.

- 100% принятых IDs/quotes существуют, criterion set complete.
- Allowed/forbidden NA, omissions, scale/flag проверены.
- Pinned scoring; invalid response не сохраняется.

### G4 — Appeal после AI

Задачи: T06, T14.

- Confirm/change с reason и immutable original.
- Concurrent resolve не перезаписывает decision, final пересчитан верно.

### G5 — Новый criterion через UI

Задачи: T14.

- Arbitrary ID/type/levels/NA получает model output v2 без code/prompt edits.
- v1 history неизменна.

### G6 — RU/KZ/EN/calls

Задачи: T15.

- Minimum labelled suite и human checks прошли.
- Voice timestamps/long context/audio access проверены; no prosody claims без звука.
- Data policy соблюдена, unresolved voice requirements disclosed.

### G7 — DEV/CONTROL/защита

Задачи: T17, T18, T19, T20, T21.

- P0 batch: progress/errors/pause/resume/reconciliation после reload; unknown не повторяется автоматически.
- Pre-H23: все 65 DEV учтены; обязательные оценки получены, оставшиеся failed/blocked items не маскируются и мешают полной приёмке.
- Measured cost/capacity и fresh launch; rehearsal≤300s.
- Post-H23: actual CONTROL imported, требуемые результаты готовы, no silent skips.
- H24 frozen commit; после только UI data/config.

G1 не закрывается без checklist PDF; G7 имеет pre-H23 и post-H23 стадии. Все gates пока не пройдены целиком. Числа quality cases/deadlines — engineering defaults, не выдуманные проценты жюри.

## ML quality и защита данных

Минимум 2 размеченных synthetic cases на RU/KZ/EN плюс voice/bot/NA/omission/new criterion; semantic claims проверяет человек. Exact substring необходим, но недостаточен. Bot greeting не считается operator greeting; C03 проверяет порядок identification/action. C04 external factual accuracy нельзя вывести из языковой уверенности; Q07 о company knowledge base остаётся открытым. Неопределённость не является автоматическим N/A. Для дикции/интонации нужен звук; без уточнения не добавлять voice penalties.

Provider/model/budget выбирает Nurtas в T08 с Farhat по доступу и измерениям; prices не выдумываются. Usage/cost всех оплаченных attempts суммируются, unknown=null. Real transcripts/voice — только в разрешённом режиме; public fixtures собственные synthetic. GuidePDF содержит signed API URI: не публиковать его, DEV/CONTROL, audio URLs, .env, DB, prompts/responses с private data. Java errors/ML errors очищены от raw inputs/secrets.

## Стоп-код и защита

До H23: получить реальные разрешённые DEV результаты, завершить G1–G6, проверить запуск и провести репетицию. В H23: получить настоящий CONTROL group_id, импортировать его отдельно, начать обработку и учёт ошибок. До H24: прогнать release checks и зафиксировать последний commit участником. После H24: запускать только этот commit; UI import/checklist/evaluation/review разрешены, исходники/prompt files/scoring/dependencies не менять. Обработка может продолжаться на frozen версии, но G7 проходит только когда нужные реальные результаты готовы.

| Минуты | Действие |
|---|---|
| 0:00–1:00 | Диалог, язык/канал, роли и версия checklist |
| 1:00–3:00 | Настоящий AI result, reason/evidence jump, NA, total/sections, model/cost |
| 3:00–4:00 | Appeal criterion → reviewer reason/decision → original/final |
| 4:00–5:00 | UI criterion replacement → v2 → реальная переоценка без code edit |

Заранее измерить latency последнего шага. Подготовить настоящие ранее полученные оценки для основных экранов и собственный synthetic fallback для offline демонстрации UI, явно подписанный; не выдавать его за CONTROL или за новый model call. При outage показать ошибку/существующий настоящий result. Встроенный mock/model fiction запрещён.


## Release checklist и открытые вопросы

- REL01: G1–G6 реально пройдены, source/privacy blockers не скрыты.
- REL02: DEV/CONTROL учтены, no silent skips, конфигурация закреплена.
- REL03: AI review/new criterion/v1 history работают.
- REL04: Clean launch, lock/constraints, public repo; ссылку отправляет участник.
- REL05: Staged diff без real data/audio/URLs/PDF sig/.env/SQLite.
- REL06: H23 CONTROL, H24 final commit; далее только UI.
- REL07: Timed rehearsal≤300s, model/cost honest, no fake fallback.

- **Q01** Предоставить отсутствующий checklist PDF. Блокирует: Официальная сверка seed/G1; provisional development возможна.
- **Q02** Как применять chat rubric к calls; обязательны ли автоматические prosody/audio-segment evidence или достаточно message+player? Блокирует: Voice-specific rules/T26. Если обязательны — пересчитать scope и поднять priority.
- **Q03** Разрешена ли отправка транскриптов/реальных звонков выбранному external LLM; retention/data constraints? Блокирует: Любые реальные external calls; до ответа только own synthetic или разрешённый local inference.
- **Q04** Точное H0, CONTROL, freeze и время выступления? Блокирует: Календарные deadlines, не относительное планирование.
- **Q05** CONTROL size, rate limits и обновление истёкших API/audio signatures? Блокирует: Capacity/refresh.
- **Q06** Бюджет, доступные ключи и оборудование local model? Блокирует: Выбор provider; не вопрос к жюри.
- **Q07** Есть ли нормативные ответы/база знаний для проверки фактической правильности консультации C04; как отмечать неподтверждаемые по transcript утверждения? Блокирует: Заявления о проверенной factual correctness; нельзя заменять недостаток знания произвольным NA или выдуманными правилами.

Student Guide доступен; ожидаемый недостающий checklist PDF: `/home/farhat/Projects/freedom-cqa-datathon/data/official/chat_quality_checklist.pdf`. Требования полностью проверенными не считаются.

## Breaking changes

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

## Следующее исполнение

Этот запрос разрешает только редактирование четырёх planning artifacts. Исходники/тесты/AGENTS.md не изменены, commit/push не выполняются. После отдельного поручения на реализацию идти по stable IDs с выполненными dependencies; T02 требует фактического принятия Farhat+Nurtas, документ сам по себе не является их согласием. Не создавать альтернативный план; новые требования связывать requirements→tasks→gates и пересчитывать baseline.
