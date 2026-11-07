"""Groq decoding aid with the SAME wire fields; final contract validation is mandatory.

Groq documents a JSON Schema subset. Keep basic shapes/refs/enums, express the
answer/value conditional as anyOf, and leave lexical/composition/grounding checks
to the unchanged authoritative schemas plus runtime context validators.
"""

import copy

from .validation import SCHEMAS


def groq_response_format():
    supported = {"type", "enum", "$ref", "additionalProperties", "required"}

    def shape(schema):
        result = {key: copy.deepcopy(value) for key, value in schema.items() if key in supported}
        if "properties" in schema:
            result["properties"] = {key: shape(value) for key, value in schema["properties"].items()}
        if "items" in schema:
            result["items"] = shape(schema["items"])
        return result

    source = SCHEMAS["provider_output"]
    schema = shape(source)
    evidence = shape(source["$defs"]["evidence"])
    answer = shape(source["$defs"]["criterion_answer"])
    scale = copy.deepcopy(answer)
    scale["properties"]["answer"] = {"type": "string", "enum": ["scale"]}
    scale["properties"]["value"] = {"type": "number"}
    other = copy.deepcopy(answer)
    other["properties"]["answer"] = {"type": "string", "enum": ["yes", "no", "na"]}
    other["properties"]["value"] = {"type": "null"}
    schema["$defs"] = {"evidence": evidence, "criterion_answer": {"anyOf": [scale, other]}}
    return {"type": "json_schema", "json_schema": {
        "name": "cqa_provider_output", "strict": True, "schema": schema}}
