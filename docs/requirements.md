# Organizer requirements — transcription of supplied documents

## Student Guide v3 (4 pages)

- Configure a checklist: edit/add criterion wording, weight, answer type, N/A availability and numeric scale. Save it and apply via UI, no Python code changes.
- Import transcript from API keyed by `group_id`; show RU/KZ/EN. DEV has 65 conversations (60 synthetic chats, 5 real voice calls). For calls, transcript + audio link are provided.
- Evaluate **operator** with per-criterion answer, score, weight, reason and evidence quote. Bot/system messages serve as context.
- Link evidence to exact transcript turn or audio segment. For missing behavior, show the checked part. For N/A, explain its condition. Display total and section summaries.
- Appeal a criterion with a comment; reviewer confirms/changes score and gives reason; preserve original, decision, final score.
- At hour 23 organizers issue control transcripts under another `group_id`. At hour 24 code freezes; config and dataset may still be operated via UI. The jury may replace one criterion in the UI.
- No login required. Frontend in HTML/CSS/JavaScript, adaptable later to a Dynamics 365 HTML component. GitHub repository must be public with setup README.
- Demo is **up to 5 minutes**: dialogue (1 min), score/evidence/N/A (2 min), appeal (1 min), replace criterion (1 min).
- Paid AI API is allowed; disclose model and approximate cost per conversation covering all API calls. Audio is needed to assess diction/intonation; speech recognition is not required.

## Chat Quality Checklist (3 pages)

The exact seed is kept in `backend/app/seed/chat_quality.json`; it defines all 8 IDs, sections, descriptions, scales and N/A conditions. These behaviors are particularly easy to misread:

- **C01:** first **operator** reply must greet **in customer's language** and introduce themselves.
- **C02 N/A:** context already sufficient for an answer; no clarification necessary.
- **C03 N/A:** request never needed identity verification. Protected account-specific action before a verified identity = **No**.
- **C04:** score exactly 0/5/10/15/20; N/A only if conversation ended before the customer formulated a request.
- **C05:** politeness, and direct acknowledgement of a customer's stated trouble or dissatisfaction.
- **C06:** score exactly 0/4/7/10; clarity, sequence and explicit warnings of waiting (but **not** a first-response timer threshold).
- **C07 N/A:** chat interrupted before operator could properly close.
- **C08:** separate `yes/no` serious violation: insult, private paid consultation bypassing company, or confidential disclosure. Merely proposing the bypass is enough. The PDF says **no points**; it does **not** prescribe automatic zeroing of total.
- 3-minute first response threshold, tags and attachments are explicitly excluded.
- Only N/A answers are removed from the denominator; max score remains 100; round to two decimal places; if no applicable weighted criteria, no overall score.

## Dataset observed from submitted `invoke.json`

- `isSuccess:true`, `data.dataset_group_id:"DEV"`, `data.total_records:65`, `data.records[]`.
- Each record: `conversation_id`, `channel` (`agent chat`/`voice call`), `language` (`RU`/`KZ`/`EN`), `transcript[{timestamp,speaker,text}]`, `audio_url`.
- 35 RU, 15 KZ, 15 EN. Calls are RU only. Source transcript has repeated timestamps; rely on per-turn ID, never timestamp for unique evidence references.
- Transcripts contain automated ASR mistakes, internal agent discussions and redactions — do not infer misconduct solely from transcription artifacts without checking context.

This document is a summary of *the user's supplied PDFs and dataset*, not a new organizer grading rubric. Exact judges' weighting between functionality/design/AI was **not supplied**.
