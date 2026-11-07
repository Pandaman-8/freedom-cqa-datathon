"""Test-only launcher for the real Python HTTP app. Never a production fallback.

No .env is read; outbound networking is forbidden even if a test is misconfigured.
The fixture provider replaces only provider.complete, not validation/policy/prompt.
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
    parser.add_argument('--mode', choices=('unconfigured', 'fixture'), required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--counter', type=Path, required=True)
    args = parser.parse_args()
    os.environ.update(GROQ_API_KEY='', GROQ_FREE_PLAN_CONFIRMED='false', ML_DATA_POLICY='synthetic_only')

    def local(host):
        if host == 'localhost':
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    connect, connect_ex, resolve = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def guarded(original):
        def call(sock, address):
            if not isinstance(address, tuple) or not local(address[0]):
                raise RuntimeError('External networking forbidden in release test')
            return original(sock, address)
        return call

    def resolve_local(host, *rest, **kwargs):
        if not local(host):
            raise RuntimeError('External DNS forbidden in release test')
        return resolve(host, *rest, **kwargs)

    socket.socket.connect = guarded(connect)
    socket.socket.connect_ex = guarded(connect_ex)
    socket.getaddrinfo = resolve_local
    sys.path.insert(0, str(ROOT / 'ml-service'))
    import uvicorn
    from app.config import Settings
    from app.main import create_app
    from app.provider import ProviderReply

    fixtures = {}
    for path in (ROOT / 'ml-service/tests/fixtures').glob('*/request.json'):
        request = json.loads(path.read_text())
        fixtures[request['conversation']['id']] = (request, json.loads(path.with_name('expected.json').read_text()))
    assert len(fixtures) == 6

    class FixtureProvider:
        async def complete(self, messages):
            context = json.loads(messages[1]['content'])
            approved, expected = fixtures[context['conversation']['id']]
            assert context['conversation'] == approved['conversation']
            assert context['checklist'] == approved['checklist']
            with args.counter.open('a') as stream:
                stream.write(json.dumps({'conversation_id': context['conversation']['id']}) + '\n')
            return ProviderReply(json.dumps(expected), 'openai/gpt-oss-20b', None, None)

    settings = Settings() if args.mode == 'unconfigured' else Settings(api_key='synthetic-test-key', free_plan_confirmed=True)
    # The app retains its production diagnostics labels. They are NOT proof of a Groq call.
    app = create_app(settings, FixtureProvider())
    uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
