# T08 provider review — 2026-11-07

Candidate: **Groq / openai/gpt-oss-20b**. Alternative configurable candidate:
`openai/gpt-oss-120b`. During initial implementation no key was available. A later
single KZ live probe on 2026-11-07 passed with 20B (details below); full multilingual
smoke remains pending. This is a provisional selection, not completed T08 acceptance.
Paid budget authorized for this work: **$0**.

Primary sources checked on 2026-11-07:

- [Models](https://console.groq.com/docs/models): GPT OSS 20B has a 131,072-token
  context and 65,536 maximum completion tokens. Published Developer text rates are
  $0.075 input / $0.30 output per million tokens; 120B is $0.15 / $0.60.
  These are reference prices, **not the Free Plan charge**. The service enables
  no paid mode, audio, tools, batch or alternate endpoint.
- [Rate limits](https://console.groq.com/docs/rate-limits): the Free Plan table
  lists both candidates at 30 RPM, 1,000 RPD, 8,000 TPM and 200,000 TPD.
  Organization-specific limits in the console take precedence. Large requests
  may exhaust that quota despite fitting the model context; 100 configured
  criteria is contract capacity, not a claim of free-tier throughput.
- [Structured outputs](https://console.groq.com/docs/structured-outputs): both
  candidates support strict structured outputs. The adapter now uses `json_schema`,
  `strict: true`, with an internal decoding schema using documented types/refs/enums
  and `anyOf` for answer/value pairing. It preserves all wire fields. Provider subset
  constraints do not replace the unchanged full published JSON Schema, Pydantic or
  contextual/evidence validation. The former JSON object mode guaranteed no schema
  adherence and made malformed-but-valid-JSON output possible.
- [GPT-OSS reasoning](https://console.groq.com/docs/reasoning): use
  `include_reasoning=false` and `reasoning_effort=low`; GPT-OSS does not support
  `reasoning_format`. Truncation/refusal/missing content now have separate safe local
  diagnostic codes. Lower effort is a bounded-output choice, not a quality guarantee.
- [Billing](https://console.groq.com/docs/billing-faqs): Developer upgrades require
  a payment method and enable usage billing. A key alone does not prove Free Plan.
- [Data policy](https://console.groq.com/docs/your-data): inference inputs/outputs
  are not retained by default, but reliability/abuse logs can retain them up to
  30 days (longer if legally required). All customers can enable ZDR in Data
  Controls. This does not constitute organizer permission to export transcripts.

`GROQ_FREE_PLAN_CONFIRMED=true` is an explicit operator assertion about the actual
organization, not a remote billing verification or hard spending cap. Set it only
after checking the console. Do not use it on a paid organization. Requests are
blocked while false. There is no automatic paid fallback or upgrade.

The service only accepts exact fingerprints of bundled own synthetic conversations
and shared synthetic positive requests. A `SYNTHETIC` label alone is insufficient.
No environment switch authorizes real customer transcripts. Checklist wording is
also sent externally; keep custom rubrics free of private data. Real-data support
requires a separate approved policy change and organizer authorization.

Diagnostics come from the HTTP response's usage metadata and monotonic timer,
never generated answer text. Tokens from invalid and repaired completions are
summed. If any attempt lacks usage (including network errors), the affected token
sum and estimated cost are null. Complete known usage on a confirmed Free Plan
has estimated cost 0 USD, regardless of token category; no cached/audio tokens are
silently billed at ordinary text rates. No nonzero pricing calculation is enabled.

Outstanding evidence: live RU/KZ/EN labels, context capacity and latency, account
Free Plan/ZDR verification, human review of proposed synthetic labels, and joint
contract/HTTP integration acceptance. No quality score or live success is invented.

Follow-up actual live evidence: `kz_public_na`, `openai/gpt-oss-20b`, HTTP 200,
one upstream attempt, four answers passing the unchanged full validators,
2485 input / 567 output tokens, estimated cost 0 USD with local Free Plan confirmation.
The temporary localhost probe was stopped afterward. There were no additional live
attempts. Account billing is still an operator assertion, not independently verified
via an API. The exact cause of the preceding user-reported 502 remains unavailable
because old code discarded validation provenance; do not claim it was necessarily
a quote error, truncation, or schema error.
