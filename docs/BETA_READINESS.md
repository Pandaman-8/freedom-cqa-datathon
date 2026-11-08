# Fullstack BETA — доступ к данным и проверка продукта

Работа: `codex/T14-dynamic-ai`, исходный main `cbd7771`. Java/Vanilla изменения;
Python admission v2 Нуртаса интегрирован отдельной веткой; contract2.0.0, Prompt v4, scoring
и SQLite schema сохранены.

## Что меняется

Основной путь: диалог → «Оценить с ИИ» → компактный результат → точная цитата →
апелляция. Ручная форма свёрнута; UUID/revision/contract находятся в подробностях.
Одинаковые original/final показываются один раз. При изменённом ответе, объяснении,
evidence или score исходный снимок остаётся в раскрываемой истории. После сохранения
версии есть «Оценить по новой версии»; это переход к выбранному диалогу, не автоматический POST.

`GET /api/ai/status` — новый Java/UI endpoint, не изменение Python contract2.0.0.
Параметры выбранного контекста: `conversation_id`, `checklist_key`, `checklist_version`
(все три или ни одного). Ответ: `ml_configured`, `ml_reachable`, `ml_ready`,
`selection_allowed`, `ready`, `data_mode`, `reason`, `rubric_confirmation_required`,
`confirmation_scope`. Он делает только bounded GET
Python `/health`; никаких transcripts, rubric, credentials или provider POST.
`ml_configured` означает корректный Java ML URL; `ml_ready` — ответ readiness Python.
Readiness не проверяет квоту, реальные credentials у провайдера или его качество.
`ready` разрешает попытку с точки зрения Java и health; Python независимо проверяет
допуск на своём POST и может отклонить его. Отказ не превращается в фиктивный результат.

## Admission v2 — текущая доработка

Технический формат v2 согласован по сообщению Farhat. Java теперь использует
`checklist_scope` вместо списка полных snapshots, отдельный opt-in внешней обработки,
явное UI-подтверждение рубрики и проверку совместимости Python health. Новая валидная
версия внутри выбранного key/range не требует правки grant или исходников.

Актуальные поля, конфигурация, миграция, проверка отзыва и точный статус совместного
прогона: [DYNAMIC_ADMISSION.md](DYNAMIC_ADMISSION.md). Оба коммита Python-only patch Нуртаса интегрированы; общий DEV HTTP-прогон
проверен с изолированным offline provider, без подмены admission. Внешняя передача DEV не разрешена этим
техническим согласованием. Все результаты ниже относятся к предыдущей BETA-проверке.

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
