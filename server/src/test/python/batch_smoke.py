"""T21 packaged Java and exact own fixtures with fake ML only. Never reads .env or calls a provider."""
import argparse
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
CASES = ('en_public_na', 'kz_public_na', 'ru_public_na')
FIXTURES = {name: json.loads((ROOT / 'ml-service/tests/fixtures' / name / 'request.json').read_text()) for name in (*CASES, 'ru_protected_violation')}
ANSWERS = {name: json.loads((ROOT / 'ml-service/tests/fixtures' / name / 'expected.json').read_text())['answers'] for name in FIXTURES}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    state = {'mode': 'ok', 'remaining': 0, 'calls': [], 'active': 0, 'max_active': 0}
    release = threading.Event()
    guard = threading.Lock()

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            assert self.path == '/v1/evaluate'
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            name = body['conversation']['conversation_id']
            assert name in FIXTURES and body['conversation'] == FIXTURES[name]['conversation']
            assert body['checklist'] == FIXTURES[name]['checklist']
            with guard:
                state['calls'].append({'request_id': body['request_id'], 'conversation_id': body['conversation']['id'], 'checklist_version': body['checklist']['version']})
                mode = state['mode'] if state['remaining'] else 'ok'
                state['remaining'] = max(0, state['remaining'] - 1)
                state['active'] += 1
                state['max_active'] = max(state['max_active'], state['active'])
            try:
                if mode == 'hold':
                    release.wait(10)
                elif mode == 'timeout':
                    time.sleep(3.5)
                answers = json.loads(json.dumps(ANSWERS[name]))
                if mode == 'invalid':
                    answers[0]['evidence'][0]['quote'] = 'NOT IN SOURCE'
                result = {'contract_version': '2.0.0', 'request_id': body['request_id'], 'conversation_id': body['conversation']['id'],
                          'checklist_key': body['checklist']['key'], 'checklist_version': body['checklist']['version'], 'answers': answers,
                          'diagnostics': {'provider': 'local-test', 'model': 'fake-batch', 'prompt_version': 'synthetic-test',
                                          'attempt_count': 1, 'input_tokens': None, 'output_tokens': None,
                                          'estimated_cost_usd': None, 'latency_ms': 1, 'warnings': []}}
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with guard:
                    state['active'] -= 1

    fake = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    proxy = None
    with tempfile.TemporaryDirectory(prefix='cqa-t21-') as temporary:
        folder = Path(temporary)
        database = folder / 'batch.sqlite'
        log = (folder / 'java.log').open('wb')
        process = None
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'

        def http(method, route, body=None, expected=200):
            try:
                res = urlopen(Request(base + route, data=None if body is None else json.dumps(body).encode(),
                                      method=method, headers={'Content-Type': 'application/json'}), timeout=15)
            except HTTPError as error:
                res = error
            with res:
                assert res.status == expected, f'{route}: HTTP {res.status}, expected {expected}'
                return json.loads(res.read())

        def start():
            nonlocal process
            process = subprocess.Popen(['java', '-jar', str(ROOT / 'server/target/freedom-cqa-server-0.1.0.jar'),
                                        f'--server.port={port}', f'--cqa.db-path={database}',
                                        f'--cqa.ml-url=http://127.0.0.1:{fake.server_port}/v1/evaluate',
                                        '--cqa.ml-response-timeout-ms=3000', '--cqa.organizer-url=',
                                        '--spring.main.banner-mode=off', '--logging.level.root=WARN'], cwd=folder,
                                       env={**os.environ, 'GROQ_API_KEY': '', 'CQA_ML_URL': '', 'CQA_ORGANIZER_URL': ''}, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(250):
                assert process.poll() is None, 'Own Java process exited'
                try:
                    if http('GET', '/api/health')['status'] == 'ok':
                        return
                except (URLError, ConnectionError):
                    time.sleep(.1)
            raise AssertionError('Java startup timeout')

        def stop(crash=False):
            nonlocal process
            if process:
                process.kill() if crash else process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process = None

        def dataset(request):
            c = request['conversation']
            return {'isSuccess': True, 'data': {'dataset_group_id': c['dataset_group_id'], 'total_records': 1,
                    'records': [{'conversation_id': c['conversation_id'], 'channel': c['channel'], 'language': c['language'],
                                 'transcript': [{k: v for k, v in m.items() if k != 'id'} for m in c['messages']]}]}}

        try:
            start()
            for name in CASES:
                http('POST', '/api/datasets/import', dataset(FIXTURES[name]))
            checklist = FIXTURES[CASES[0]]['checklist']
            http('POST', '/api/checklists/synthetic-local', {k: v for k, v in checklist.items() if k not in ('key', 'version')})
            saved = []
            for name in CASES:
                payload = {'request_id': str(uuid.uuid4()), 'conversation_id': FIXTURES[name]['conversation']['id'],
                           'checklist_key': 'synthetic-local', 'checklist_version': 1}
                result = http('POST', '/api/evaluations/auto', payload)
                assert result['origin'] == 'model' and result['original_score']['overall_score'] == 100
                saved.append((payload, result))
            assert len(state['calls']) == 3 and state['max_active'] == 1
            stop()
            start()
            for payload, result in saved:
                status = http('GET', '/api/evaluation-requests/' + payload['request_id'])
                assert status['status'] == 'succeeded' and status['evaluation_id'] == result['id']
                assert http('GET', '/api/evaluations/' + result['id']) == result
                assert http('POST', '/api/evaluations/auto', payload) == result
            assert len(state['calls']) == 3
            print('PASS: three exact RU/KZ/EN fixtures, sequential Java/fake ML, model score100, durable IDs/results across JVM restart, replay without inference.', flush=True)
            print('NOT RUN: Groq, real Python/provider, Organizer or real DEV/CONTROL. Browser scenarios are separate.', flush=True)
            if args.serve:
                class Proxy(BaseHTTPRequestHandler):
                    def log_message(self, *_):
                        pass

                    def handle_request(self):
                        body = self.rfile.read(int(self.headers.get('Content-Length', '0'))) or None
                        code, kind = 200, 'application/json'
                        if self.path == '/__tests/state':
                            data = json.dumps(state).encode()
                        elif self.path == '/__tests/mode' and self.command == 'POST':
                            mode = json.loads(body)['mode']
                            assert mode in ('ok', 'invalid', 'timeout', 'hold')
                            with guard:
                                state['mode'], state['remaining'] = mode, 0 if mode == 'ok' else 1
                                release.clear()
                            data = b'{}'
                        elif self.path == '/__tests/release' and self.command == 'POST':
                            release.set()
                            data = b'{}'
                        elif self.path == '/__tests/restart' and self.command == 'POST':
                            with sqlite3.connect(database) as db:
                                before = db.execute('SELECT * FROM evaluations ORDER BY id').fetchall()
                            stop(crash=True)
                            release.set()
                            start()
                            with sqlite3.connect(database) as db:
                                assert before == db.execute('SELECT * FROM evaluations ORDER BY id').fetchall()
                            data = b'{"originals_unchanged":true}'
                        elif self.path == '/__tests/import-late' and self.command == 'POST':
                            late = json.loads((ROOT / 'ml-service/tests/fixtures/ru_protected_violation/request.json').read_text())
                            data = json.dumps(http('POST', '/api/datasets/import', dataset(late))).encode()
                        elif self.path in ('/__tests/', '/__tests/batch-tests.js'):
                            name = 'batch.html' if self.path.endswith('/') else 'batch-tests.js'
                            data = (ROOT / 'server/src/test/browser' / name).read_bytes()
                            kind = 'text/html' if name.endswith('html') else 'text/javascript'
                        else:
                            try:
                                response = urlopen(Request(base + self.path, data=body, method=self.command, headers={'Content-Type': 'application/json'}), timeout=15)
                            except HTTPError as error:
                                response = error
                            with response:
                                code, data, kind = response.status, response.read(), response.headers.get('Content-Type', kind)
                        self.send_response(code)
                        self.send_header('Content-Type', kind)
                        self.send_header('Content-Length', str(len(data)))
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        try:
                            self.wfile.write(data)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                    do_GET = handle_request
                    do_POST = handle_request
                    do_PUT = handle_request

                proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
                threading.Thread(target=proxy.serve_forever, daemon=True).start()
                print(f'BATCH BROWSER http://127.0.0.1:{proxy.server_port}/__tests/', flush=True)
                print('Enter to stop owned processes and remove temporary SQLite.', flush=True)
                input()
        finally:
            release.set()
            if proxy:
                proxy.shutdown()
                proxy.server_close()
            stop()
            fake.shutdown()
            fake.server_close()
            log.close()


if __name__ == '__main__':
    main()
