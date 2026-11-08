#!/usr/bin/env python3
"""Conservative public-release scan: tracked working files and all reachable Git blobs.

Never prints matching values. This is a detector, not proof of absence of personal data.
Use --repo /path/to/fresh-public-mirror.git to inspect public branches/tags/history.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

TOKENS = [re.compile(p.encode()) for p in (
    r'gh[pousr]_[A-Za-z0-9]{25,}', r'github_pat_[A-Za-z0-9_]{30,}',
    r'gsk_[A-Za-z0-9]{20,}', r'AKIA[0-9A-Z]{16}',
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
)]
URL = re.compile(rb'https?://[^\s<>"\x27`\\]+')
SIGNATURE = re.compile(r'(?:[?&])(?:sig|signature|x-amz-signature|token|api_key|key)=([^&\s]+)', re.I)


def private_path(name):
    p = Path(name)
    return (p.name == '.env' or (p.name.startswith('.env.') and p.name != '.env.example')
            or p.suffix.lower() in {'.pdf', '.sqlite', '.sqlite3', '.db', '.wav', '.mp3', '.m4a', '.pem', '.key'}
            or re.search(r'\.(?:sqlite3?|db)-(?:wal|shm|journal)$', name)
            or p.name.endswith(('.ml-approval.json', '.approval-selection.json', '.dataset-source.json'))
            or p.name.lower() == 'invoke.json' or p.parts[0] in {'uploads', 'recordings'}
            or (p.parts[0] == 'data' and p.name != '.gitkeep'))


def findings(raw):
    found = []
    if raw.startswith((b'%PDF-', b'SQLite format 3\0')):
        found.append('private-binary-format')
    if any(p.search(raw) for p in TOKENS):
        found.append('credential-pattern')
    for match in URL.finditer(raw):
        try:
            url = match.group().decode('utf-8')
            parsed = urlsplit(url)
            hostname = parsed.hostname or ''
            reserved = hostname.endswith('.invalid') or hostname in {'127.0.0.1', 'localhost', '::1'}
            if (parsed.username or parsed.password) and not reserved:
                found.append('url-userinfo')
            if SIGNATURE.search(url) and not reserved:
                found.append('signed-or-keyed-url')
        except ValueError:
            pass
    return sorted(set(found))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo = args.repo.resolve()

    def git(*arguments, **kwargs):
        return subprocess.check_output(['git', '-C', str(repo), *arguments], **kwargs)

    issues, blobs, checked = [], 0, 0
    # Include historical names even when rev-list picks a different name for a reused blob.
    historical_names = {name.strip('\n') for name in git('log', '--all', '--format=', '--name-only', '-z').decode().split('\0')}
    for name in sorted(historical_names - {''}):
        if private_path(name):
            issues.append({'location': name, 'kind': 'private-path-in-history'})
    objects = git('rev-list', '--objects', '--all', 'HEAD').decode().splitlines()
    paths = {}
    for line in objects:
        oid, _, name = line.partition(' ')
        paths[oid] = name
    process = subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for oid, name in paths.items():
            process.stdin.write((oid + '\n').encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            assert len(header) == 3, 'Unexpected Git object header'
            raw = process.stdout.read(int(header[2]))
            assert process.stdout.read(1) == b'\n'
            if header[1] in ('blob', 'commit', 'tag'):
                checked += 1
                blobs += header[1] == 'blob'
                if header[1] == 'blob' and name and private_path(name):
                    issues.append({'location': name, 'kind': 'private-path-in-history'})
                for kind in findings(raw):
                    issues.append({'location': name or oid[:12], 'kind': kind})
    finally:
        process.stdin.close()
        process.wait(timeout=10)
    bare = git('rev-parse', '--is-bare-repository').strip() == b'true'
    tracked = 0
    if not bare:
        for name in git('ls-files', '-z').decode().split('\0'):
            if not name:
                continue
            path = repo / name
            if path.is_file():
                tracked += 1
                if private_path(name):
                    issues.append({'location': name, 'kind': 'private-tracked-path'})
                for kind in findings(path.read_bytes()):
                    issues.append({'location': name, 'kind': kind})
        probes = ['.env', 'ml-service/.env', 'data/official/student_guide_v3.pdf', 'data/official/chat_quality_checklist.pdf',
                  'data/DEV.json', 'invoke.json', 'release.sqlite', 'server/release.sqlite-wal', 'recordings/test.wav']
        ignored = git('check-ignore', '--stdin', input=('\n'.join(probes) + '\n').encode()).decode().splitlines()
        for name in set(probes) - set(ignored):
            issues.append({'location': name, 'kind': 'private-path-not-ignored'})
    report = {'status': 'FAIL' if issues else 'PASS', 'reachable_commits': int(git('rev-list', '--count', '--all')),
              'reachable_objects': len(paths), 'scanned_blobs': blobs, 'scanned_objects_including_messages': checked,
              'tracked_working_files': tracked, 'findings': issues,
              'limits': 'Pattern/path scan, not exhaustive PII detection. Excludes unreachable/deleted remote objects, PR-only refs, releases, artifacts, issues, logs and external caches. Synthetic contents need human provenance review.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(issues))


if __name__ == '__main__':
    main()
