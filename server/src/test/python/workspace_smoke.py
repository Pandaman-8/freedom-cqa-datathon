"""T12 packaged HTTP smoke + optional browser harness. Synthetic data/temp SQLite only.

--serve exposes the unmodified JAR through a loopback proxy with test-only /__tests/ pages.
No browser tools, npm packages, real Organizer, provider or persistent user DB are used.
"""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
JAR = ROOT / 'server/target/freedom-cqa-server-0.1.0.jar'
GROUP = 'UI-SYNTHETIC'
QUOTE = 'Сәлем! Synthetic support.\n  Exact e\u0301 quote.'
DRAFT = {'title': 'Synthetic workspace rubric', 'description': 'UI test only',
         'sections': [{'id': 'quality', 'title': 'Качество'}, {'id': 'risk', 'title': 'Риски'}],
         'criteria': [
             {'id': 'WELCOME_X', 'section_id': 'quality', 'title': 'Welcome', 'instruction': 'Check the operator greeting.', 'kind': 'binary', 'weight': 5, 'allow_na': True, 'na_rule': 'Synthetic allowed omission.', 'levels': []},
             {'id': 'CLARITY_X', 'section_id': 'quality', 'title': 'Clarity', 'instruction': 'Choose one configured level.', 'kind': 'scale', 'weight': 15, 'allow_na': False, 'na_rule': None, 'levels': [{'value': 0, 'description': 'Missing'}, {'value': 7, 'description': 'Partial'}, {'value': 10, 'description': 'Complete'}]},
             {'id': 'RISK_X', 'section_id': 'risk', 'title': 'Critical flag', 'instruction': 'Flag separately, without numeric penalty.', 'kind': 'flag', 'weight': 0, 'allow_na': False, 'na_rule': None, 'levels': []}]}


