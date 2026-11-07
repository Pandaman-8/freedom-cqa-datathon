# Java ↔ Python ML contract artifacts — T02

Contract **2.0.0**, `POST http://127.0.0.1:8001/v1/evaluate`, JSON/UTF-8.
HTTP route generation `/v1` and envelope version `2.0.0` are intentional.
These are review artifacts, not implemented services or joint approval.

## Schemas and preservation

| File | Payload |
|---|---|
| [evaluation_request.schema.json](evaluation_request.schema.json) | Java → ML: version, request ID, conversation and full versioned checklist |
| [evaluation_result.schema.json](evaluation_result.schema.json) | ML → Java: identity echoes, answers and SDK diagnostics |
| [provider_output.schema.json](provider_output.schema.json) | Model output: answers only |
| [error.schema.json](error.schema.json) | Safe `detail` error envelope |

Files are exact JSON-value extractions of `plan.json → contracts.json_schemas`. No fields,
configured values, constraints or scoring semantics changed. No `$id` or envelope fields
were added. `provider_output` and `error` intentionally have no `contract_version` field:
they belong to this versioned artifact set while preserving their existing payload shapes.

Use these files for both future implementations. The plan retains its identical embedded
snapshot; `validate.py` rejects divergence. Any later change requires joint agreement and
coherent updates. See [the full specification](../docs/INTEGRATION_CONTRACT.md).

## Shared fixtures

[fixtures/manifest.json](fixtures/manifest.json) lists every file, schema, associated request,
expected validation layers and optional HTTP status. Positive/negative files are raw
payloads, not wrappers. Java and Python can independently load the same bytes and manifest.

- **16 positive cases:** unchanged request/result/provider/error examples, nullable error ID,
  RU/KZ text, ISO call timestamps with repeats, added criterion/version, decomposed Unicode
  evidence and numeric equivalence.
- **23 schema negatives:** required/unknown fields, obsolete version, numeric coercion,
  non-scale values, blank text, warnings, costs, attempts and invalid error shape.
- **28 context negatives:** identity echoes, complete criterion set, configured scales/N/A,
  exact evidence, checklist composition, positional IDs, error code/status pairs and zero
  production attempts. These intentionally pass JSON Schema and fail the context layer.
- **5 parser negatives:** duplicate key, NaN, Infinity, exponent overflow and trailing text.
  They intentionally fail strict decoding. `1e999` is syntactically JSON, but rejected by
  the documented nonfinite-overflow policy in this tooling runtime. Do not run a blanket
  “every JSON file must parse” check on this directory.

`expected.parse/schema/context` are booleans, or null when an earlier failure prevents the
next check. A negative case passes only if rejected at its specified layer. One synthetic
`mode=production` negative exercises the attempt-count guard, not a real model call.
All text is fictional; `example.invalid` appears only to test rejection of an audio field.

JSON Schema considers mathematically integral `2.0` an integer. The positive numeric case
preserves that existing meaning; strings and booleans are rejected. `10` and `10.0` are
equivalent levels. Unicode whitespace and unnormalized exact quotes are exercised. These
cases do not measure model accuracy or semantic relevance.

## Reproducible validation

From the repository root:

```bash
python3 -m venv /tmp/freedom-cqa-t02-validation
/tmp/freedom-cqa-t02-validation/bin/python -m pip install -r contracts/requirements.txt
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
```

This uses `jsonschema==4.23.0` and the Draft 2020-12 metaschema validator, not a handwritten
JSON Schema subset. The runner checks extraction drift, manifest references, transport
metadata, documented examples and context rules exercised by the corpus. It performs no
HTTP/model calls, writes no output files and imports no application modules. Its context
checker is offline tooling, not a Python ML-service implementation or a substitute for
future Java DTO/Python schema tests.

T02 does not prove SDK metadata authenticity, semantic relevance, network deadlines/retries,
persistence, Java scoring, SQLite or browser behavior. Those retain their existing tasks.
Full cross-language runtime tests require later implementations. Numeric/parser behavior
beyond these cases must stay explicit; do not silently narrow the contract to this tooling's
host numeric type.

## Joint approval checklist

Nurtas and Farhat must accept the same revision, or propose concrete changes:

1. All four schemas, fixture expectations and the integration document. The prepared bundle
   is identified by `plan.json → contracts.artifacts.review_fingerprint`; no participant
   approval is inferred from preparation or passing tests.
2. `POST /v1/evaluate`, contract `2.0.0`, localhost ports, full pinned checklist, request and
   conversation/checklist identity echoes, and answers-only provider output.
3. Strict JSON/no coercion/extra fields, error code/status pairs, exact evidence, discrete
   scales/N/A/flag rules and the schema/context validation boundary.
4. Python owns at most two provider attempts in 65 seconds; Java deadline70s, browser75s,
   no automatic Java POST replay; unknown outcomes, diagnostics/costs and duplicate billing.
5. Farhat owns Java/SQLite/scoring/shared-contract edits; Nurtas owns isolated Python ML.
   Review BC01–BC07, including public Java API changes. Python never returns authoritative scores.
6. Remaining T02 launch decisions: exact Spring Boot release, configuration names/start order
   and Nurtas's Python transport choice. These are not silently selected or implemented here.

Record each actual acknowledgment with date and artifact revision in T02 evidence.
**T02 remains `ready` until both approvals exist.** Passing the suite alone does not satisfy
joint agreement. This task creates no Java backend or Python ML service and makes no commits.
