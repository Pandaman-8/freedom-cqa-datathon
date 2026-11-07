from copy import deepcopy
from .conftest import answers_for


def test_health_and_initial_checklist(client):
    assert client.get("/api/health").json()["evaluator"] == "unconfigured"
    default = client.get("/api/checklists/chat-quality")
    assert default.status_code == 200
    assert default.json()["version"] == 1
    assert len(client.get("/api/checklists").json()) == 1


def test_import_is_idempotent_and_evidence_ids_are_stable(client, sample_dataset):
    assert client.post("/api/datasets/import", json=sample_dataset).json()["imported_records"] == 2
    assert client.post("/api/datasets/import", json=sample_dataset).status_code == 200
    conversations = client.get("/api/conversations").json()
    assert len(conversations) == 2
    record = client.get("/api/conversations/DEV:synthetic-kz-001").json()
    assert [m["speaker"] for m in record["messages"]] == ["bot", "system", "operator", "client"]
    assert record["messages"][0]["timestamp"] == record["messages"][1]["timestamp"]
    assert [m["id"] for m in record["messages"]] == ["m0001", "m0002", "m0003", "m0004"]
    call = client.get("/api/conversations/DEV:synthetic-ru-call").json()
    assert call["audio_url"] == "https://example.invalid/synthetic.wav"
    changed = deepcopy(sample_dataset)
    changed["data"]["records"][0]["transcript"][0]["text"] = "This changes the source"
    assert client.post("/api/datasets/import", json=changed).status_code == 409
    assert client.get("/api/conversations/DEV:missing").status_code == 404


def test_import_validation(client, sample_dataset):
    wrong = deepcopy(sample_dataset)
    wrong["data"]["total_records"] = 999
    assert client.post("/api/datasets/import", json=wrong).status_code == 422
    wrong = deepcopy(sample_dataset)
    wrong["isSuccess"] = False
    assert client.post("/api/datasets/import", json=wrong).status_code == 422


def test_full_manual_appeal_and_revision_flow(ready_client):
    checklist = ready_client.get("/api/checklists/chat-quality").json()
    answers = answers_for(checklist)
    answers[3]["value"] = 10  # only partial consultation
    request = {"conversation_id": "DEV:synthetic-kz-001", "checklist_key": "chat-quality", "answers": answers}
    response = ready_client.post("/api/evaluations/manual", json=request)
    assert response.status_code == 201, response.text
    evaluation = response.json()
    eval_id = evaluation["id"]
    assert evaluation["original_score"]["overall_score"] == 90.0
    assert evaluation["final_score"]["overall_score"] == 90.0
    assert evaluation["review_status"] == "evaluated"

    # Invalid quotes are never accepted as evidence.
    forged = deepcopy(request)
    forged["answers"][0]["evidence"][0]["quote"] = "quote not in transcript"
    assert ready_client.post("/api/evaluations/manual", json=forged).status_code == 422

    appeal = ready_client.post(f"/api/evaluations/{eval_id}/appeals", json={
        "criterion_id": "C04", "comment": "Основной запрос закрыт, проверьте ещё раз"
    })
    assert appeal.status_code == 201, appeal.text
    appeal_id = appeal.json()["id"]
    assert ready_client.get(f"/api/evaluations/{eval_id}").json()["review_status"] == "appealed"
    assert ready_client.post(f"/api/evaluations/{eval_id}/appeals", json={
        "criterion_id": "C04", "comment": "Duplicate"}).status_code == 409

    replacement = deepcopy(answers[3]); replacement["value"] = 20
    result = ready_client.post(f"/api/appeals/{appeal_id}/resolve", json={
        "decision": "change", "reason": "Проверяющий подтвердил полный ответ", "replacement": replacement
    })
    assert result.status_code == 200, result.text
    assert result.json()["original_score"]["overall_score"] == 90.0
    assert result.json()["final_score"]["overall_score"] == 100.0
    assert result.json()["review_status"] == "reviewed"
    assert ready_client.post(f"/api/appeals/{appeal_id}/resolve", json={
        "decision": "confirm", "reason": "Repeated review"}).status_code == 409

    # Changing checklist NEVER changes historic assessments.
    draft = {key: checklist[key] for key in ("title", "description", "sections", "criteria")}
    draft["criteria"][4]["weight"] = 25
    draft["criteria"][4]["instruction"] += " Дополнительное контрольное условие."
    new_config = ready_client.put("/api/checklists/chat-quality", json=draft)
    assert new_config.status_code == 200, new_config.text
    assert new_config.json()["version"] == 2
    assert ready_client.get("/api/checklists/chat-quality?version=1").json()["criteria"][4]["weight"] == 15
    assert ready_client.get(f"/api/evaluations/{eval_id}").json()["checklist_version"] == 1
    newer = ready_client.post("/api/evaluations/manual", json=request)
    assert newer.status_code == 201
    assert newer.json()["checklist_version"] == 2
    assert newer.json()["original_score"]["overall_score"] == 90.91  # 100 earned / 110 *100
    assert ready_client.post("/api/evaluations/auto", json={
        "conversation_id": "DEV:synthetic-kz-001"}).status_code == 501
    assert len(ready_client.get("/api/evaluations?conversation_id=DEV:synthetic-kz-001").json()) == 2


