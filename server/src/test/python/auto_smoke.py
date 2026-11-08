"""T13 packaged Java + local fake ML; never a real Python/provider/model E2E.

Only immutable own ML fixtures and temporary SQLite. --serve adds browser test routes.
No credentials, environment ML URL or user's database are used.
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
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / 'ml-service/tests/fixtures/en_public_na'
FIXTURE = json.loads((FIXTURES / 'request.json').read_text())
ANSWERS = json.loads((FIXTURES / 'expected.json').read_text())['answers']
JAR = ROOT / 'server/target/freedom-cqa-server-0.1.0.jar'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    state = {'mode': 'ok', 'calls': 0}
    entered = threading.Event()

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path != '/health':
                self.send_error(404)
                return
            payload = b'{"configured":true,"ready":true,"reason":null,"model":"fake-http","contract_version":"2.0.0"}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            assert self.path == '/v1/evaluate'
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert body['conversation'] == FIXTURE['conversation']
            assert body['checklist'] == FIXTURE['checklist']
            state['calls'] += 1
            mode = state['mode']
            entered.set()
            if mode in ('timeout', 'crash'):
                time.sleep(2.2 if mode == 'timeout' else 5)
            result = {'contract_version': '2.0.0', 'request_id': body['request_id'],
                      'conversation_id': body['conversation']['id'], 'checklist_key': body['checklist']['key'],
                      'checklist_version': body['checklist']['version'], 'answers': copy.deepcopy(ANSWERS),
                      'diagnostics': {'provider': 'local-test', 'model': 'fake-http', 'prompt_version': 'synthetic-test',
                                      'attempt_count': 1, 'input_tokens': None, 'output_tokens': None,
                                      'estimated_cost_usd': None, 'latency_ms': 1, 'warnings': []}}
            if mode == 'invalid':
                result['answers'][0]['evidence'][0]['quote'] = 'NOT IN SOURCE'
            data = json.dumps(result).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    fake = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    proxy = None
    with tempfile.TemporaryDirectory(prefix='cqa-t13-') as temporary:
        folder = Path(temporary)
        db = folder / 'auto.sqlite'
        log = (folder / 'java.log').open('wb')
        process = None
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        base = f'http://127.0.0.1:{port}'

        def http(method, route, body=None, expected=200):
            request = Request(base + route, data=None if body is None else json.dumps(body).encode(),
                              method=method, headers={'Content-Type': 'application/json'})
            try:
                with urlopen(request, timeout=15) as response:
                    code, data = response.status, response.read()
            except HTTPError as error:
                code, data = error.code, error.read()
            assert code == expected, f'HTTP {code}, expected {expected}: {route}'
            return json.loads(data)

        def start():
            nonlocal process
            process = subprocess.Popen(['java', '-jar', str(JAR), f'--server.port={port}', f'--cqa.db-path={db}',
                                        f'--cqa.ml-url=http://127.0.0.1:{fake.server_port}/v1/evaluate',
                                        '--cqa.ml-response-timeout-ms=1500', '--cqa.ml-connect-timeout-ms=500',
                                        '--cqa.organizer-url=', '--cqa.ml-data-mode=synthetic_only', '--cqa.ml-approval-file=', '--spring.main.banner-mode=off', '--logging.level.root=WARN'],
                                       cwd=folder, env={**os.environ, 'CQA_ML_URL': '', 'CQA_ORGANIZER_URL': '', 'GROQ_API_KEY': ''},
                                       stdout=log, stderr=subprocess.STDOUT)
            for _ in range(300):
                assert process.poll() is None, 'Own Java process exited'
                try:
                    if http('GET', '/api/health')['status'] == 'ok':
                        return
                except (URLError, ConnectionError):
                    time.sleep(.1)
            raise AssertionError('Java startup timeout')

        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process = None

        def payload():
            return {'request_id': str(uuid.uuid4()), 'conversation_id': FIXTURE['conversation']['id'],
                    'checklist_key': FIXTURE['checklist']['key'], 'checklist_version': 1}

        def status(body):
            return http('GET', '/api/evaluation-requests/' + body['request_id'])

        def originals():
            with sqlite3.connect(db) as connection:
                return connection.execute('SELECT * FROM evaluations ORDER BY id').fetchall()

        try:
            start()
            source = FIXTURE['conversation']
            dataset = {'isSuccess': True, 'data': {'dataset_group_id': source['dataset_group_id'], 'total_records': 1,
                       'records': [{'conversation_id': source['conversation_id'], 'language': source['language'], 'channel': source['channel'],
                                    'transcript': [{k: v for k, v in message.items() if k != 'id'} for message in source['messages']]}]}}
            http('POST', '/api/datasets/import', dataset)
            draft = {k: v for k, v in FIXTURE['checklist'].items() if k not in ('key', 'version')}
            http('POST', '/api/checklists/synthetic-local', draft)
            good = payload()
            saved = http('POST', '/api/evaluations/auto', good)
            assert saved['origin'] == 'model' and saved['original_score']['overall_score'] == 100
            assert status(good)['status'] == 'succeeded'
            assert http('POST', '/api/evaluations/auto', good) == saved and state['calls'] == 1
            conflict = {**good, 'checklist_version': 99}
            assert http('POST', '/api/evaluations/auto', conflict, 409)['detail']['code'] == 'REQUEST_ID_CONFLICT'
            original = originals()
            state['mode'] = 'invalid'
            invalid = payload()
            assert http('POST', '/api/evaluations/auto', invalid, 502)['detail']['code'] == 'EVALUATOR_INVALID_OUTPUT'
            assert status(invalid)['status'] == 'failed' and originals() == original
            state['mode'] = 'timeout'
            timed = payload()
            http('POST', '/api/evaluations/auto', timed, 504)
            assert status(timed)['status'] == 'unknown'
            calls = state['calls']
            http('POST', '/api/evaluations/auto', timed, 504)
            assert state['calls'] == calls
            # Kill our own Java while the fake server has received the POST: a real interrupted ledger.
            state['mode'] = 'crash'
            interrupted = payload()
            entered.clear()
            def pending():
                try:
                    http('POST', '/api/evaluations/auto', interrupted)
                except (ConnectionError, URLError):
                    pass
            sending = threading.Thread(target=pending)
            sending.start()
            assert entered.wait(5)
            assert status(interrupted)['status'] == 'pending'
            process.kill()
            process.wait(timeout=5)
            process = None
            sending.join(timeout=5)
            calls = state['calls']
            start()
            assert status(interrupted)['status'] == 'unknown'
            http('POST', '/api/evaluations/auto', interrupted, 504)
            assert state['calls'] == calls
            assert http('POST', '/api/evaluations/auto', good) == saved
            assert status(invalid)['status'] == 'failed' and originals() == original
            state['mode'] = 'ok'
            print('PASS: synthetic packaged Java + fake ML HTTP, strict evidence, model score100, duplicate/conflict IDs, timeout, actual process kill/restart, immutable originals, no replay.', flush=True)
            print('NOT RUN: actual Python service/provider/Groq/live model E2E; real DEV/CONTROL/Organizer/audio.', flush=True)
            if args.serve:
                class Proxy(BaseHTTPRequestHandler):
                    def log_message(self, *_):
                        pass

                    def handle_request(self):
                        body = self.rfile.read(int(self.headers.get('Content-Length', '0'))) or None
                        content_type = 'application/json'
                        code = 200
                        if self.path == '/__tests/mode' and self.command == 'POST':
                            value = json.loads(body)['mode']
                            assert value in ('ok', 'invalid', 'timeout')
                            state['mode'] = value
                            data = json.dumps(state).encode()
                        elif self.path == '/__tests/state':
                            data = json.dumps(state).encode()
                        elif self.path == '/__tests/fixture.json':
                            data = json.dumps(FIXTURE).encode()
                        elif self.path == '/__tests/restart' and self.command == 'POST':
                            before = originals()
                            stop()
                            start()
                            assert originals() == before, 'Restart changed immutable evaluation rows'
                            data = json.dumps({'status': 'restarted', 'originals_unchanged': True}).encode()
                        elif self.path in ('/__tests/', '/__tests/auto-tests.js', '/__tests/model-review.html', '/__tests/model-review-tests.js'):
                            name = 'auto-index.html' if self.path.endswith('/') else self.path.rsplit('/', 1)[1]
                            data = (ROOT / 'server/src/test/browser' / name).read_bytes()
                            content_type = 'text/html' if name.endswith('html') else 'text/javascript'
                        else:
                            request = Request(base + self.path, data=body, method=self.command, headers={'Content-Type': 'application/json'})
                            try:
                                response = urlopen(request, timeout=15)
                            except HTTPError as error:
                                response = error
                            with response:
                                code, data = response.status, response.read()
                                content_type = response.headers.get('Content-Type', 'application/json')
                        self.send_response(code)
                        self.send_header('Content-Type', content_type)
                        self.send_header('Content-Length', str(len(data)))
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        self.wfile.write(data)
                    do_GET = handle_request
                    do_POST = handle_request
                    do_PUT = handle_request
                proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
                threading.Thread(target=proxy.serve_forever, daemon=True).start()
                print(f'BROWSER TESTS http://127.0.0.1:{proxy.server_port}/__tests/', flush=True)
                print(f'T14 BROWSER TESTS http://127.0.0.1:{proxy.server_port}/__tests/model-review.html', flush=True)
                print('Enter to stop own synthetic fixture server.', flush=True)
                input()
        finally:
            if proxy:
                proxy.shutdown()
                proxy.server_close()
            stop()
            fake.shutdown()
            fake.server_close()
            log.close()


if __name__ == '__main__':
    main()
