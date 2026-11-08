# Dynamic admission v2 — Java implementation and Python handoff

Status: Farhat relayed joint technical agreement and acceptance of all four Nurtas comments
in the FINAL DYNAMIC AI INTEGRATION task (chat, not a GitHub Review). This does not grant
external DEV transfer consent. Applies to PR #14; evaluation contract 2.0.0/scoring stay unchanged.

## Scope

Keep `synthetic_only` as the default. In `approved_dataset`, both services independently
load the same private, expiring approval file and verify its exact bytes/hash and the
approved dataset hash. Match the full audio-free source projection and explicit chat IDs.
No group-name permission, no wildcard conversations, no voice calls in this phase.

Approval v2 retains `approval_reference`, both `approved_by` names,
`processing_mode`, `destination_description`, `expires_at`, `ml_url`, `dataset_path`,
`dataset_sha256`, `conversation_ids`, and adds:

- `approval_version: 2`, `session_id`: one explicit named session;
- `provider: "groq"`, `model: "openai/gpt-oss-20b"`: machine-checked destination;
- `checklist_scope`: `key`, `min_version`, `max_version`, `max_criteria`,
  `require_confirmation: true`.

The scope authorizes **valid** versions within one named key and bounded numeric range,
not any checklist. Both sides still validate all supplied criteria/kinds/levels/NA.
The original baseline and every subsequent rubric remain pinned in Java SQLite.
New instructions within the agreed scope need no approval-file or prompt/code edit.
Versions beyond scope require a new actual session approval. Changing/removing the file,
expiry, a wrong source, model or endpoint must fail closed; no fallback to synthetic mode.

This is an explicit private-configuration migration: old snapshot-only approvals must
not silently become permission for dynamic rubrics. Existing default fixtures stay unchanged.
Approval fields are an operator attestation, not cryptographic proof of organizer consent.
The current Groq-only provider cannot accept `local_only` as authorization for cloud inference.

## Readiness and confirmation

Extend Python's existing read-only `/health` with a versioned admission capability,
the active policy mode, and a SHA256 of the fully validated private approval file (never
its contents, paths or conversation IDs). Java reports selected-request readiness only
if its own checks pass and Python attests to the **same** valid grant/protocol/model.
Missing protocol, mismatched mode/grant, expiry/revocation and unavailable provider
configuration produce explicit safe reasons. No provider probe or inference on health.
Readiness is rechecked before dispatch; a race/revocation still results in a safe refusal.

For an admitted dynamic rubric, the UI shows the selected version and explicit outgoing
data notice. The user confirms that rubric for this action/session. An additive HTTP
header `X-CQA-Rubric-Confirmed: true` accompanies the existing pinned auto request;
Java forwards it only after its checks. Python independently requires it before Groq.
The header is **not** a replacement for the private approval and cannot authorize another
dataset/key/version. It changes no contract JSON. Reload/new version loses the UI checkbox.
Batch must preflight each selected item and use the same explicit pinned-rubric confirmation;
known refusals must not create an inference UUID or send an ML POST.

## Verification and live gate

First reproduce the existing DEV refusal without provider calls. Then verify independent
Java/Python admission, missing confirmation, dynamic v1/v2, wrong IDs/dataset/version/model,
expired/deleted/changed approvals, and no POST on a known readiness refusal. Offline test
providers are regression infrastructure only, never proof that the real model understood a rubric.

Only after actual transfer terms and budget are confirmed: one existing chat v1 then a
criterion replaced through UI/v2; inspect real diagnostics/usage and semantic relevance,
preserve v1, then 15 explicitly approved chats (5 RU/5 KZ/5 EN). Exclude all five real calls.
No raw source, private URLs, active grants, credentials or database may enter Git/evidence.

## Reproduction at 97b5d1a, 2026-11-08

No Java/Python service processes were running when inspected. Isolated services used a
temporary SQLite and the existing private `data/dev/invoke.json`, with provider key empty:
Java `synthetic_only`, ML URL configured to loopback; Python `synthetic_only`,
`GROQ_FREE_PLAN_CONFIRMED=false`, default model GPT-OSS20B.

- Existing DEV chat plus C01–C08: Java503 `PRIVACY_POLICY_UNCONFIGURED`, ledger404.
  Refusal occurs in `SyntheticPolicy.requireApproved`, before `MlClient.evaluate`.
- The existing DEV source fingerprint is absent from Python's synthetic allowlist.
- Isolated `Settings.check()` with a non-secret dummy test key/free flag and
  `approved_dataset` returns `PRIVACY_POLICY_UNCONFIGURED` without invoking a provider.
- Actual Python HTTP health503 `EVALUATOR_UNCONFIGURED` with the empty key.
- Inference `/v1/evaluate` POST count **0**; real Groq calls **0**; no model result saved.

The config-only test above is not an external inference or a DEV E2E. No client text,
IDs, credentials, audio locators or private endpoint URLs are recorded here.

## Historical independent UI fix at a32deba

The AI action rechecks the existing Java readiness endpoint **before** allocating a
request UUID. A stale green indicator followed by a known ML refusal sends no inference
POST and leaves no UUID to reconcile. This does not yet fix cross-service admission:
Java's existing readiness cannot attest to Python's selected-request policy.

