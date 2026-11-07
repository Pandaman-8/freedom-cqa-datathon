import hashlib
import json

import pytest

from app.config import Settings
from app.errors import ServiceError
from conftest import ScriptedProvider, reply
from scripts import quality_pass


def test_quality_pass_loads_only_the_six_reviewed_requests():
    cases = quality_pass.load_cases()
    assert tuple(name for name, _ in cases) == quality_pass.SCENARIOS
    assert len(cases) == 6
    assert len({request["request_id"] for _, request in cases}) == 6
    assert {r["conversation"]["language"] for _, r in cases} == {"RU", "KZ", "EN"}
    review = json.loads((quality_pass.ROOT / "reports/synthetic-quality-review.json").read_text())
    for name, request in cases:
        assert request["conversation"]["dataset_group_id"] == "SYNTHETIC"
        expected = quality_pass.ROOT / "tests/fixtures" / name / "expected.json"
        assert hashlib.sha256(expected.read_bytes()).hexdigest() == review["scenarios"][name]["expected_sha256"]


@pytest.mark.asyncio
async def test_quality_audit_blocks_a_third_provider_attempt(output_data):
    records = {"ru_public_na": {"attempts": []}}
    delegate = ScriptedProvider(reply(output_data), reply(output_data))
    audit = quality_pass.AttemptAudit(delegate, records)
    audit.current = "ru_public_na"
    await audit.complete([])
    await audit.complete([])
    with pytest.raises(ServiceError):
        await audit.complete([])
    assert len(delegate.messages) == 2
    assert len(records["ru_public_na"]["attempts"]) == 2
    assert "answers" not in json.dumps(records)


@pytest.mark.asyncio
async def test_quality_audit_rejects_unapproved_scenario():
    delegate = ScriptedProvider()
    audit = quality_pass.AttemptAudit(delegate, {})
    audit.current = "DEV"
    with pytest.raises(ServiceError, match="PRIVACY_POLICY_UNCONFIGURED"):
        await audit.complete([])
    assert not delegate.messages


def test_quality_pass_rejects_model_change_before_ledger_or_network(monkeypatch):
    monkeypatch.setattr(quality_pass, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(Settings, "from_env", lambda: Settings(api_key="test-key", free_plan_confirmed=True,
                                                              model="openai/gpt-oss-120b"))
    with pytest.raises(ValueError, match="approved model"):
        quality_pass.main()


def test_repeat_pass_keeps_baseline_and_cannot_overwrite_its_own_ledger(monkeypatch, tmp_path):
    from app import prompt
    # This ledger belongs to the historical v3 run, not the current prompt.
    monkeypatch.setattr(prompt, "PROMPT_VERSION", "cqa-dynamic/3")
    monkeypatch.setattr(quality_pass, "ROOT", tmp_path)
    baseline = quality_pass.reserve_ledger("baseline")
    baseline.write_text('{"status": "complete", "synthetic_test_only": true}')
    original = baseline.read_bytes()
    repeat = quality_pass.reserve_ledger("prompt-v3")
    assert repeat != baseline
    assert repeat.stat().st_mode & 0o777 == 0o600
    assert repeat.parent.stat().st_mode & 0o777 == 0o700
    for run_id in ("baseline", "prompt-v3"):
        with pytest.raises(FileExistsError):
            quality_pass.reserve_ledger(run_id)
    assert baseline.read_bytes() == original


def test_repeat_pass_rejects_unknown_name_without_creating_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(quality_pass, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Unknown quality run"):
        quality_pass.reserve_ledger("../unreviewed-run")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("version", ["cqa-dynamic/2", "cqa-dynamic/4"])
def test_repeat_pass_rejects_wrong_prompt_version(monkeypatch, tmp_path, version):
    from app import prompt
    monkeypatch.setattr(quality_pass, "ROOT", tmp_path)
    monkeypatch.setattr(prompt, "PROMPT_VERSION", version)
    with pytest.raises(ValueError, match="requires prompt"):
        quality_pass.reserve_ledger("prompt-v3")
    assert not list(tmp_path.iterdir())
