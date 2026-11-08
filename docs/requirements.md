# Organizer requirements — source status and implementation scope

## Source status at release preparation

The private guide is present at `data/official/student_guide_v3.pdf`; the checklist PDF is **missing** at `data/official/chat_quality_checklist.pdf`. Guide contents were recorded by the earlier audit; this release check confirms availability without publishing its signed API URI. Checklist details below are the existing provisional seed/reference, **not a new verification of the missing PDF**. Do not claim full official conformance.

Current target: Java21/Spring Boot/SQLite, HTML/CSS/Vanilla JS, separate Python HTTP ML. See [architecture](architecture.md), [API](api-contract.md) and [confirmed release evidence/blockers](RELEASE_READINESS.md). The 65-source release dataset is generated own synthetic data; it is not the historical organizer DEV dataset described below.

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

## Chat Quality Checklist — seed and user-supplied official excerpt (PDF unavailable)

The exact seed is kept in `backend/app/seed/chat_quality.json`; it defines all 8 IDs, sections, descriptions, scales and N/A conditions. These behaviors are particularly easy to misread:

- **C01:** first **operator** reply must greet **in customer's language** and introduce themselves.
- **C02 N/A:** context already sufficient for an answer; no clarification necessary.
- **C03 N/A:** request never needed identity verification. Protected account-specific action before a verified identity = **No**.
- **C04:** score exactly 0/5/10/15/20; N/A only if conversation ended before the customer formulated a request.
- **C05:** politeness, and direct acknowledgement of a customer's stated trouble or dissatisfaction.
- **C06:** score exactly 0/4/7/10; clarity, sequence and explicit warnings of waiting (but **not** a first-response timer threshold).
- **C07 N/A:** chat interrupted before operator could properly close.
- **C08:** separate `yes/no` serious violation: insult, private paid consultation bypassing company, or confidential disclosure. Merely proposing the bypass is enough. The retained seed uses **no numeric penalty**; the missing PDF has not been rechecked.
- 3-minute first response threshold, tags and attachments are explicitly excluded.
- Only N/A answers are removed from the denominator; max score remains 100; round to two decimal places; if no applicable weighted criteria, no overall score.

## Historical aggregate observation of submitted `invoke.json` (not reread for release)

- `isSuccess:true`, `data.dataset_group_id:"DEV"`, `data.total_records:65`, `data.records[]`.
- Each record: `conversation_id`, `channel` (`agent chat`/`voice call`), `language` (`RU`/`KZ`/`EN`), `transcript[{timestamp,speaker,text}]`, `audio_url`.
- 35 RU, 15 KZ, 15 EN. Calls are RU only. Source transcript has repeated timestamps; rely on per-turn ID, never timestamp for unique evidence references.
- Transcripts contain automated ASR mistakes, internal agent discussions and redactions — do not infer misconduct solely from transcription artifacts without checking context.

This document combines historical guide/dataset notes with the provisional seed; it is not a new organizer grading rubric or proof that both PDFs were verified. Exact judges' weighting between functionality/design/AI was **not supplied**.

Final acceptance: Farhat supplied the C01–C08 rules/weights/types/levels/N/A in the FINAL ACCEPTANCE & CONTROL READINESS task. The seed matches that supplied excerpt; original PDF verification remains unavailable. No scoring/rounding formula was changed. Semantic explanation/evidence quality still requires separately authorized live review.
