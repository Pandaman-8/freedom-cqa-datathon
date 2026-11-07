# Java REST API — текущая реализация

Base: `http://127.0.0.1:8080`, JSON/UTF-8, same-origin с Vanilla UI. Java не публикует Swagger `/docs`. Отдельный Python имеет `/health` и `POST /v1/evaluate`; его wire envelope **2.0.0** описан в [INTEGRATION_CONTRACT.md](INTEGRATION_CONTRACT.md). Эта страница документирует существующие endpoints, не меняет их.

| Method / route | Body / условия | Успех |
|---|---|---|
| GET `/api/health` | Java liveness, не ML readiness | 200 |
| POST `/api/datasets/import` | `isSuccess`, `data.dataset_group_id`, `total_records`, `records[]`; organizer envelope, до 16 MiB | 200 |
| POST `/api/datasets/fetch` | `{group_id}`; приватный URL только в Java config | 200 |
| GET `/api/conversations` | Все summaries; фильтрация группы/языка в UI | 200 |
| GET `/api/conversations/{id}` | URL-encoded composite ID, transcript/messages/audio_url | 200 |
| GET `/api/checklists` | Latest для каждого key | 200 |
| GET `/api/checklists/{key}?version=N` | Убрать version для latest | 200 |
| POST `/api/checklists/{key}` | ChecklistDraft, новый key → v1 | 200 |
| PUT `/api/checklists/{key}?expected_version=N` | ChecklistDraft, CAS latest → новая версия | 200 |
| POST `/api/evaluations/manual` | conversation_id, checklist_key, **checklist_version**, answers | 201 |
| POST `/api/evaluations/auto` | **request_id UUID**, conversation_id, checklist_key, **checklist_version** | 200; повтор pending — 202 + Location |
| GET `/api/evaluation-requests/{request_id}` | Только чтение persisted ledger | 200 |
| GET `/api/evaluations?conversation_id=...` | Убрать filter для всех evaluations | 200 |
| GET `/api/evaluations/{id}` | Original/final, pinned version, appeals, review_revision | 200 |
| POST `/api/evaluations/{id}/appeals` | `{criterion_id,comment}` | 201 |
| POST `/api/appeals/{id}/resolve?expected_revision=N` | `{decision,reason,replacement}`; current aggregate revision | 200 |

ChecklistDraft: `title`, `description`, `sections[]`, `criteria[]`, без key/version. Каждому section соответствует существующий criterion.section_id; criterion задаёт kind binary/scale/flag, weight, levels, allow_na и na_rule. UI может использовать произвольные IDs. Исторические версии не изменяются.

Manual/ML answers должны покрывать **все** критерии pinned версии. Каждый answer содержит `criterion_id`, `answer`, `value`, `explanation`, `evidence:[{message_id,quote}]`. `value` — точный configured level только для scale, иначе null. N/A разрешён только allow_na; цитата — дословная непустая подстрока существующего message. Полный синтетический вход/answers для тестовой подготовки находятся в `ml-service/tests/fixtures/*/{request,expected}.json`; это ML envelope, не готовое тело публичного Java endpoint.

## Review и CAS

```json
{"criterion_id":"LOCAL_CLARITY","comment":"Прошу проверить выбранный уровень"}
```

После создания appeal перечитайте evaluation: revision увеличился. Передайте его **query parameter** при resolve, не поле JSON. Confirm:

```json
{"decision":"confirm","reason":"Текущий ответ подтверждён","replacement":null}
```

Для change replacement — полный ответ на тот же criterion с exact evidence. Причина обязательна. Duplicate/open/stale/resolved conflicts возвращают 409 REVIEW_CONFLICT; UI сохраняет draft и перечитывает состояние без автоматического retry. Original snapshot неизменен, final рассчитывается Java.

## AI lifecycle и ошибки

Ledger status: `pending`, `succeeded`, `failed`, `unknown`; поля `request_id`, `status`, `evaluation_id`, `error`. Одинаковый UUID/payload возвращает прежний результат/ошибку без ML. Иной payload с этим UUID — 409 REQUEST_ID_CONFLICT. Reload/GET не запускает inference; новая попытка — только явно новый UUID. После restart незавершённый pending становится unknown. Политика/ресурсы/Java URL проверяются до claim; rejected preflight UUID даёт 404. Ошибка уже вызванного Python сохраняется в ledger.

| HTTP | Значение |
|---|---|
| 422 | INVALID_INPUT: strict types, duplicate/extra fields, evidence/composition/version errors |
| 404 | NOT_FOUND: отсутствует source/checklist/version/evaluation/request |
| 409 | VERSION_CONFLICT / REVIEW_CONFLICT / REQUEST_ID_CONFLICT |
| 413 | PAYLOAD_TOO_LARGE: import 16 MiB, прочие Java bodies 1 MiB |
| 501 | EVALUATOR_UNCONFIGURED: Java ML URL отсутствует/невалиден или Python без provider config |
| 502 | EVALUATOR_INVALID_OUTPUT / EVALUATOR_PROVIDER_ERROR |
| 503 | PRIVACY_POLICY_UNCONFIGURED / EVALUATOR_BUSY / auth/rate-limit; также safe Organizer errors |
| 504 | EVALUATOR_TIMEOUT: исход может быть unknown |

Error envelope: `detail:{code,message,retryable,request_id}` (Organizer errors документированы в server/README.md). Не выводить raw source/provider body/URLs. Неожиданный Java fault может вернуть пустой 500; клиент не должен считать его безопасным основанием повторить POST. `retryable` не означает автоматический retry.

Java HTTP deadline70s, browser75s; Python максимум2 attempts за65s, Java POST replay=0. Timeout не доказывает отмену/отсутствие оплаты. Batch использует эти же single-item endpoints, без отдельного `/batch` API.

Подробности и проверенные команды: [server/README.md](../server/README.md), [release report](RELEASE_READINESS.md).
