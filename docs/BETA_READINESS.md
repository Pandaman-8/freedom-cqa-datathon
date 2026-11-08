# Fullstack BETA — доступ к данным и проверка продукта

Работа: `codex/T14-dynamic-ai`, исходный main `cbd7771`. Java/Vanilla изменения;
Python ML, contract2.0.0, scoring и SQLite schema не меняются.

## Что меняется

Основной путь: диалог → «Оценить с ИИ» → компактный результат → точная цитата →
апелляция. Ручная форма свёрнута; UUID/revision/contract находятся в подробностях.
Одинаковые original/final показываются один раз. При изменённом ответе, объяснении,
evidence или score исходный снимок остаётся в раскрываемой истории. После сохранения
версии есть «Оценить по новой версии»; это переход к выбранному диалогу, не автоматический POST.

`GET /api/ai/status` — новый Java/UI endpoint, не изменение Python contract2.0.0.
Параметры выбранного контекста: `conversation_id`, `checklist_key`, `checklist_version`
(все три или ни одного). Ответ: `ml_configured`, `ml_reachable`, `ml_ready`,
`selection_allowed`, `ready`, `data_mode`, `reason`. Он делает только bounded GET
Python `/health`; никаких transcripts, rubric, credentials или provider POST.
`ml_configured` означает корректный Java ML URL; `ml_ready` — ответ readiness Python.
Readiness не проверяет квоту, реальные credentials у провайдера или его качество.
`ready` разрешает попытку с точки зрения Java и health; Python независимо проверяет
допуск на своём POST и может отклонить его. Отказ не превращается в фиктивный результат.

## Явный допуск: configuration, не обход политики

- `CQA_ML_DATA_MODE=synthetic_only` — default: прежние шесть **точных пар** остаются
  без изменений. Ни DEV, ни новая рубрика не получают разрешение от имени группы.
- `CQA_ML_DATA_MODE=approved_dataset` вместе с `CQA_ML_APPROVAL_FILE` — отдельный режим.
  Путь абсолютный, файл приватный, рекомендуемое расширение `*.ml-approval.json`
  (ignored). Неправильный/пустой/истёкший grant, другой endpoint или scope →503 до ML
  и до ledger claim. Нет fallback в synthetic mode.

Файл заполняется **только после фактического согласования Farhat/Nurtas и условий
передачи данных**. Поля `approved_by` — локальное утверждение ответственного оператора,
не цифровые подписи и не доказательство согласия владельца данных. Не копируйте
тестовые значения approvals в рабочую конфигурацию. Разрешение на разработку режима
или согласование модели само по себе не разрешает внешнюю передачу DEV.

Структура приватного grant (значения ниже — обозначения, не действующее разрешение):

```json
{
  "approval_reference": "ссылка/номер фактического согласования условий, модели и бюджета",
  "approved_by": ["Farhat", "Nurtas"],
  "processing_mode": "external_approved",
  "destination_description": "Groq GPT-OSS 20B; согласованные условия обработки",
  "expires_at": "UTC expiration supplied by the approvers",
  "ml_url": "http://127.0.0.1:8001/v1/evaluate",
  "dataset_path": "/absolute/private/path/invoke.json",
  "dataset_sha256": "SHA256 of exact approved file bytes",
  "conversation_ids": ["explicit full composite IDs of approved chats"],
  "checklist_snapshots": ["full Checklist objects read from Java GET, not keys or wildcards"]
}
```

`processing_mode` допускает только `local_only` или `external_approved`. Local означает
реально локальную модель, подтверждённую ML-владельцем; loopback-адрес Python сам по себе
**не** означает, что Python не отправит данные в облако. Текущий Python реализует Groq,
локального провайдера в этом PR не добавлено.

Java проверяет hash исходного файла, разбирает его тем же import parser и сравнивает
полный исходный conversation projection (IDs, группа, язык, канал, все сообщения) и
полный Checklist snapshot (key/version/instructions/levels/weights/NA). В grant явно
перечисляются разрешённые conversation IDs и полные рубрики. Никаких wildcard-групп,
всех будущих версий или неявного допуска voice calls.

Новая версия: сохранить в UI → прочитать её через существующий GET → отдельно
проверить и добавить полный снимок в приватный grant обеих сторон. Java перечитывает
изменённый grant перед новым допуском; правка исходников и restart не нужны.
Рекомендуется атомарная замена файла. Удаление/порча/истечение срока немедленно
блокирует новые запросы. Уже отправленный inference этим не отменяется. Replay
сохранённого UUID остаётся чтением результата, без повторной отправки.

