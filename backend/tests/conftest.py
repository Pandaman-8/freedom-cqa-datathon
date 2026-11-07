import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CQA_DB_PATH", str(tmp_path / "test.sqlite"))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_dataset():
    return {
        "error": "", "isSuccess": True,
        "data": {
            "dataset_group_id": "DEV", "total_records": 2,
            "records": [
                {"conversation_id": "synthetic-kz-001", "channel": "agent chat", "language": "KZ",
                 "transcript": [
                     {"timestamp": "00:02", "speaker": "bot", "text": "Сәлеметсіз бе!"},
                     {"timestamp": "00:02", "speaker": "system", "text": "Оператор қосылды."},
                     {"timestamp": "01:15", "speaker": "operator", "text": "Сәлеметсіз бе, мен Айдана."},
                     {"timestamp": "01:30", "speaker": "client", "text": "Рақмет!"},
                 ], "audio_url": None},
                {"conversation_id": "synthetic-ru-call", "channel": "voice call", "language": "RU",
                 "transcript": [
                     {"timestamp": "2026-11-03T13:00:00+00:00", "speaker": "client", "text": "Здравствуйте."},
                     {"timestamp": "2026-11-03T13:00:01+00:00", "speaker": "operator", "text": "Чем могу помочь?"},
                 ], "audio_url": "https://example.invalid/synthetic.wav"}
            ]
        }
    }


@pytest.fixture
def ready_client(client, sample_dataset):
    response = client.post("/api/datasets/import", json=sample_dataset)
    assert response.status_code == 200
    return client


def answers_for(checklist, message_id="m0003", quote="Сәлеметсіз бе, мен Айдана."):
    result = []
    for c in checklist["criteria"]:
        a = "scale" if c["kind"] == "scale" else "no" if c["kind"] == "flag" else "yes"
        result.append({"criterion_id": c["id"], "answer": a,
                       "value": max(l["value"] for l in c["levels"]) if a == "scale" else None,
                       "explanation": "Синтетический тестовый фрагмент.",
                       "evidence": [{"message_id": message_id, "quote": quote}]})
    return result
