"""Offline-only v2 approval checks. All conversations are freshly invented test data."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.admission import ApprovedDatasetAdmission
from app.config import Settings
from app.errors import ServiceError


def make_context(tmp_path):
    dataset = tmp_path / 'fictional.json'
    turns = [
        {'timestamp': '00:01', 'speaker': 'client', 'text': 'Test question, no account data.'},
        {'timestamp': '00:02', 'speaker': 'operator', 'text': 'Hello, this is a fictional answer.'},
    ]
    records = [{'conversation_id': 'fake-001', 'channel': 'agent chat', 'language': 'EN',
                'transcript': turns, 'audio_url': None},
               {'conversation_id': 'fake-002', 'channel': 'agent chat', 'language': 'EN',
                'transcript': turns, 'audio_url': None}]
    raw = json.dumps({'error': '', 'isSuccess': True,
                      'data': {'dataset_group_id': 'DEV', 'total_records': 2,
                               'records': records}}).encode()
    dataset.write_bytes(raw)
    approval = tmp_path / 'reviewed.ml-approval.json'
    info = {
        'approval_version': 2,
        'session_id': 'session-dev15-test',
        'approval_reference': 'fictional local test only — no external transfer permission',
        'approved_by': ['Farhat', 'Nurtas'],
        'processing_mode': 'external_approved',
        'destination_description': 'fictional test approval, no actual provider call',
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace('+00:00', 'Z'),
        'ml_url': 'http://127.0.0.1:8001/v1/evaluate',
        'dataset_path': str(dataset),
        'dataset_sha256': hashlib.sha256(raw).hexdigest(),
        'conversation_ids': ['DEV:fake-001'],
        'provider': 'groq',
        'model': 'openai/gpt-oss-20b',
        'checklist_scope': {'key': 'chat-quality', 'min_version': 1, 'max_version': 2,
                            'max_criteria': 8, 'require_confirmation': True},
    }

    def write():
        approval.write_text(json.dumps(info))
        approval.chmod(0o600)

    write()
    request = {
        'conversation': {
            'id': 'DEV:fake-001', 'dataset_group_id': 'DEV',
            'conversation_id': 'fake-001', 'channel': 'agent chat', 'language': 'EN',
            'messages': [{'id': 'm0001', **turns[0]}, {'id': 'm0002', **turns[1]}],
        },
        'checklist': {'key': 'chat-quality', 'version': 1,
                      'criteria': [{'id': 'C01'}]}
    }
    enabled = Settings(api_key='fictional-key-not-usable', free_plan_confirmed=True,
                       data_policy='approved_dataset', approval_file=str(approval),
                       external_transfer_authorized=True)
    return info, write, request, enabled, approval, dataset


def rejects(f, code='PRIVACY_POLICY_UNCONFIGURED'):
    with pytest.raises(ServiceError) as err:
        f()
    assert err.value.code == code


def test_disabled_by_default_even_with_a_well_formed_private_grant(tmp_path):
    _, _, request, enabled, _, _ = make_context(tmp_path)
    assert not Settings().external_transfer_authorized
    disabled = Settings(api_key='fictional-key-not-usable', free_plan_confirmed=True,
                        data_policy='approved_dataset', approval_file=enabled.approval_file)
    rejects(lambda: ApprovedDatasetAdmission(disabled).authorize(request, confirmed='true'))


def test_scope_selected_source_and_dynamic_v1_v2(tmp_path):
    _, _, request, settings, _, _ = make_context(tmp_path)
    admission = ApprovedDatasetAdmission(settings)
    grant = admission.authorize(request, confirmed='true')
    assert grant.model == 'openai/gpt-oss-20b'
    assert admission.health_fields()['admission_sha256'] == grant.sha256
    request['checklist']['version'] = 2
    assert admission.authorize(request, confirmed='true', expected_sha256=grant.sha256).sha256 == grant.sha256
    request['checklist']['version'] = 3
    rejects(lambda: admission.authorize(request, confirmed='true'))
    request['checklist']['version'] = 1
    rejects(lambda: admission.authorize(request, confirmed=None))
    rejects(lambda: admission.authorize(request, confirmed='True'))
    request['conversation']['messages'][0]['text'] += ' edited'
    rejects(lambda: admission.authorize(request, confirmed='true'))


def test_unselected_chat_rejected_and_no_group_shortcut(tmp_path):
    _, _, request, settings, _, _ = make_context(tmp_path)
    request['conversation']['id'] = 'DEV:fake-002'
    request['conversation']['conversation_id'] = 'fake-002'
    rejects(lambda: ApprovedDatasetAdmission(settings).authorize(request, confirmed='true'))


@pytest.mark.parametrize('change', [
    ('provider', 'other-provider'),
    ('model', 'openai/gpt-oss-120b'),
    ('ml_url', 'http://127.0.0.1:8888/v1/evaluate'),
    ('approval_version', 1),
    ('approved_by', ['Farhat']),
    ('processing_mode', 'local_only'),
    ('expires_at', '2020-01-01T00:00:00Z'),
    ('conversation_ids', ['DEV:fake-001', 'DEV:unknown']),
    ('dataset_sha256', '0'*64),
])
def test_invalid_grant_fails_closed(tmp_path, change):
    info, write, request, settings, _, _ = make_context(tmp_path)
    info[change[0]] = change[1]
    write()
    rejects(lambda: ApprovedDatasetAdmission(settings).authorize(request, confirmed='true'))


def test_tampering_and_deletion_revoke_and_no_cached_fallback(tmp_path):
    info, write, request, settings, path, data_path = make_context(tmp_path)
    admission = ApprovedDatasetAdmission(settings)
    first = admission.authorize(request, confirmed='true')
    info['session_id'] = 'another-reviewed-session'
    write()
    rejects(lambda: admission.authorize(request, confirmed='true', expected_sha256=first.sha256))
    path.unlink()
    rejects(lambda: admission.authorize(request, confirmed='true'))
    write()
    data_path.write_text('tampered')
    rejects(lambda: admission.authorize(request, confirmed='true'))


def test_rejects_extra_grant_fields_symlinks_and_wrong_permissions(tmp_path):
    info, write, request, settings, path, _ = make_context(tmp_path)
    info['ignore_policy'] = True
    write()
    rejects(lambda: ApprovedDatasetAdmission(settings).authorize(request, confirmed='true'))
    del info['ignore_policy']
    write()
    path.chmod(0o644)
    rejects(lambda: ApprovedDatasetAdmission(settings).authorize(request, confirmed='true'))
    path.chmod(0o600)
    symlink = path.with_name('link.json')
    symlink.symlink_to(path)
    linked = Settings(api_key=settings.api_key, free_plan_confirmed=True,
                      data_policy='approved_dataset', approval_file=str(symlink),
                      external_transfer_authorized=True)
    rejects(lambda: ApprovedDatasetAdmission(linked).authorize(request, confirmed='true'))
