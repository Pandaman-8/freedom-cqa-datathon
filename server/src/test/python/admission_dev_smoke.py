"""Private existing DEV + real Java/Python HTTP, offline provider only. Never a live E2E.

No source data is bundled. Test approvals exist only in a disposable directory and
are not evidence of consent. Python's launcher rejects all external networking.
"""
import argparse
import copy
import hashlib
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
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--ml-python', type=Path, required=True)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    dataset_path=args.dataset.resolve()
    raw=dataset_path.read_bytes(); envelope=json.loads(raw)
    group=envelope['data']['dataset_group_id']; rows=envelope['data']['records']
    selected=[]
    for language in ('RU','KZ','EN'):
        candidates=[r for r in rows if r['channel']=='agent chat' and r['language']==language]
        assert len(candidates)>=5, 'Existing source must contain five chats per language'
        selected.extend(group+':'+r['conversation_id'] for r in candidates[:5])
    def port():
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));return s.getsockname()[1]
    jp,mp=port(),port();java_url=f'http://127.0.0.1:{jp}';ml_url=f'http://127.0.0.1:{mp}'
    env={k:v for k,v in os.environ.items() if not any(w in k for w in ('GROQ','CQA_','ML_','SPRING_','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'))}
    with tempfile.TemporaryDirectory(prefix='cqa-admission-private-') as temporary:
        folder=Path(temporary);grant_path=folder/'shared.ml-approval.json';peer_path=folder/'mismatch.ml-approval.json';counter=folder/'counts.log'
        log=(folder/'services.log').open('wb');java=None;python=None;proxy=None;db=folder/'cqa.sqlite'
        def counts():
            lines=counter.read_text().splitlines() if counter.exists() else []
            return {'ml_posts':lines.count('ml_http_post'),'offline_provider_calls':lines.count('offline_provider'),'groq_calls':0}
        def http(base,method,route,body=None,expected=200,confirmed=False):
            headers={'Content-Type':'application/json'}
            if confirmed:headers['X-CQA-Rubric-Confirmed']='true'
            request=Request(base+route,method=method,data=None if body is None else json.dumps(body).encode(),headers=headers)
            try:response=urlopen(request,timeout=80)
            except HTTPError as error:response=error
            with response:
                assert response.status==expected, f'HTTP {response.status}, expected {expected}'
                return json.load(response)
        def wait_ready(base,process,route,expected):
            for _ in range(300):
                assert process.poll() is None, 'Owned service stopped unexpectedly; private logs retained only until cleanup'
                try:return http(base,'GET',route,expected=expected)
                except URLError:time.sleep(.1)
            raise AssertionError('Local startup timed out')
        def stop(process):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=20)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        def start_java(enabled=True):
            nonlocal java
            java=subprocess.Popen(['java','-jar',str(ROOT/'server/target/freedom-cqa-server-0.1.0.jar'),f'--server.port={jp}',f'--cqa.db-path={db}',
                f'--cqa.ml-url={ml_url}/v1/evaluate','--cqa.ml-data-mode=approved_dataset',f'--cqa.ml-approval-file={grant_path}',
                '--cqa.ml-external-inference-enabled='+str(enabled).lower(),'--cqa.organizer-url=','--logging.level.root=WARN','--spring.main.banner-mode=off'],env=env,cwd=folder,stdout=log,stderr=log)
            wait_ready(java_url,java,'/api/health',200)
        def start_python(enabled=True,expected=200,approval=None):
            nonlocal python
            ml_env={**env,'ML_DATA_POLICY':'approved_dataset','ML_APPROVAL_FILE':str(approval or grant_path),
                    'ML_EXTERNAL_TRANSFER_AUTHORIZED':str(enabled).lower(),'ML_ADMISSION_URL':ml_url+'/v1/evaluate'}
            python=subprocess.Popen([str(args.ml_python.absolute()),'-B',str(ROOT/'server/src/test/python/admission_offline_ml.py'),
                '--port',str(mp),'--counter',str(counter)],env=ml_env,cwd=folder,stdout=log,stderr=log)
            return wait_ready(ml_url,python,'/health',expected)
        def write_grant(value,path=None):
            # One grant file is shared by both processes. A second is used only for the mismatch test.
            path=path or grant_path
            with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as stream:
                stream.write(json.dumps(value,ensure_ascii=False).encode())
            path.chmod(0o600)
        grant={'approval_version':2,'session_id':'OFFLINE-REGRESSION-NOT-CONSENT','approval_reference':'TEST ONLY: no external permission',
               'approved_by':['Farhat','Nurtas'],'processing_mode':'external_approved','destination_description':'TEST configuration; outbound network forbidden',
               'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat().replace('+00:00','Z'),'ml_url':ml_url+'/v1/evaluate',
               'dataset_path':str(dataset_path),'dataset_sha256':hashlib.sha256(raw).hexdigest(),'conversation_ids':selected,
               'provider':'groq','model':'openai/gpt-oss-20b','checklist_scope':{'key':'chat-quality','min_version':1,'max_version':10,'max_criteria':100,'require_confirmation':True}}
        write_grant(grant)
        def status_route(cid,version=1):return '/api/ai/status?conversation_id='+quote(cid,safe='')+'&checklist_key=chat-quality&checklist_version='+str(version)
        def auto_body(cid,version=1):return {'request_id':str(uuid.uuid4()),'conversation_id':cid,'checklist_key':'chat-quality','checklist_version':version}
        def context(cid,version=1):
            source=http(java_url,'GET','/api/conversations/'+quote(cid,safe=''));rubric=http(java_url,'GET','/api/checklists/chat-quality?version='+str(version))
            projection={k:source[k] for k in ('id','dataset_group_id','conversation_id','channel','language','messages')}
            return {'contract_version':'2.0.0','request_id':str(uuid.uuid4()),'conversation':projection,'checklist':rubric}
        try:
            start_java(False);http(java_url,'POST','/api/datasets/import',envelope)
            assert http(java_url,'GET',status_route(selected[0]))['reason']=='EXTERNAL_INFERENCE_DISABLED'
            http(java_url,'POST','/api/evaluations/auto',auto_body(selected[0]),expected=503,confirmed=True)
            assert counts()['ml_posts']==0
            stop(java);start_java()
            local_allowed=sum(http(java_url,'GET',status_route(group+':'+r['conversation_id']))['selection_allowed'] for r in rows)
            assert local_allowed==15
            print('PASS: Java admission on existing DEV: exactly15 selected chats; opt-in absent denies before ML. Groq calls=0.',flush=True)
            # This must use Nurtas's independently implemented admission; no gate monkeypatching.
            peer_health=start_python(False,503)
            if peer_health.get('admission_protocol')!=2:
                raise SystemExit('BLOCKED: the installed Python service does not expose admission protocol2; Nurtas patch required. Groq calls=0.')
            http(ml_url,'POST','/v1/evaluate',context(selected[0]),expected=503,confirmed=True)
            assert counts()['offline_provider_calls']==0
            stop(python);peer_health=start_python()
            assert all(peer_health.get(k)==v for k,v in {
                'admission_protocol':2,'policy_mode':'approved_dataset','provider':'groq',
                'model':'openai/gpt-oss-20b','grant_sha256':hashlib.sha256(grant_path.read_bytes()).hexdigest()}.items())
            assert http(java_url,'GET',status_route(selected[0]))['ready']
            approved_count=0
            for row in rows:
                state=http(java_url,'GET',status_route(group+':'+row['conversation_id']))
                approved_count+=state['ready']
            assert approved_count==15, 'Only selected chats may be ready; calls and other chats must be blocked'
            print('PASS: Java/Python opt-in gates; exact selected15 existing chats; all other source IDs and calls denied.',flush=True)
            for field,value in [('approval_version',1),('expires_at','2000-01-01T00:00:00Z'),('dataset_sha256','0'*64),('provider','other'),('model','openai/gpt-oss-120b')]:
                invalid=copy.deepcopy(grant);invalid[field]=value;write_grant(invalid)
                assert not http(java_url,'GET',status_route(selected[0]))['ready']
                http(ml_url,'POST','/v1/evaluate',context(selected[0]),expected=503,confirmed=True)
                assert counts()['offline_provider_calls']==0
            write_grant(grant);grant_path.unlink();assert not http(java_url,'GET',status_route(selected[0]))['ready']
            http(ml_url,'POST','/v1/evaluate',context(selected[0]),expected=503,confirmed=True)
            assert not http(java_url,'GET',status_route(selected[0]))['ready'];write_grant(grant)
            # Check the actual Python gate, not only Java's interpretation of /health.
            for row in rows:
                cid=group+':'+row['conversation_id']
                if cid not in selected:
                    http(ml_url,'POST','/v1/evaluate',context(cid),expected=503,confirmed=True)
            for field,value in [('version',11),('key','OUTSIDE_APPROVED_SCOPE')]:
                outside=context(selected[0]);outside['checklist'][field]=value
                http(ml_url,'POST','/v1/evaluate',outside,expected=503,confirmed=True)
            assert counts()['offline_provider_calls']==0
            changed=copy.deepcopy(grant);changed['session_id']='OTHER-TEST-SESSION';write_grant(changed,peer_path)
            stop(python);start_python(approval=peer_path)
            assert http(java_url,'GET',status_route(selected[0]))['reason']=='PYTHON_GRANT_MISMATCH'
            stop(python);start_python();peer_path.unlink()
            http(java_url,'POST','/api/evaluations/auto',auto_body(selected[0]),expected=503)
            http(ml_url,'POST','/v1/evaluate',context(selected[0]),expected=503)
            assert counts()['offline_provider_calls']==0
            first_body=auto_body(selected[0]);first=http(java_url,'POST','/api/evaluations/auto',first_body,confirmed=True)
            assert first['origin']=='model' and len(first['original_answers'])==8
            assert http(java_url,'POST','/api/evaluations/auto',first_body)==first
            assert counts()['offline_provider_calls']==1
            rubric=context(selected[0])['checklist'];draft={k:copy.deepcopy(rubric[k]) for k in ('title','description','sections','criteria')}
            draft['criteria'][0]['id']='OFFLINE_DYNAMIC_CRITERION';draft['criteria'][0]['instruction']='Test-only dynamic criterion; structural validation, not a model quality judgment.'
            http(java_url,'PUT','/api/checklists/chat-quality?expected_version=1',draft)
            second=http(java_url,'POST','/api/evaluations/auto',auto_body(selected[0],2),confirmed=True)
            assert second['checklist_version']==2 and second['original_answers'][0]['criterion_id']=='OFFLINE_DYNAMIC_CRITERION'
            assert http(java_url,'GET','/api/evaluations/'+first['id'])==first
            assert counts()['offline_provider_calls']==2
            assert http(ml_url,'GET','/health')['grant_sha256']==hashlib.sha256(grant_path.read_bytes()).hexdigest()
            stop(java);start_java();assert http(java_url,'GET','/api/evaluations/'+first['id'])==first
            assert http(java_url,'GET','/api/evaluations/'+second['id'])==second
            print('PASS: real Java/Python HTTP admission, missing confirmation/invalid grants/mismatched peer, offline v1-v2, immutable v1, ledger replay/restart. Groq calls=0.',flush=True)
            if args.serve:
                stop(java);db=folder/'browser.sqlite';start_java();http(java_url,'POST','/api/datasets/import',envelope)
                class Proxy(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def handle_request(self):
                        body=self.rfile.read(int(self.headers.get('Content-Length','0'))) or None
                        if self.path=='/__tests/state':
                            out=json.dumps({**counts(),'selected':selected,'group':group}).encode();code=200;ctype='application/json'
                        elif self.path in ('/__tests/','/__tests/admission-dev-tests.js'):
                            name='admission-dev.html' if self.path=='/__tests/' else 'admission-dev-tests.js'
                            out=(ROOT/'server/src/test/browser'/name).read_bytes();code=200;ctype='text/html' if name.endswith('.html') else 'text/javascript'
                        else:
                            headers={k:self.headers[k] for k in ('Content-Type','X-CQA-Rubric-Confirmed') if self.headers.get(k)}
                            req=Request(java_url+self.path,data=body,method=self.command,headers=headers)
                            try:response=urlopen(req,timeout=80)
                            except HTTPError as error:response=error
                            with response:code=response.status;out=response.read();ctype=response.headers.get('Content-Type','application/json')
                        try:
                            self.send_response(code);self.send_header('Content-Type',ctype);self.end_headers();self.wfile.write(out)
                        except (BrokenPipeError,ConnectionResetError):pass
                    do_GET=handle_request;do_POST=handle_request;do_PUT=handle_request
                proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy);threading.Thread(target=proxy.serve_forever,daemon=True).start()
                print(f'PRIVATE OFFLINE BROWSER http://127.0.0.1:{proxy.server_port}/__tests/',flush=True)
                input('Enter stops only owned processes and deletes temporary DEV databases.\n')
        finally:
            if proxy:proxy.shutdown();proxy.server_close()
            stop(java);stop(python);log.close()


if __name__=='__main__':main()
