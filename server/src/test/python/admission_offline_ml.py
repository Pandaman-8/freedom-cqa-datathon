"""TEST ONLY: real ML HTTP/admission/validation with a structural offline provider.

Never run as a demo model. Uses caller-provided private grant and existing DEV locally.
External networking is blocked before importing the service. No .env is loaded.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--counter', type=Path, required=True)
    args = parser.parse_args()

    def local(host):
        try:
            return host == 'localhost' or ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    connect, connect_ex, resolve = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def guarded(original):
        def call(sock, address):
            if not isinstance(address, tuple) or not local(address[0]):
                raise RuntimeError('External network forbidden in admission regression')
            return original(sock, address)
        return call

    def resolve_local(host, *rest, **kwargs):
        if not local(host):
            raise RuntimeError('External DNS forbidden in admission regression')
        return resolve(host, *rest, **kwargs)

    socket.socket.connect = guarded(connect)
    socket.socket.connect_ex = guarded(connect_ex)
    socket.getaddrinfo = resolve_local
    # A deliberately unusable key. The only evaluator is injected through the existing test seam.
    os.environ.update(GROQ_API_KEY='OFFLINE-TEST-NOT-A-KEY', GROQ_MODEL='openai/gpt-oss-20b',
                      GROQ_FREE_PLAN_CONFIRMED='true')
    sys.path.insert(0, str(ROOT / 'ml-service'))
    import uvicorn
    from app.config import Settings
    from app.main import create_app
    from app.provider import ProviderReply

    def count(kind):
        with args.counter.open('a') as stream:
            stream.write(kind + '\n')  # Counts only: no IDs, transcript, rubric or private locators.

    class OfflineProvider:
        async def complete(self, messages):
            count('offline_provider')
            context = json.loads(messages[1]['content'])
            message = next(m for m in context['conversation']['messages'] if m['speaker'] == 'operator' and m['text'].strip())
            answers = []
            for c in context['checklist']['criteria']:
                answer = 'na' if c['allow_na'] else 'scale' if c['kind'] == 'scale' else 'no'
                answers.append({'criterion_id': c['id'], 'answer': answer,
                                'value': min(level['value'] for level in c['levels']) if answer == 'scale' else None,
                                'explanation': 'OFFLINE TEST ONLY: structural validation, not a model quality judgment.',
                                'evidence': [{'message_id': message['id'], 'quote': message['text']}]})
            return ProviderReply(json.dumps({'answers': answers}), 'openai/gpt-oss-20b', None, None)

    app = create_app(Settings.from_env(), OfflineProvider())

    @app.middleware('http')
    async def counters(request, call_next):
        if request.method == 'POST' and request.url.path == '/v1/evaluate':
            count('ml_http_post')
        return await call_next(request)

    uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
