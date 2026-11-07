import json

from .validation import ROOT, SCHEMAS

PROMPT_VERSION = "cqa-dynamic/4"
SYSTEM = (ROOT / "prompts/evaluate-v1.txt").read_text(encoding="utf-8")

# Only the current dialogue's language guide is sent; examples carry no criterion IDs,
# answer values, message IDs or quotes that could be mistaken for conversation evidence.
EXPLANATION_GUIDES = {
    "RU": (
        "Каждое explanation пишите по-русски. Не переводите цитаты и не меняйте поля JSON.\n"
        "Примеры стиля объяснения, только если это подтверждено диалогом и критерием:\n"
        "Оператор выполнил действие до проверки личности.\n"
        "Клиент задал только общий вопрос, поэтому проверка личности для него не требуется."
    ),
    "KZ": (
        "Әр explanation мәтінін қазақ тілінде жазыңыз. Дәйексөздерді аудармаңыз және JSON өрістерін өзгертпеңіз.\n"
        "Диалог пен критерий растаған жағдайда ғана қолданылатын түсіндірме үлгілері:\n"
        "Оператор әрекетті жеке басты тексеруден бұрын орындаған.\n"
        "Клиент тек жалпы сұрақ қойды, сондықтан жеке басты растау қажет емес."
    ),
    "EN": (
        "Write every explanation in English. Do not translate quotes or change JSON fields.\n"
        "Explanation style examples, only when supported by the dialogue and criterion:\n"
        "The operator acted before verifying the client's identity.\n"
        "The client asked only a general question, so identity verification was not required."
    ),
}


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
    guide = EXPLANATION_GUIDES[request["conversation"]["language"]]
    messages = [{"role": "system", "content": SYSTEM + "\n" + guide},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
    if feedback:
        # Never echo an untrusted previous response or a validator exception dump.
        messages.append({"role": "user", "content": json.dumps({
            "repair": "Re-evaluate the original context and return a complete valid JSON object.",
            "validation_failure": feedback})})
    return messages
