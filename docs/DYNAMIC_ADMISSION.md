# Dynamic admission — proposed Java/Python agreement

Status: proposal for Farhat/Nurtas review, not recorded joint approval or DEV transfer consent.
Applies to PR #14 after `97b5d1a`; does not change evaluation contract 2.0.0 or scoring.

## Scope

Keep `synthetic_only` as the default. In `approved_dataset`, both services independently
load the same private, expiring approval file and verify its exact bytes/hash and the
approved dataset hash. Match the full audio-free source projection and explicit chat IDs.
No group-name permission, no wildcard conversations, no voice calls in this phase.

Proposed approval v2 retains `approval_reference`, both `approved_by` names,
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

## Independent UI fix while agreement is pending

The AI action rechecks the existing Java readiness endpoint **before** allocating a
request UUID. A stale green indicator followed by a known ML refusal sends no inference
POST and leaves no UUID to reconcile. This does not yet fix cross-service admission:
Java's existing readiness cannot attest to Python's selected-request policy.

Local verification: packaged fake-HTTP smoke PASS, 27 JS tests PASS, actual browser
5/5 AI scenarios PASS including revocation of readiness between display and click.
Existing timeout/unknown recovery, double-click protection and explicit retry still pass.
No new Java/Python policy implementation is claimed pending the required joint agreement.