def dataset(group=GROUP):
    records = []
    for language in ['RU', 'KZ', 'EN']:
        call = language == 'EN'
        turns = []
        texts = ['<img src=x onerror=alert(1)>', 'Synthetic bot greeting.', QUOTE,
                 '<script>alert(1)</script>', 'Synthetic long message: ' + ('Қазақша / Русский / English. ' * 180)]
        for speaker, text in zip(['client', 'bot', 'operator', 'system', 'operator'], texts):
            turns.append({'timestamp': '2026-11-07T10:00:00+05:00' if call else '00:01', 'speaker': speaker, 'text': text})
        records.append({'conversation_id': language, 'language': language, 'channel': 'voice call' if call else 'agent chat',
                        'transcript': turns, 'audio_url': 'https://example.invalid/synthetic.wav' if call else None})
    return {'error': '', 'isSuccess': True, 'data': {'dataset_group_id': group, 'total_records': len(records), 'records': records}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cqa-t12-') as temporary:
        directory = Path(temporary)
        db = directory / 'workspace.sqlite'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        process = None
        log = (directory / 'java.log').open('wb')
        proxy = None

        def http(method, route, body=None, expected=200):
            payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
            req = Request(base + route, data=payload, method=method, headers={'Content-Type': 'application/json'})
            try:
                with urlopen(req, timeout=15) as response:
                    code, data = response.status, response.read()
            except HTTPError as error:
                code, data = error.code, error.read()
            assert code == expected, f'HTTP {code}, expected {expected}'
            return json.loads(data)

        def start():
            nonlocal process
            process = subprocess.Popen(['java', '-jar', str(JAR), f'--server.port={port}', f'--cqa.db-path={db}',
                                        '--spring.main.banner-mode=off', '--logging.level.root=WARN'], cwd=directory,
                                       env={**os.environ, 'CQA_ORGANIZER_URL': ''}, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(300):
                assert process.poll() is None, 'Java child exited'
                try:
                    assert http('GET', '/api/health')['status'] == 'ok'
                    return
                except (URLError, ConnectionError):
                    time.sleep(.1)
            raise AssertionError('Startup timeout')

        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process = None

        def snapshots():
            with sqlite3.connect(db) as connection:
                return [connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                        for table in ['checklists', 'conversations', 'evaluations']]

        try:
            start()
            assert http('POST', '/api/datasets/import', dataset())['imported_records'] == 3
            assert http('POST', '/api/checklists/ui-synthetic', DRAFT)['version'] == 1
            source = http('GET', '/api/conversations/UI-SYNTHETIC:RU')
            assert source['messages'][2] == {'id': 'm0003', **dataset()['data']['records'][0]['transcript'][2]}
            assert [m['id'] for m in source['messages']] == [f'm{i:04}' for i in range(1, 6)]
            changed = copy.deepcopy(DRAFT)
            changed['title'] = 'Synthetic rubric v2'
            changed['criteria'][0]['id'] = 'NEW_ARBITRARY_ID'
            assert http('PUT', '/api/checklists/ui-synthetic?expected_version=1', changed)['version'] == 2
            assert http('GET', '/api/checklists/ui-synthetic?version=1')['criteria'][0]['id'] == 'WELCOME_X'
            assert http('PUT', '/api/checklists/ui-synthetic?expected_version=1', changed, 409)['detail']['code'] == 'VERSION_CONFLICT'
            answers = [{'criterion_id': c['id'], 'answer': answer, 'value': value, 'explanation': 'Synthetic manual explanation.',
                        'evidence': [{'message_id': 'm0003', 'quote': QUOTE}]}
                       for c, answer, value in zip(DRAFT['criteria'], ['na', 'scale', 'yes'], [None, 7, None])]
            saved = http('POST', '/api/evaluations/manual', {'conversation_id': 'UI-SYNTHETIC:RU', 'checklist_key': 'ui-synthetic', 'checklist_version': 1, 'answers': answers}, 201)
            route = '/api/evaluations/' + saved['id']
            assert saved['original_score']['overall_score'] == 70
            assert saved['original_score']['criteria'][1]['raw_points'] == 10.5
            assert saved['original_score']['applicable_weight'] == 15
            assert saved['original_score']['critical_violation'] is True
            original = snapshots()
            appeal = http('POST', route + '/appeals', {'criterion_id': 'WELCOME_X', 'comment': 'Synthetic confirm.'}, 201)
            view = http('GET', route)
            view = http('POST', '/api/appeals/' + appeal['id'] + '/resolve?expected_revision=' + str(view['review_revision']), {'decision': 'confirm', 'reason': 'Synthetic confirmation.', 'replacement': None})
            appeal = http('POST', route + '/appeals', {'criterion_id': 'CLARITY_X', 'comment': 'Synthetic change.'}, 201)
            replacement = {**answers[1], 'value': 0}
            decision = {'decision': 'change', 'reason': 'Synthetic correction.', 'replacement': replacement}
            assert http('POST', '/api/appeals/' + appeal['id'] + '/resolve?expected_revision=0', decision, 409)['detail']['code'] == 'REVIEW_CONFLICT'
            view = http('GET', route)
            view = http('POST', '/api/appeals/' + appeal['id'] + '/resolve?expected_revision=' + str(view['review_revision']), decision)
            assert view['final_score']['overall_score'] == 0
            assert view['original_score'] == saved['original_score'] and snapshots() == original
            assert http('POST', '/api/datasets/fetch', {'group_id': 'SYNTHETIC'}, 503)['detail']['code'] == 'ORGANIZER_UNCONFIGURED'
            assert http('POST', '/api/evaluations/auto', {'request_id': '00000000-0000-4000-8000-000000000001', 'conversation_id': source['id'], 'checklist_key': 'ui-synthetic', 'checklist_version': 1}, 501)['detail']['code'] == 'EVALUATOR_UNCONFIGURED'
            stop(); start()
            assert http('GET', route) == view and snapshots() == original
            print('PASS: packaged JAR health/import, exact messages, arbitrary checklist v1/v2, historical pinning, manual70/raw10.5/N-A/critical, confirm/change/CAS409, immutable originals and restart.', flush=True)
            print('NOT RUN: real Organizer, real DEV/CONTROL, Groq/ML, external audio.', flush=True)
            if args.serve:
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *_):
                        pass

                    def handle_request(self):
                        if self.path.startswith('/__tests/'):
                            name = self.path.split('?', 1)[0].removeprefix('/__tests/') or 'index.html'
                            if name == 'fixture.json':
                                data = json.dumps({'draft': DRAFT, 'dataset': dataset(), 'quote': QUOTE}).encode()
                                content_type = 'application/json'
                            elif name in ['index.html', 'workspace-tests.js']:
                                data = (ROOT / 'server/src/test/browser' / name).read_bytes()
                                content_type = 'text/html' if name.endswith('.html') else 'text/javascript'
                            else:
                                self.send_error(404)
                                return
                            self.send_response(200)
                            self.send_header('Content-Type', content_type + '; charset=utf-8')
                            self.send_header('Content-Length', str(len(data)))
                            self.end_headers(); self.wfile.write(data)
                            return
                        body = self.rfile.read(int(self.headers.get('Content-Length', '0'))) or None
                        req = Request(base + self.path, data=body, method=self.command, headers={'Content-Type': self.headers.get('Content-Type', 'application/json')})
                        try:
                            response = urlopen(req, timeout=40)
                        except HTTPError as error:
                            response = error
                        with response:
                            data = response.read()
                            self.send_response(response.code)
                            self.send_header('Content-Type', response.headers.get('Content-Type', 'application/octet-stream'))
                            self.send_header('Cache-Control', 'no-store')
                            self.send_header('Content-Length', str(len(data)))
                            self.end_headers(); self.wfile.write(data)

                    do_GET = handle_request
                    do_POST = handle_request
                    do_PUT = handle_request

                proxy = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                threading.Thread(target=proxy.serve_forever, daemon=True).start()
                print(f'WORKSPACE http://127.0.0.1:{proxy.server_port}/', flush=True)
                print(f'BROWSER TESTS http://127.0.0.1:{proxy.server_port}/__tests/', flush=True)
                print('Only synthetic temporary database. Enter restart to restart own JAR, or Enter to stop.', flush=True)
                while input().strip() == 'restart':
                    stop(); start(); print('RESTARTED: own JAR, same temporary SQLite.', flush=True)
        finally:
            if proxy:
                proxy.shutdown(); proxy.server_close()
            stop(); log.close()


if __name__ == '__main__':
    main()