Local verification: packaged fake-HTTP smoke PASS, 27 JS tests PASS, actual browser
5/5 AI scenarios PASS including revocation of readiness between display and click.
Existing timeout/unknown recovery, double-click protection and explicit retry still pass.
At that historical revision the shared policy implementation was still pending agreement.


## Current Java implementation

Java reads `CQA_ML_DATA_MODE=approved_dataset`, absolute `CQA_ML_APPROVAL_FILE`, and
`CQA_ML_EXTERNAL_INFERENCE_ENABLED=true`. The last flag defaults to **false** and is a
separate opt-in, not evidence of data consent. Default `synthetic_only` keeps its six
exact pairs. Legacy snapshot-only grants are rejected; migrate configuration once after
actual authorization, not once per criterion. `checklist_scope.max_criteria` is 1..100,
min_version>=1, max_version>=min_version, and require_confirmation must be true.

Both reviewer names, nonblank session/reference, exact source file SHA256, explicit
unique conversation IDs, scope, expiry, exact ML URL, `external_approved`, `groq` and
`openai/gpt-oss-20b` are checked. All selected IDs must exist and be agent chats.
Java rechecks source bytes on admission; changing/deleting grant or source fails closed.
A valid replacement grant can establish a newly authorized session. It cannot retroactively
cancel an already sent inference or convert a ledger replay into a new POST.

The Java adapter currently expects these **flat Python health fields**:

| Field | Required value in approved_dataset |
| --- | --- |
| `admission_protocol` | integer 2 |
| `policy_mode` | `approved_dataset` |
| `grant_sha256` | SHA256 of exactly the same fully validated private grant bytes |
| `provider` | `groq` |
| `model` | `openai/gpt-oss-20b` |

**Integration pending:** these exact spellings must be checked against Nurtas's patch;
no compatible Python implementation has been received in this checkout or published in
an accessible branch at this verification. They are the current Java adapter interface,
not a claim that Nurtas has implemented it. Old Python/missing metadata fails closed.
The existing `configured`, `ready`, `reason`, `contract_version` health checks also apply.
No health request sends transcripts or invokes a provider.

Java UI status adds `rubric_confirmation_required` and `confirmation_scope` (grant hash).
No UUID is allocated before current selected readiness and required confirmation pass.
A changed grant resets the checkbox. The checkbox is per loaded conversation/version;
new version/reload requires fresh confirmation. Only the exact true header is forwarded
by Java after admission, confirmation and matching Python health, before ledger claim.
Normal Python result validation, pinned snapshots, immutable originals and Java scoring remain.

Batch preflights each pinned item before UUID. Known refusals persist as `blocked_code`
with no inference attempt; old manifests still load. Only explicit retry can reconsider a
blocked item. Consent is never stored in localStorage and must match the current grant.
Unknown outcomes remain unknown even if an explicitly requested retry is denied by policy.

## Private DEV integration check

```bash
ml-service/.venv/bin/python -B server/src/test/python/admission_dev_smoke.py \
  --dataset data/dev/invoke.json --ml-python "$PWD/ml-service/.venv/bin/python" --serve
```

The test launcher requires Nurtas's admission patch. It uses a disposable grant/database,
an unusable provider key, the existing Python provider injection seam, and rejects all
external DNS/connect calls. No policy is mocked. Expected provider responses are structural
regression outputs labelled OFFLINE TEST ONLY, never Groq results or semantic quality proof.
The prepared browser suite checks explicit consent, v1→UI criterion replacement→v2,
review/evidence/history and batch15 accepted/50 blocked, including pause/reload/resume.
Until Python v2 is available, this suite is **BLOCKED / NOT RUN**, not PASS.
The test-only `ML_*` environment names likewise must be aligned with the supplied patch.

Observed locally: Java selected admission on the supplied65-record DEV accepts exactly
15 configured chats (5RU/5KZ/5EN); external opt-in absent blocks before ML. The installed
Python health does not expose protocol2, so the joint test stops there. Groq calls=0.


## Verification of this Java/UI change (2026-11-08)

- Java clean verify: 5989 JUnit PASS; after the final health-reason change, 25 focused
  admission/readiness cases and packaging PASS. Zero failures/errors/skips.
- JS: 30 PASS (batch19, presentation3, workspace8). Contracts: 72 fixtures, four schemas
  and plan drift PASS. Scoring reference: 5184 PASS.
- Actual browser: AI6/6 and batch9/9 on fake HTTP; explicit confirmation / changed grant
  was tested with simulated readiness metadata, not an actual Python v2 handshake.
- Existing DEV packaged local manual/review/CAS/version/restart PASS; private browser6/6
  PASS, including65 explicit batch refusals with no inference. No raw input/audio fetched
  externally. These technical manual answers are not model quality labels.
- Actual Java/Python HTTP default synthetic_only regression PASS with the existing offline
  provider seam:65 distinct synthetic inputs =6 accepted/59 blocked;65 sequential operations
  over6 approved inputs PASS, no additional provider calls on restart/replay. This does not
  establish approved_dataset compatibility or live-model quality.
- New joint DEV v1→v2/browser/batch harness remains BLOCKED before inference because the
  available Python lacks protocol2. No Nurtas source edits. Real Groq calls:0.
