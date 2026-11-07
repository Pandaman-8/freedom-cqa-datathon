# Local REST API contract (FastAPI)

Open interactive documentation after backend start: **http://127.0.0.1:8000/docs**.

| Endpoint | Meaning |
|---|---|
| `GET /api/health` | API health and evaluator readiness |
| `POST /api/datasets/import` | Import exact organizer envelope, idempotent; reject changed source under existing ID |
| `GET /api/conversations` | List imported conversations with IDs, language, channel |
| `GET /api/conversations/{id}` | Original transcript + `messages[]` with stable `mNNNN` IDs |
| `GET /api/checklists` | Latest version of each checklist |
| `GET /api/checklists/{key}?version=N` | Latest or historical configuration |
| `PUT /api/checklists/{key}` | Create new immutable version of existing checklist from ChecklistDraft |
| `POST /api/checklists/{key}` | Create new checklist under a new key (not `chat-quality`) |
| `POST /api/evaluations/manual` | Save a human-prepared CriterionAnswer[] and calculated score |
| `POST /api/evaluations/auto` | Future ML bridge, currently returns 501 |
| `GET /api/evaluations?conversation_id=...` | History (original and final scores) |
| `GET /api/evaluations/{id}` | Detailed original/final answers, scores and appeal history |
| `POST /api/evaluations/{id}/appeals` | Request manual review for one criterion |
| `POST /api/appeals/{id}/resolve` | Confirm or replace answer, recalculate final score |

## Payload examples

Checklist PUT: send `title`, `description`, `sections[]`, `criteria[]` as in `backend/app/seed/chat_quality.json`, **omitting** `key` and `version`. New versions are assigned by backend.

Manual evaluation:

```json
{
  "conversation_id": "DEV:synthetic-001",
  "checklist_key": "chat-quality",
  "answers": [
    {
      "criterion_id": "C01",
      "answer": "yes",
      "value": null,
      "explanation": "Operator greets and introduces themself in first reply.",
      "evidence": [
        {"message_id": "m0003", "quote": "Hello, I'm Ada from support."}
      ]
    }
  ]
}
```

**The example above illustrates just one criterion; a valid request must contain answers for ALL criteria in the selected checklist.** A `scale` answer also needs its `value`; a `na` answer must not carry a numeric value. Evidence quotes are validated as exact substrings of the referenced source messages.

Appeal:

```json
{"criterion_id":"C04","comment":"Прошу пересмотреть неполный ответ"}
```

Review:

```json
{"decision":"confirm","reason":"Оригинальная оценка корректна"}
```

Or `{"decision":"change","reason":"Причина исправления","replacement":<FULL CRITERION ANSWER>}` where replacement is a complete valid CriterionAnswer (same `criterion_id` as the appeal, with evidence).
