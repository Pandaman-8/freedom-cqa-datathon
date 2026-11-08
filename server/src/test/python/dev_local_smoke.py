"""Private supplied dataset checks. Never calls a model or an external URL.

Input is deliberately required and never bundled. --serve exposes the tested temporary
Java database through a loopback browser harness. Technical manual answers are labelled
as such, never presented as model output or human quality annotations.
"""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    envelope = json.loads(args.dataset.read_text())
    records = envelope['data']['records']
    calls = []

    class Tripwire(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            # Readiness remains honest: no model is running behind this test guard.
            payload = b'{"configured":false,"ready":false,"reason":"EVALUATOR_UNCONFIGURED","contract_version":"2.0.0"}'
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            calls.append(1)
            self.send_response(500)
            self.end_headers()

    with tempfile.TemporaryDirectory(prefix='cqa-private-dev-') as tmp:
        guard = ThreadingHTTPServer(('127.0.0.1', 0), Tripwire)
        threading.Thread(target=guard.serve_forever, daemon=True).start()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        process = None
        proxy = None
        log = open(Path(tmp) / 'java.log', 'wb')
        # Do not inherit provider credentials, existing approvals or production database settings.
        env = {k: v for k, v in os.environ.items() if not any(w in k for w in
               ('GROQ', 'CQA_', 'ML_', 'SPRING_', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'))}
        env.update(CQA_ORGANIZER_URL='', CQA_ML_URL=f'http://127.0.0.1:{guard.server_port}/v1/evaluate')

        def http(method, route, body=None, expected=200):
            request = Request(base + route, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                              method=method, headers={'Content-Type': 'application/json'})
            try:
                response = urlopen(request, timeout=20)
            except HTTPError as error:
                response = error
            with response:
                assert response.status == expected, f'HTTP {response.status}, expected {expected}'
                return json.load(response)

        def start():
            nonlocal process
            process = subprocess.Popen(['java', '-jar', str(ROOT / 'server/target/freedom-cqa-server-0.1.0.jar'),
                                        f'--server.port={port}', f'--cqa.db-path={tmp}/private.sqlite',
                                        '--cqa.ml-data-mode=synthetic_only', '--cqa.ml-approval-file=',
                                        '--logging.level.root=WARN', '--spring.main.banner-mode=off'],
                                       cwd=tmp, env=env, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(300):
                assert process.poll() is None, 'Java startup failed'
                try:
                    http('GET', '/api/health')
                    return
                except URLError:
                    time.sleep(.1)
            raise AssertionError('Java startup timeout')

        def stop():
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        try:
            start()
            assert http('POST', '/api/datasets/import', envelope)['imported_records'] == len(records)
            summaries = http('GET', '/api/conversations')
            assert len(summaries) == len(records)
            for record in records:
                cid = envelope['data']['dataset_group_id'] + ':' + record['conversation_id']
                stored = http('GET', '/api/conversations/' + quote(cid, safe=''))
                assert stored['transcript'] == record['transcript'], 'Transcript mismatch'
                assert stored['audio_url'] == record.get('audio_url'), 'Audio locator mismatch'
                assert stored['language'] == record['language'] and stored['channel'] == record['channel']
                assert stored['messages'] == [dict(id=f'm{i:04}', **m) for i, m in enumerate(record['transcript'], 1)]
            http('POST', '/api/datasets/import', envelope)
            assert len(http('GET', '/api/conversations')) == len(records)
            rubric = next(c for c in http('GET', '/api/checklists') if {r['id'] for r in c['criteria']} == {f'C{i:02}' for i in range(1, 9)})
            source = http('GET', '/api/conversations/' + quote(summaries[0]['id'], safe=''))
            evidence = next(m for m in source['messages'] if m['speaker'] == 'operator' and m['text'].strip())
            answers = [{'criterion_id': c['id'], 'answer': 'scale' if c['kind'] == 'scale' else 'no',
                        'value': 0 if c['kind'] == 'scale' else None,
                        'explanation': 'Техническая проверка. Не является оценкой качества диалога.',
                        'evidence': [{'message_id': evidence['id'], 'quote': evidence['text']}]} for c in rubric['criteria']]
            payload = {'conversation_id': source['id'], 'checklist_key': rubric['key'], 'checklist_version': rubric['version'], 'answers': answers}
            saved = http('POST', '/api/evaluations/manual', payload, 201)
            assert saved['origin'] == 'manual' and saved['original_score']['overall_score'] == 0
            route = '/api/evaluations/' + saved['id']
            appeal = http('POST', route + '/appeals', {'criterion_id': 'C01', 'comment': 'Техническая проверка пересчёта.'}, 201)
            current = http('GET', route)
            replacement = copy.deepcopy(next(a for a in answers if a['criterion_id'] == 'C01'))
            replacement['answer'] = 'yes'
            resolve = '/api/appeals/' + appeal['id'] + '/resolve?expected_revision=' + str(current['review_revision'])
            decision = {'decision': 'change', 'reason': 'Техническая проверка без модели.', 'replacement': replacement}
            final = http('POST', resolve, decision)
            assert final['original_score'] == saved['original_score'] and final['original_answers'] == saved['original_answers']
            assert final['final_score']['overall_score'] > 0
            assert http('POST', resolve, decision, 409)['detail']['code'] == 'REVIEW_CONFLICT'
            draft = {k: copy.deepcopy(rubric[k]) for k in ('title', 'description', 'sections', 'criteria')}
            draft['criteria'][0]['id'] = 'TECHNICAL_NEW_ITEM'
            draft['criteria'][0]['instruction'] = 'Техническая проверка произвольного критерия; не экспертная рубрика.'
            v2 = http('PUT', '/api/checklists/' + quote(rubric['key']) + '?expected_version=' + str(rubric['version']), draft)
            answers_v2 = copy.deepcopy(answers)
            answers_v2[0]['criterion_id'] = 'TECHNICAL_NEW_ITEM'
            second = http('POST', '/api/evaluations/manual', {**payload, 'checklist_version': v2['version'], 'answers': answers_v2}, 201)
            assert http('GET', '/api/checklists/' + quote(rubric['key']) + '?version=' + str(rubric['version'])) == rubric
            for row in summaries:
                request_id = str(uuid.uuid4())
                result = http('POST', '/api/evaluations/auto', {'request_id': request_id, 'conversation_id': row['id'],
                              'checklist_key': rubric['key'], 'checklist_version': rubric['version']}, 503)
                assert result['detail']['code'] == 'PRIVACY_POLICY_UNCONFIGURED'
                http('GET', '/api/evaluation-requests/' + request_id, expected=404)
            readiness = http('GET', '/api/ai/status?conversation_id=' + quote(source['id'], safe='') + '&checklist_key=' + quote(rubric['key']) + '&checklist_version=' + str(v2['version']))
            assert not readiness['ready'] and not readiness['selection_allowed'] and not readiness['ml_ready']
            stop()
            start()
            assert len(http('GET', '/api/conversations')) == len(records)
            assert http('GET', route) == final and http('GET', '/api/evaluations/' + second['id']) == second
            assert not calls, 'Unexpected outbound ML POST'
            print(f'PASS: {len(records)} supplied conversations; exact import/idempotence/manual/review/CAS/v1-v2/restart; all AI denied; ML POST=0. Technical manual results only.', flush=True)
            if args.serve:
                class Proxy(BaseHTTPRequestHandler):
                    def log_message(self, *_):
                        pass

                    def forward(self):
                        if self.path.startswith('/__tests/'):
                            files = {'/__tests/': ('beta-dev.html', 'text/html'), '/__tests/beta-dev-tests.js': ('beta-dev-tests.js', 'text/javascript')}
                            if self.path == '/__tests/status':
                                data, content_type = json.dumps({'ml_posts': len(calls)}).encode(), 'application/json'
                            elif self.path in files:
                                filename, content_type = files[self.path]
                                data = (ROOT / 'server/src/test/browser' / filename).read_bytes()
                            else:
                                self.send_error(404)
                                return
                            self.send_response(200)
                            self.send_header('Content-Type', content_type + '; charset=utf-8')
                            self.end_headers()
                            self.wfile.write(data)
                            return
                        request = Request(base + self.path, data=self.rfile.read(int(self.headers.get('Content-Length', '0'))) or None,
                                          method=self.command, headers={'Content-Type': self.headers.get('Content-Type', 'application/json')})
                        try:
                            response = urlopen(request, timeout=20)
                        except HTTPError as error:
                            response = error
                        with response:
                            data = response.read()
                            self.send_response(response.status)
                            self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                            self.end_headers()
                            self.wfile.write(data)
                    do_GET = do_POST = do_PUT = forward
                proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
                threading.Thread(target=proxy.serve_forever, daemon=True).start()
                print(f'PRIVATE DEV BROWSER: http://127.0.0.1:{proxy.server_port}/__tests/', flush=True)
                input('Enter stops only owned test processes and removes the temporary database.\n')
                assert not calls, 'Unexpected outbound ML POST'
        finally:
            if proxy:
                proxy.shutdown()
                proxy.server_close()
            stop()
            guard.shutdown()
            guard.server_close()
            log.close()


if __name__ == '__main__':
    main()
