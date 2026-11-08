"""CLI permission/config checks only; reuse existing invented test context, no provider."""
import importlib.util
import json
from pathlib import Path

import pytest
from test_approved_dataset_admission import make_context

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepare_approval', ROOT / 'scripts/prepare-approval.py')
cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)


def setup(tmp_path):
    info, _, _, _, _, source = make_context(tmp_path)
    archived = tmp_path / (info['dataset_sha256'] + '.dataset-source.json')
    source.rename(archived); archived.chmod(0o600)
    selection = tmp_path / 'selected.approval-selection.json'
    assert cli.main(['inspect', '--source', str(archived), '--output', str(selection)]) == 0
    contents = json.loads(selection.read_bytes())
    assert contents['selected_ids'] == []
    contents['selected_ids'] = info['conversation_ids']; selection.write_text(json.dumps(contents))
    output = tmp_path / 'session.ml-approval.json'
    args = ['create', '--source', str(archived), '--selection', str(selection), '--output', str(output),
            '--session-id', 'OFFLINE-TEST-NOT-CONSENT', '--approval-reference', 'TEST ONLY',
            '--expires-at', info['expires_at'], '--ml-url', info['ml_url'], '--checklist-key', 'chat-quality',
            '--min-version', '1', '--max-version', '10', '--max-criteria', '100', '--confirm-external-transfer']
    return args, archived, selection, output


def test_cli_shared_validation_private_files_and_no_overwrite(tmp_path):
    args, source, selection, output = setup(tmp_path)
    assert cli.main(args) == 0
    assert selection.stat().st_mode & 0o777 == output.stat().st_mode & 0o777 == 0o600
    saved = output.read_bytes(); grant = json.loads(saved)
    assert grant['dataset_path'] == str(source)
    assert grant['checklist_scope']['max_version'] == 10
    assert cli.main(args) == 2
    assert output.read_bytes() == saved


def test_cli_requires_explicit_transfer_attestation(tmp_path):
    args, _, _, output = setup(tmp_path)
    with pytest.raises(SystemExit): cli.main(args[:-1])
    assert not output.exists()


@pytest.mark.parametrize('fault', ['empty', 'wildcard', 'wrong_id', 'wrong_source', 'expired', 'public_selection', 'public_directory'])
def test_cli_rejects_invalid_selection_or_permission_without_publishing(tmp_path, fault):
    args, source, selection, output = setup(tmp_path)
    content = json.loads(selection.read_bytes())
    if fault in ('empty', 'wildcard', 'wrong_id'):
        content['selected_ids'] = {'empty': [], 'wildcard': ['DEV:*'], 'wrong_id': ['OTHER:fake-001']}[fault]
        selection.write_text(json.dumps(content))
    elif fault == 'wrong_source': source.write_bytes(source.read_bytes() + b' ')
    elif fault == 'expired': args[args.index('--expires-at')+1] = '2000-01-01T00:00:00Z'
    elif fault == 'public_selection': selection.chmod(0o644)
    elif fault == 'public_directory': tmp_path.chmod(0o755)
    assert cli.main(args) == 2
    assert not output.exists()