def test_reviewer_can_confirm_without_changing_score(ready_client):
    checklist = ready_client.get("/api/checklists/chat-quality").json()
    evaluation = ready_client.post("/api/evaluations/manual", json={
        "conversation_id": "DEV:synthetic-kz-001", "answers": answers_for(checklist)
    }).json()
    a = ready_client.post(f"/api/evaluations/{evaluation['id']}/appeals", json={
        "criterion_id": "C01", "comment": "Прошу проверить приветствие"
    }).json()
    resolved = ready_client.post(f"/api/appeals/{a['id']}/resolve", json={
        "decision": "confirm", "reason": "Приветствие и представление есть"
    }).json()
    assert resolved["final_score"]["overall_score"] == resolved["original_score"]["overall_score"]


def test_control_group_does_not_overwrite_dev(client, sample_dataset):
    assert client.post("/api/datasets/import", json=sample_dataset).status_code == 200
    control = deepcopy(sample_dataset)
    control["data"]["dataset_group_id"] = "CONTROL"
    # Same source conversation ID in a new group must get a different stable composite ID.
    assert client.post("/api/datasets/import", json=control).status_code == 200
    ids = {c["id"] for c in client.get("/api/conversations").json()}
    assert "DEV:synthetic-kz-001" in ids and "CONTROL:synthetic-kz-001" in ids


def test_changed_checklist_with_added_criterion_is_supported(ready_client):
    base = ready_client.get("/api/checklists/chat-quality").json()
    draft = {k: deepcopy(base[k]) for k in ("title", "description", "sections", "criteria")}
    draft["criteria"].append({
        "id": "C09", "section_id": "start", "title": "Новый критерий жюри",
        "instruction": "Проверить дополнительное действие.",
        "kind": "binary", "weight": 10, "allow_na": True,
        "na_rule": "Если дополнительное действие не требовалось", "levels": []
    })
    result = ready_client.put("/api/checklists/chat-quality", json=draft)
    assert result.status_code == 200, result.text
    checklist = result.json()
    assert checklist["version"] == 2
    assert len(checklist["criteria"]) == 9
    answers = answers_for(checklist)
    answers[-1]["answer"] = "na"
    evaluation = ready_client.post("/api/evaluations/manual", json={
        "conversation_id": "DEV:synthetic-kz-001", "answers": answers
    })
    assert evaluation.status_code == 201, evaluation.text
    assert evaluation.json()["original_score"]["overall_score"] == 100
