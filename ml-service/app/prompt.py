import json

from .validation import ROOT, SCHEMAS

PROMPT_VERSION = "cqa-dynamic/2"
SYSTEM = (ROOT / "prompts/evaluate-v1.txt").read_text(encoding="utf-8")


def build_messages(request, feedback=None):
    # Identity and diagnostics are deliberately absent from the model task.
    allowed = []
    for criterion in request["checklist"]["criteria"]:
        choices = ([{"answer": "scale", "value": level["value"]} for level in criterion["levels"]]
                   if criterion["kind"] == "scale" else
                   [{"answer": "yes", "value": None}, {"answer": "no", "value": None}])
        if criterion["allow_na"]:
            choices.append({"answer": "na", "value": None})
        allowed.append({"criterion_id": criterion["id"], "allowed_answer_value_pairs": choices})
    context = {"checklist": request["checklist"],
               "conversation": request["conversation"],
               "required_answers": allowed,
               "allowed_message_ids": [m["id"] for m in request["conversation"]["messages"]],
               "output_schema": SCHEMAS["provider_output"]}
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
    if feedback:
        # Never echo an untrusted previous response or a validator exception dump.
        messages.append({"role": "user", "content": json.dumps({
            "repair": "Re-evaluate the original context and return a complete valid JSON object.",
            "validation_failure": feedback})})
    return messages
