#!/usr/bin/env python3
"""Prepare a private approval v2 from Java's exact-byte archive. Never calls a provider."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml-service'))
from app.admission import ApprovedDatasetAdmission, _private_read, _dataset_projections, DATASET_LIMIT
from app.config import Settings
from app.errors import ServiceError
from app.validation import strict_loads


def archive(path):
    raw = _private_read(str(path), DATASET_LIMIT, grant=True)
    digest = hashlib.sha256(raw).hexdigest()
    if path.name != digest + '.dataset-source.json':
        raise ValueError('Archive filename must match the source hash')
    data = strict_loads(raw)['data']
    group = data['dataset_group_id']
    candidates = [{'id': group + ':' + r['conversation_id'], 'language': r['language']}
                  for r in data['records'] if r['channel'] == 'agent chat' and r.get('audio_url') is None]
    _dataset_projections(raw, digest, {c['id'] for c in candidates})
    return digest, group, candidates, len(data['records'])


def publish(path, value, validate=lambda _: None):
    if not path.is_absolute() or path.parent.is_symlink():
        raise ValueError('Use an absolute private destination')
    meta = path.parent.stat()
    if meta.st_uid != os.getuid() or meta.st_mode & 0o077:
        raise ValueError('Destination directory must be private and owned by the operator')
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    if len(raw) > 256 * 1024:  # Java's smaller approval-file limit governs shared grants.
        raise ValueError('Private configuration exceeds shared size limit')
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.ml-approval.json')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        validate(Path(temporary))
        os.link(temporary, path)  # Atomic, never overwrite/revoke a running session accidentally.
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='Write private candidate IDs; selected_ids starts empty')
    create = commands.add_parser('create', help='Require explicit IDs, scope, expiry and transfer attestation')
    for command in (inspect, create):
        command.add_argument('--source', type=Path, required=True)
        command.add_argument('--output', type=Path, required=True)
    create.add_argument('--selection', type=Path, required=True)
    for name in ('session-id', 'approval-reference', 'expires-at', 'ml-url', 'checklist-key'):
        create.add_argument('--'+name, required=True)
    for name in ('min-version', 'max-version', 'max-criteria'):
        create.add_argument('--'+name, type=int, required=True)
    create.add_argument('--confirm-external-transfer', action='store_true', required=True,
                        help='Attest that actual transfer terms/budget and Farhat/Nurtas permission exist; technical approval is insufficient')
    args = parser.parse_args(argv)
    try:
        digest, group, candidates, total = archive(args.source)
        if args.command == 'inspect':
            if not args.output.name.endswith('.approval-selection.json'):
                raise ValueError('Use the gitignored .approval-selection.json suffix')
            publish(args.output, {'dataset_sha256': digest, 'dataset_group_id': group,
                                 'total_records': total, 'candidates': candidates, 'selected_ids': []})
            print(f'PRIVATE selection written: {len(candidates)} eligible chats; {total-len(candidates)} excluded. No permission granted.')
            return 0
        selection = strict_loads(_private_read(str(args.selection), 256 * 1024, grant=True))
        if selection['dataset_sha256'] != digest or selection['dataset_group_id'] != group:
            raise ValueError('Selection belongs to a different source')
        endpoint = urlsplit(args.ml_url)
        if (endpoint.port is None or not 1 <= endpoint.port <= 65535
                or args.ml_url != f'http://127.0.0.1:{endpoint.port}/v1/evaluate'):
            raise ValueError('Use the configured local ML endpoint')
        if not args.output.name.endswith('.ml-approval.json'):
            raise ValueError('Grant requires the gitignored .ml-approval.json suffix')
        grant = {'approval_version': 2, 'session_id': args.session_id,
                 'approval_reference': args.approval_reference, 'approved_by': ['Farhat', 'Nurtas'],
                 'processing_mode': 'external_approved',
                 'destination_description': 'Groq GPT-OSS 20B; chat transcript and confirmed checklist only',
                 'expires_at': args.expires_at, 'ml_url': args.ml_url,
                 'dataset_path': str(args.source), 'dataset_sha256': digest,
                 'conversation_ids': selection['selected_ids'], 'provider': 'groq', 'model': 'openai/gpt-oss-20b',
                 'checklist_scope': {'key': args.checklist_key, 'min_version': args.min_version,
                                     'max_version': args.max_version, 'max_criteria': args.max_criteria,
                                     'require_confirmation': True}}
        def validate(path):
            ApprovedDatasetAdmission(Settings(data_policy='approved_dataset', approval_file=str(path),
                admission_ml_url=args.ml_url, external_transfer_authorized=True)).load()
        publish(args.output, grant, validate)
        print(f'PRIVATE approval v2 written for {len(grant["conversation_ids"])} explicit chats. Services/opt-ins unchanged; provider calls=0.')
        return 0
    except (OSError, ValueError, TypeError, KeyError, ServiceError):
        print('REFUSED: invalid/private source, explicit selection, scope, expiry or destination; existing files unchanged.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
