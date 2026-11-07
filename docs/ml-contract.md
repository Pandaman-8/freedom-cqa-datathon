# ML teammate handoff

**Your target function**: `Evaluator.evaluate(conversation: dict, checklist: Checklist) -> list[CriterionAnswer]`, defined in `backend/app/evaluator.py`. It is a stub until a real model implementation is ready.

### Inputs

`conversation.messages` are ordered; each message has `id`, `timestamp`, `speaker` (`operator`, `client`, `bot`, `system`) and `text`. For voice calls, preserve ISO 8601. `checklist.criteria` is fully dynamic and contains ID, instruction, kind (`binary`, `scale`, `flag`), weight, allowed N/A, N/A rule and numeric levels. **Do not hardcode the 8 criterion IDs as model instructions** — a criterion will be replaced in judging.

### Output (one per configured criterion)

```json
{
  "criterion_id": "C04",
  "answer": "scale",
  "value": 10,
  "explanation": "Часть запроса решена, но существенный вопрос остался без ответа.",
  "evidence": [{ "message_id": "m0007", "quote": "Клиентская реплика, дословно присутствующая в источнике" }]
}
```

The example is **only a schema illustration, not a real assessment**. Valid answers: `yes`, `no`, `na`, `scale`. For `scale`, the value must **exactly** equal a configured level. N/A only if criterion allows it; explain **why** and cite the relevant portion. Critical flag: **yes** means a gross violation was found. Every evidence quote must be a substring of the referenced real message. Server rejects fabricated evidence/unknown IDs.

### Important pitfalls

- Don't treat the bot greeting as operator greeting (C01). The first operator turn matters.
- For identity verification (C03), infer from the sequence of protected actions and confirmation, not just the existence of a word like “код”. No verification needed in a general question => N/A.
- For missing actions, reference the turn(s) where the action was expected. Do not fabricate a non-existent sentence.
- C04 problem resolution and C06 conversation clarity are different; evaluate independently.
- Call transcripts can include transcription mistakes and side conversations between colleagues. Do not attribute all utterances to the client-facing agent with high confidence by default.
- Flag C08 serious violations without altering the numeric score. If uncertain, prefer explainable conservatism and reviewer escalation.
- Measure quality on at least RU/KZ/EN; test short, long, good, bad, interrupted and account-security cases. Use only synthetic dialogue excerpts in Git.
- For paid APIs: estimate **per-conversation** cost across all calls, token usage and retry budget. Never expose the key to the Vite/browser environment.

### Integration tests

There must be an automated test verifying evaluator output can be passed through `calculate(checklist, answers)` and that all message IDs/quotes are real. Add end-to-end tests for a **changed checklist criterion**.
