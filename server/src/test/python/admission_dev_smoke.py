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
    source_args=parser.add_mutually_exclusive_group(required=True)
    source_args.add_argument('--dataset', type=Path)
    source_args.add_argument('--synthetic-fixtures', action='store_true', help='Adapt the six existing ML conversation fixtures; no new text, no real data')
    parser.add_argument('--ml-python', type=Path, required=True)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--all-chats', action='store_true', help='Explicitly select every existing chat for this OFFLINE test')
    parser.add_argument('--group-id', help='Test-only copy: change group metadata, never the source conversations')
    args = parser.parse_args()
    dataset_path=args.dataset.resolve() if args.dataset else None
    if args.synthetic_fixtures:
        inputs=[json.loads(p.read_bytes())['conversation'] for p in sorted((ROOT/'ml-service/tests/fixtures').glob('*/request.json'))]
        assert len(inputs)==6 and all(c['dataset_group_id']=='SYNTHETIC' for c in inputs)
        records=[{'conversation_id':c['conversation_id'],'language':c['language'],'channel':c['channel'],'audio_url':None,
                  'transcript':[{k:m[k] for k in ('timestamp','speaker','text')} for m in c['messages']]} for c in inputs]
        envelope={'isSuccess':True,'error':'','data':{'dataset_group_id':'SYNTHETIC','total_records':len(records),'records':records}}
        raw=json.dumps(envelope,ensure_ascii=False).encode()
    else:
        raw=dataset_path.read_bytes(); envelope=json.loads(raw)
    if args.group_id:
        envelope['data']['dataset_group_id']=args.group_id
        raw=json.dumps(envelope,ensure_ascii=False).encode()
    group=envelope['data']['dataset_group_id']; rows=envelope['data']['records']
    selected=[]
    for language in ('RU','KZ','EN'):
        candidates=[r for r in rows if r['channel']=='agent chat' and r['language']==language]
        assert len(candidates)>=(1 if args.synthetic_fixtures else 5), 'Source must contain the requested language sample'
        selected.extend(group+':'+r['conversation_id'] for r in (candidates if args.all_chats else candidates[:5]))
    def port():
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));return s.getsockname()[1]
    jp,mp=port(),port();java_url=f'http://127.0.0.1:{jp}';ml_url=f'http://127.0.0.1:{mp}'
    env={k:v for k,v in os.environ.items() if not any(w in k for w in ('GROQ','CQA_','ML_','SPRING_','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'))}
    with tempfile.TemporaryDirectory(prefix='cqa-admission-private-') as temporary:
        folder=Path(temporary)
        if args.group_id or args.synthetic_fixtures:
            dataset_path=folder/'relabeled-private-source.json';dataset_path.write_bytes(raw);dataset_path.chmod(0o600)
        grant_path=folder/'shared.ml-approval.json';peer_path=folder/'mismatch.ml-approval.json';counter=folder/'counts.log'
        log=(folder/'services.log').open('wb');java=None;python=None;proxy=None;db=folder/'cqa.sqlite';behavior=folder/'offline-behavior'
        def counts():
            lines=counter.read_text().splitlines() if counter.exists() else []
            return {'ml_posts':lines.count('ml_http_post'),'offline_provider_calls':lines.count('offline_provider'),'groq_calls':0}
        def http(base,method,route,body=None,expected=200,confirmed=False):
            headers={'Content-Type':'application/json'}
            if confirmed:headers['X-CQA-Rubric-Confirmed']='true'
            request=Request(base+route,method=method,data=None if body is None else body if isinstance(body,bytes) else json.dumps(body).encode(),headers=headers)
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
        def start_java(enabled=True,timeout=70000):
            nonlocal java
            java=subprocess.Popen(['java','-jar',str(ROOT/'server/target/freedom-cqa-server-0.1.0.jar'),f'--server.port={jp}',f'--cqa.db-path={db}',
                f'--cqa.ml-url={ml_url}/v1/evaluate','--cqa.ml-data-mode=approved_dataset',f'--cqa.ml-approval-file={grant_path}',
                '--cqa.ml-external-inference-enabled='+str(enabled).lower(),f'--cqa.ml-response-timeout-ms={timeout}','--cqa.organizer-url=','--logging.level.root=WARN','--spring.main.banner-mode=off'],env=env,cwd=folder,stdout=log,stderr=log)
            wait_ready(java_url,java,'/api/health',200)
        def start_python(enabled=True,expected=200,approval=None):
            nonlocal python
            ml_env={**env,'ML_DATA_POLICY':'approved_dataset','ML_APPROVAL_FILE':str(approval or grant_path),
                    'ML_EXTERNAL_TRANSFER_AUTHORIZED':str(enabled).lower(),'ML_ADMISSION_URL':ml_url+'/v1/evaluate'}
            python=subprocess.Popen([str(args.ml_python.absolute()),'-B',str(ROOT/'server/src/test/python/admission_offline_ml.py'),
                '--port',str(mp),'--counter',str(counter),'--behavior',str(behavior)],env=ml_env,cwd=folder,stdout=log,stderr=log)
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
            start_java(False);http(java_url,'POST','/api/datasets/import',raw)
            archived=folder/'dataset-sources'/(hashlib.sha256(raw).hexdigest()+'.dataset-source.json')
            assert archived.read_bytes()==raw, 'Java must retain exact source transport bytes'
            assert archived.stat().st_mode & 0o777 == 0o600
            assert archived.parent.stat().st_mode & 0o777 == 0o700
            grant_path.unlink()
            selection_path=folder/'selected.approval-selection.json'
            def prepare(*arguments):
                result=subprocess.run([str(args.ml_python.absolute()),'-B',str(ROOT/'scripts/prepare-approval.py'),*arguments],
                    env=env,cwd=folder,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                assert result.returncode==0, 'Private approval CLI failed; no customer data echoed'
            prepare('inspect','--source',str(archived),'--output',str(selection_path))
            selection=json.loads(selection_path.read_bytes());assert selection['selected_ids']==[]
            selection['selected_ids']=selected;selection_path.write_text(json.dumps(selection))
            prepare('create','--source',str(archived),'--selection',str(selection_path),'--output',str(grant_path),
                '--session-id','OFFLINE-REGRESSION-NOT-CONSENT','--approval-reference','TEST ONLY: no external permission',
                '--expires-at',grant['expires_at'],'--ml-url',ml_url+'/v1/evaluate','--checklist-key','chat-quality',
                '--min-version','1','--max-version','10','--max-criteria','100','--confirm-external-transfer')
            grant=json.loads(grant_path.read_bytes())
            print('PASS: exact existing source archived privately by Java; shared grant uses archived SHA-256.',flush=True)
            assert http(java_url,'GET',status_route(selected[0]))['reason']=='EXTERNAL_INFERENCE_DISABLED'
            http(java_url,'POST','/api/evaluations/auto',auto_body(selected[0]),expected=503,confirmed=True)
            assert counts()['ml_posts']==0
            stop(java);start_java()
            local_allowed=sum(http(java_url,'GET',status_route(group+':'+r['conversation_id']))['selection_allowed'] for r in rows)
            assert local_allowed==len(selected)
            print(f'PASS: Java admission: {len(selected)} explicit existing chats; opt-in absent denies before ML. Groq calls=0.',flush=True)
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
            assert approved_count==len(selected), 'Only selected chats may be ready; calls and other chats must be blocked'
            print(f'PASS: Java/Python opt-ins; {len(selected)} admitted/{len(rows)-len(selected)} denied; calls excluded.',flush=True)
            call_id=next(group+':'+r['conversation_id'] for r in rows if r['channel']=='voice call')
            for field,value in [('approval_version',1),('expires_at','2000-01-01T00:00:00Z'),('dataset_sha256','0'*64),('provider','other'),('model','openai/gpt-oss-120b'),('conversation_ids',['NOT-IN-DATASET']),('conversation_ids',[call_id])]:
                invalid=copy.deepcopy(grant);invalid[field]=value;write_grant(invalid)
                assert not http(java_url,'GET',status_route(selected[0]))['ready']
                http(ml_url,'POST','/v1/evaluate',context(selected[0]),expected=503,confirmed=True)
                assert counts()['offline_provider_calls']==0
            write_grant(grant)
            archived.write_bytes(raw+b' ')
            assert not http(java_url,'GET',status_route(selected[0]))['ready']
            http(ml_url,'POST','/v1/evaluate',context(selected[0]),expected=503,confirmed=True)
            assert counts()['offline_provider_calls']==0
            archived.write_bytes(raw)
            grant_path.unlink();assert not http(java_url,'GET',status_route(selected[0]))['ready']
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
            if args.all_chats:
                for cid in selected[1:]:
                    result=http(java_url,'POST','/api/evaluations/auto',auto_body(cid,2),confirmed=True)
                    assert len(result['original_answers'])==8 and result['checklist_version']==2
                assert counts()['offline_provider_calls']==len(selected)+1
                print(f'PASS: {len(selected)} distinct existing chats evaluated via real Java/Python/offline HTTP.',flush=True)
            assert http(ml_url,'GET','/health')['grant_sha256']==hashlib.sha256(grant_path.read_bytes()).hexdigest()
            stop(java);start_java();assert http(java_url,'GET','/api/evaluations/'+first['id'])==first
            assert http(java_url,'GET','/api/evaluations/'+second['id'])==second
            print('PASS: real Java/Python HTTP admission, missing confirmation/invalid grants/mismatched peer, offline v1-v2, immutable v1, ledger replay/restart. Groq calls=0.',flush=True)
            if args.serve:
                stop(java);db=folder/'browser.sqlite';archived.unlink();start_java()
                class Proxy(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def handle_request(self):
                        body=self.rfile.read(int(self.headers.get('Content-Length','0'))) or None
                        if self.path=='/__tests/state':
                            out=json.dumps({**counts(),'selected':selected,'group':group,'total':len(rows),'call_count':sum(r['channel']=='voice call' for r in rows),'synthetic':args.synthetic_fixtures,'source_sha256':hashlib.sha256(raw).hexdigest(),'archive_verified':archived.exists() and archived.read_bytes()==raw}).encode();code=200;ctype='application/json'
                        elif self.path=='/__tests/source':
                            out=raw;code=200;ctype='application/json'
                        elif self.path=='/__tests/fault' and self.command=='POST':
                            mode=json.loads(body)['mode'];assert mode in ('invalid','slow','normal')
                            behavior.write_text(mode)
                            stop(java);start_java(timeout=200 if mode=='slow' else 70000)
                            out=b'{}';code=200;ctype='application/json'
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
                input('Enter stops only owned processes and deletes temporary test databases.\n')
        finally:
            if proxy:proxy.shutdown();proxy.server_close()
            stop(java);stop(python);log.close()


if __name__=='__main__':main()
