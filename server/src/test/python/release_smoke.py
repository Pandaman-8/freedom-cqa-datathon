"""T16/T18: real packaged Java + real Python HTTP/validator + offline fixture provider.

65 distinct sources are accounted for (6 permitted + 59 policy rejections), followed by
65 successful evaluation operations over the unchanged six permitted fixtures. These are
different claims: policy intentionally prevents 65 distinct sources from reaching ML.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = [json.loads(p.read_text()) for p in sorted((ROOT / 'ml-service/tests/fixtures').glob('*/request.json'))]


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ml-python', default=str(ROOT / 'ml-service/.venv/bin/python'))
    args = parser.parse_args()
    assert len(FIXTURES) == 6
    with tempfile.TemporaryDirectory(prefix='cqa-release-') as temporary:
        folder = Path(temporary)
        db, counter = folder / 'release.sqlite', folder / 'provider-calls.jsonl'
        java_port, ml_port = port(), port()
        java_base, ml_base = f'http://127.0.0.1:{java_port}', f'http://127.0.0.1:{ml_port}'
        java = ml = None
        log = (folder / 'processes.log').open('wb')
        env = {**os.environ, 'GROQ_API_KEY': '', 'GROQ_FREE_PLAN_CONFIRMED': 'false', 'ML_DATA_POLICY': 'synthetic_only',
               'CQA_ORGANIZER_URL': '', 'CQA_ML_URL': '', 'PYTHONDONTWRITEBYTECODE': '1'}

        def http(base, method, route, body=None, expected=200):
            try:
                response = urlopen(Request(base + route, data=None if body is None else json.dumps(body).encode(),
                                          method=method, headers={'Content-Type': 'application/json'}), timeout=80)
            except HTTPError as error:
                response = error
            with response:
                assert response.status == expected, f'{method} {route}: HTTP {response.status}, expected {expected}'
                return json.loads(response.read())

        def api(method, route, body=None, expected=200):
            return http(java_base, method, route, body, expected)

        def wait(child, base, route, expected):
            for _ in range(300):
                assert child.poll() is None, 'Child exited; inspect isolated test log'
                try:
                    return http(base, 'GET', route, expected=expected)
                except (URLError, ConnectionError):
                    time.sleep(.1)
            raise AssertionError('Local startup timeout')

        def stop(child):
            if child:
                child.terminate()
                try:
                    child.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

        def start_ml(mode):
            command = ([args.ml_python, '-B', '-m', 'uvicorn', 'app.main:app', '--app-dir', str(ROOT / 'ml-service'),
                        '--host', '127.0.0.1', '--port', str(ml_port), '--workers', '1', '--no-access-log', '--log-level', 'warning']
                       if mode == 'unconfigured' else
                       [args.ml_python, '-B', str(ROOT / 'server/src/test/python/offline_ml_service.py'),
                        '--mode', mode, '--port', str(ml_port), '--counter', str(counter)])
            child = subprocess.Popen(command,
                                     cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                wait(child, ml_base, '/health', 503 if mode == 'unconfigured' else 200)
            except BaseException:
                stop(child)
                raise
            return child

        def start_java():
            child = subprocess.Popen(['java', '-jar', str(ROOT / 'server/target/freedom-cqa-server-0.1.0.jar'),
                                      f'--server.port={java_port}', f'--cqa.db-path={db}',
                                      f'--cqa.ml-url={ml_base}/v1/evaluate', '--cqa.organizer-url=',
                                      '--spring.main.banner-mode=off', '--logging.level.root=WARN'],
                                     cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                wait(child, java_base, '/api/health', 200)
            except BaseException:
                stop(child)
                raise
            return child

        def calls():
            return len(counter.read_text().splitlines()) if counter.exists() else 0

        def auto(fixture):
            return {'request_id': str(uuid4()), 'conversation_id': fixture['conversation']['id'],
                    'checklist_key': fixture['checklist']['key'], 'checklist_version': fixture['checklist']['version']}

        def original_rows():
            with sqlite3.connect(db) as connection:
                return connection.execute('SELECT * FROM evaluations ORDER BY id').fetchall()

        try:
            ml = start_ml('unconfigured')
            java = start_java()
            # Generate new input in memory, never edit a shared fixture or register policy exceptions.
            sources = copy.deepcopy(FIXTURES)
            for index in range(59):
                fixture = copy.deepcopy(FIXTURES[index % len(FIXTURES)])
                c = fixture['conversation']
                c['conversation_id'] = f'release-extra-{index:03d}'
                c['id'] = c['dataset_group_id'] + ':' + c['conversation_id']
                c['messages'][0]['text'] += f' [own synthetic release case {index:03d}]'
                sources.append(fixture)
            records = []
            for fixture in sources:
                c = fixture['conversation']
                records.append({'conversation_id': c['conversation_id'], 'channel': c['channel'], 'language': c['language'],
                                'transcript': [{k: v for k, v in m.items() if k != 'id'} for m in c['messages']]})
            envelope = {'isSuccess': True, 'data': {'dataset_group_id': 'SYNTHETIC', 'total_records': 65, 'records': records}}
            api('POST', '/api/datasets/import', envelope)
            api('POST', '/api/datasets/import', envelope)
            assert len(api('GET', '/api/conversations')) == 65
            for fixture in sources:
                c = fixture['conversation']
                actual = api('GET', '/api/conversations/' + quote(c['id'], safe=''))
                assert actual['messages'] == c['messages'] and actual['language'] == c['language']
            versions = {}
            for fixture in FIXTURES:
                c = fixture['checklist']
                identity = (c['key'], c['version'])
                assert identity not in versions or versions[identity] == c
                versions[identity] = c
            for (key, version), checklist in sorted(versions.items()):
                route = '/api/checklists/' + key + ('' if version == 1 else '?expected_version=' + str(version - 1))
                stored = api('POST' if version == 1 else 'PUT', route, {k: v for k, v in checklist.items() if k not in ('key', 'version')})
                assert stored == checklist
            # Production startup has no credentials, no automatic probes and honest unavailable status.
            missing = auto(FIXTURES[0])
            assert api('POST', '/api/evaluations/auto', missing, 501)['detail']['code'] == 'EVALUATOR_UNCONFIGURED'
            assert api('GET', '/api/evaluation-requests/' + missing['request_id'])['status'] == 'failed'
            assert calls() == 0
            print('PASS: clean Java/Python startup, static UI, unconfigured Python health503/evaluate501, zero provider calls.', flush=True)
            with urlopen(java_base + '/') as page:
                assert b'js/app.js' in page.read()
            stop(ml)
            ml = start_ml('fixture')
            saved, blocked = [], 0
            start = time.monotonic()
            for index, fixture in enumerate(sources):
                payload = auto(fixture)
                if index < 6:
                    result = api('POST', '/api/evaluations/auto', payload)
                    assert result['origin'] == 'model' and result['contract_version'] == '2.0.0'
                    saved.append((payload, result))
                else:
                    assert api('POST', '/api/evaluations/auto', payload, 503)['detail']['code'] == 'PRIVACY_POLICY_UNCONFIGURED'
                    api('GET', '/api/evaluation-requests/' + payload['request_id'], expected=404)
                    # Python independently rejects the unapproved input, without the fake provider.
                    fixture['request_id'] = str(uuid4())
                    assert http(ml_base, 'POST', '/v1/evaluate', fixture, 503)['detail']['code'] == 'PRIVACY_POLICY_UNCONFIGURED'
                    blocked += 1
            assert calls() == 6 and blocked == 59 and len(saved) == 6
            print('PASS: 65 distinct synthetic sources accounted: 6 model results / 59 explicit policy blocks; no silent skips.', flush=True)
            for index in range(59):
                payload = auto(FIXTURES[index % 6])
                saved.append((payload, api('POST', '/api/evaluations/auto', payload)))
            assert calls() == 65 and len(saved) == 65
            elapsed = round(time.monotonic() - start, 3)
            assert len(api('GET', '/api/evaluations')) == 65
            # Review a model result, keep its original snapshot, and preserve the entire history.
            target = next(result for _, result in saved if result['original_score']['overall_score'] == 100)
            before = original_rows()
            appeal = api('POST', '/api/evaluations/' + target['id'] + '/appeals',
                         {'criterion_id': 'LOCAL_CLARITY', 'comment': 'Synthetic release workflow check'}, 201)
            current = api('GET', '/api/evaluations/' + target['id'])
            replacement = copy.deepcopy(next(a for a in target['original_answers'] if a['criterion_id'] == 'LOCAL_CLARITY'))
            replacement.update(value=0, explanation='Synthetic reviewer change to exercise Java final scoring; not model quality evidence.')
            revision = current['review_revision']
            route = '/api/appeals/' + appeal['id'] + '/resolve?expected_revision=' + str(revision)
            decision = {'decision': 'change', 'reason': 'Synthetic release regression', 'replacement': replacement}
            reviewed = api('POST', route, decision)
            # IDENTITY is N/A: applicable weight75; GREETING25 + CLARITY0 -> 100*25/75=33.33.
            assert reviewed['final_score']['overall_score'] == 33.33 and reviewed['original_score']['overall_score'] == 100
            assert api('POST', route, decision, 409)['detail']['code'] == 'REVIEW_CONFLICT'
            assert before == original_rows()
            # Both existing approved v1/v2 remain pinned; the new v3 is not approved.
            checklist = copy.deepcopy(FIXTURES[0]['checklist'])
            key = checklist.pop('key')
            checklist.pop('version')
            checklist['title'] += ' release v3'
            api('PUT', '/api/checklists/' + key + '?expected_version=2', checklist)
            new = auto(FIXTURES[0])
            new['checklist_version'] = 3
            assert api('POST', '/api/evaluations/auto', new, 503)['detail']['code'] == 'PRIVACY_POLICY_UNCONFIGURED'
            snapshots = {result['id']: api('GET', '/api/evaluations/' + result['id']) for _, result in saved}
            stop(java)
            java = start_java()
            stop(ml)
            ml = start_ml('fixture')
            for payload, result in saved:
                status = api('GET', '/api/evaluation-requests/' + payload['request_id'])
                assert status['status'] == 'succeeded' and status['evaluation_id'] == result['id']
                assert api('GET', '/api/evaluations/' + result['id']) == snapshots[result['id']]
                assert api('POST', '/api/evaluations/auto', payload) == snapshots[result['id']]
            assert calls() == 65 and before == original_rows()
            print(f'PASS: 65 sequential evaluations over 6 approved fixtures in {elapsed}s, 65 provider stub calls; restart/replay add zero calls.', flush=True)
            print('PASS: original100/final33.33 (N/A denominator75), CAS409, immutable original rows, pinned v1/v2, denied new v3, persistent history.', flush=True)
            print('NOT RUN/BLOCKED: 65 distinct inputs reaching ML, live Groq, model quality/cost/capacity, DEV/CONTROL, Organizer, audio.', flush=True)
            print('Diagnostics provider/model are production app labels with an injected stub; they do not prove real inference.', flush=True)
        finally:
            stop(java)
            stop(ml)
            log.close()


if __name__ == '__main__':
    main()