## Handoff Нуртасу — остающийся blocker

Подтверждённый ML-план из чата: основная модель Groq GPT-OSS20B, первая проверка
15 существующих чатов (5 RU +5 KZ +5 EN); пять звонков по transcript требуют отдельной
проверки условий передачи. В этом PR **не создаётся действующее разрешение на DEV**.

Текущий неизменённый Python `Settings.check()` допускает только `synthetic_only`,
а `/v1/evaluate` сверяет conversation с существующими synthetic fingerprints.
Поэтому даже Java grant **не делает DEV E2E рабочим автоматически**.
Нуртас должен независимо реализовать и проверить эквивалентный допуск до Groq:
точный набор/hash, явно выбранные IDs, полный rubric snapshot, endpoint/destination,
expiry/revocation, запрет неизвестных режимов и запрет fallback. Можно использовать
тот же приватный grant как локальный конфигурационный документ; он не передаётся
в evaluation_request и не меняет contract2.0.0. Формат и правила должны пройти
совместное ревью; наличие этого документа не выдаётся за полученное ML approval.

Затем, только при подтверждённых условиях передачи и бюджете, согласовать один
DEV v1→UI replacement→v2 live E2E и серию15 чатов. Обе стороны обязаны блокировать
неразрешённые snapshots. В текущей работе никаких DEV/Groq-вызовов нет.

## Проверки и границы

Новый `server/src/test/python/dev_local_smoke.py --dataset /absolute/private/invoke.json`
работает только с переданным существующим набором. Собственные Java/SQLite/loopback
tripwire; ML POST запрещён. Проверяет source identity, audio locator preservation,
idempotence, technical manual answers, review/CAS, versions, restart и явные отказы AI.
`--serve` даёт приватный localhost browser harness; Enter очищает временную БД.
Не публикуйте его screenshots, transcripts, JSON или Java logs.

Ручные ответы в harness помечены как технические, не human gold и не оценка качества.
Audio URLs сохраняются, но записи не скачиваются. CONTROL ещё не выдан/не проверен;
существующий `group_id` endpoint остаётся конфигурируемым, не требует исходников для
следующей группы. Импорт CONTROL не разрешает автоматически его внешний inference.

Новый Java integration test использует **существующую** synthetic conversation и
локальный fake HTTP server: v1, отказ v2 до approval, hot grant v2, pinned result,
duplicate UUID без POST, revoke. Это не Python/Groq E2E и не модельная интерпретация
нового критерия. Реальный DEV оценивается в этом PR только вручную/технически.

Официальный checklist PDF всё ещё отсутствует: `data/official/chat_quality_checklist.pdf`.
C01–C08 — сохранённый provisional seed, не заново подтверждённый официальный оригинал.

## Подтверждённый запуск 2026-11-08

| Проверка | Результат и границы |
| --- | --- |
| Java `clean verify` | **5982 PASS**, 0 failures/errors/skipped, BUILD SUCCESS |
| Vanilla JS unit | **27 PASS** |
| Contract validator | **72 fixtures PASS**, четыре схемы, drift и route/version PASS |
| Scoring reference | **5184 PASS**, формулы не изменены |
| Python ML offline regression | **332 PASS**, provider keys выключены; не Groq E2E |
| Packaged HTTP/JAR | Workspace, organizer, review, auto, batch PASS; локальные fixture/fake servers |
| Browser regression | **37/37 PASS**: workspace 11, auto 4, review/history 7, batch 9, private DEV 6 |
| Существующий DEV, локально | **65/65**, 1268 сообщений, 35 RU / 15 KZ / 15 EN, 60 chats / 5 calls; исходные роли, timestamps, IDs и пять audio locators сохранены |
| DEV manual/review/version/restart | PASS на временной SQLite; технические ответы не являются quality labels |
| DEV AI / batch | 65 явных policy отказов, **0 ML POST**; не успешная AI-оценка |

Браузерные результаты получены в локальном браузере и не объявляются частью GitHub CI.
Нет нового cross-browser/mobile matrix, проигрывания аудио, CONTROL-run или настоящего
DEV/Groq E2E. Фактический CI статус привязан к SHA в PR.
