import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {BatchRunner,BATCH_KEY,readManifest,itemState,lastAttempt,batchLock} from '../../main/resources/static/js/batch-state.js';
import {ApiError} from '../../main/resources/static/js/api.js';

function setup() {
  const values=new Map(),storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
  const rows=['A','B','C'].map(id=>({id:'OWN:'+id,dataset_group_id:'OWN'}));
  const requests=[],ledger=new Map(),evaluations=new Map();let mode='ok',gate=null,locked=false,active=0,maxActive=0;
  const lock=async action=>{if(locked)throw new Error('another tab');locked=true;try{return await action();}finally{locked=false;}};
  const api=async(path,options={})=>{
    if(path==='/api/conversations')return rows;
    if(path.startsWith('/api/checklists/'))return {key:'rubric',version:'9007199254740993'};
    if(path.startsWith('/api/evaluation-requests/')){
      const id=path.split('/').at(-1);if(!ledger.has(id))throw new ApiError(404,'NOT_FOUND');return ledger.get(id);
    }
    if(path.startsWith('/api/evaluations/')){
      if(options.method!=='POST')return evaluations.get(path.split('/').at(-1));
      const p=options.body;requests.push(p);active++;maxActive=Math.max(maxActive,active);
      assert.equal(readManifest(storage).items.find(i=>i.conversation_id===p.conversation_id).attempts.at(-1).request_id,p.request_id,'intent saved before POST');
      try{
        const current=mode;
        if(current==='preflight')throw new ApiError(503,'PRIVACY_POLICY_UNCONFIGURED');
        if(current==='conflict')throw new ApiError(409,'REQUEST_ID_CONFLICT');
        if(current==='absent')throw new ApiError(0,'NETWORK',true);
        const view={request_id:p.request_id,status:'pending',evaluation_id:null,error:null};ledger.set(p.request_id,view);
        if(gate)await gate;
        if(current==='pending')return view;
        if(current==='failed'||current==='unknown'){
          view.status=current;view.error={code:current==='failed'?'EVALUATOR_INVALID_OUTPUT':'EVALUATOR_TIMEOUT'};
          if(current==='failed')mode='ok';throw new ApiError(502,view.error.code);
        }
        const result={id:randomUUID(),origin:'model',conversation_id:p.conversation_id,checklist_key:p.checklist_key,checklist_version:String(p.checklist_version)};
        evaluations.set(result.id,result);view.status='succeeded';view.evaluation_id=result.id;
        if(current==='lost')throw new ApiError(0,'NETWORK',true);
        return result;
      }finally{active--;}
    }
    throw new Error('Unexpected path '+path);
  };
  const factory=()=>new BatchRunner({storage,api,lock,newId:randomUUID});
  return {storage,rows,requests,ledger,evaluations,factory,runner:factory(),set mode(v){mode=v;},set gate(v){gate=v;},get maxActive(){return maxActive;}};
}
async function prepared(){const s=setup();await s.runner.create('OWN',{key:'rubric',version:'9007199254740993'});return s;}
async function until(check){for(let i=0;i<100;i++){if(check())return;await new Promise(r=>setTimeout(r,2));}throw new Error('condition timeout');}

test('batch snapshots membership/version and submits each UUID once, strictly sequentially',async()=>{
 const s=await prepared();s.rows.push({id:'OWN:LATE',dataset_group_id:'OWN'});
 await Promise.all([s.runner.resume(),s.runner.resume()]);assert.equal(s.requests.length,3);assert.equal(s.maxActive,1);
 assert.deepEqual(s.requests.map(p=>p.conversation_id),['OWN:A','OWN:B','OWN:C']);
 assert(s.requests.every(p=>String(p.checklist_version)==='9007199254740993'));
 assert.equal(new Set(s.requests.map(p=>p.request_id)).size,3);
 await s.runner.resume();assert.equal(s.requests.length,3);assert(s.runner.manifest.items.every(i=>itemState(i)==='succeeded'));
});
test('pause waits for the current request, resume sends only remaining queued items',async()=>{
 const s=await prepared();let release;s.gate=new Promise(r=>release=r);const running=s.runner.resume();await until(()=>s.requests.length===1);
 s.runner.pause();release();await running;assert.equal(s.requests.length,1);assert.equal(s.runner.manifest.paused,true);
 s.gate=null;await s.runner.resume();assert.equal(s.requests.length,3);
});
test('known failure continues, retry requires acknowledgment/new UUID and preserves attempt history',async()=>{
 const s=await prepared();s.mode='failed';await s.runner.resume();assert.equal(s.requests.length,3);
 const old=lastAttempt(s.runner.manifest.items[0]).request_id;assert.equal(itemState(s.runner.manifest.items[0]),'failed');
 await assert.rejects(s.runner.retry('OWN:A',false));assert.equal(s.requests.length,3);
 await s.runner.retry('OWN:A',true);assert.equal(s.requests.length,4);assert.notEqual(s.requests[3].request_id,old);
 assert.deepEqual(s.runner.manifest.items[0].attempts.map(a=>a.state),['failed','succeeded']);
});
test('unknown stops the loop; explicit continue never retries it; explicit retry records a new UUID',async()=>{
 const s=await prepared();s.mode='unknown';await s.runner.resume();assert.equal(s.requests.length,1);
 await assert.rejects(s.runner.resume());assert.equal(s.requests.length,1);
 s.mode='ok';await s.runner.resume(true);assert.equal(s.requests.length,3);assert.equal(itemState(s.runner.manifest.items[0]),'unknown');
 await s.runner.retry('OWN:A',true);assert.equal(s.requests.length,4);assert.equal(s.runner.manifest.items[0].attempts.length,2);
});
test('reload after persisted success/lost response reconciles by GET without any POST',async()=>{
 const s=await prepared();s.mode='lost';await s.runner.resume();const replacement=s.factory();replacement.load();await replacement.refresh();
 assert.equal(s.requests.length,3);assert(replacement.manifest.items.every(i=>itemState(i)==='succeeded'));
});
test('reloaded pending blocks resume and retry until Java reports a terminal outcome',async()=>{
 const s=await prepared();s.mode='pending';await s.runner.resume();const replacement=s.factory();replacement.load();await replacement.refresh();
 assert.equal(itemState(replacement.manifest.items[0]),'pending');await assert.rejects(replacement.resume(true));await assert.rejects(replacement.retry('OWN:A',true));assert.equal(s.requests.length,1);
 s.ledger.get(s.requests[0].request_id).status='unknown';s.mode='ok';await replacement.refresh();await replacement.resume(true);assert.equal(s.requests.length,3);
});
test('missing status after transport loss remains uncertain, not silently queued',async()=>{
 const s=await prepared();s.mode='absent';await s.runner.resume();assert.equal(itemState(s.runner.manifest.items[0]),'not_found');
 const reloaded=s.factory();reloaded.load();await reloaded.refresh();await assert.rejects(reloaded.resume());assert.equal(s.requests.length,1);
 s.mode='ok';await reloaded.retry('OWN:A',true);assert.equal(s.requests.length,2);assert.equal(reloaded.manifest.items[0].attempts.length,2);
});
test('policy preflight503 with no ledger stays failed across reload, never implicitly retried',async()=>{
 const s=await prepared();s.mode='preflight';await s.runner.resume();assert.equal(s.requests.length,3);assert.equal(s.ledger.size,0);
 const reloaded=s.factory();await reloaded.refresh();assert(reloaded.manifest.items.every(i=>itemState(i)==='failed'));await reloaded.resume();assert.equal(s.requests.length,3);
});
test('storage failure before durable intent prevents POST; after POST leaves recoverable intent',async()=>{
 const s=await prepared(),save=s.storage.setItem;s.storage.setItem=()=>{throw new Error('quota');};
 await assert.rejects(s.runner.resume());assert.equal(s.requests.length,0);s.storage.setItem=save;
 let writes=0;s.storage.setItem=(k,v)=>{if(++writes>2)throw new Error('quota after response');save(k,v);};
 await assert.rejects(s.runner.resume());assert.equal(s.requests.length,1);
 s.storage.setItem=save;const reloaded=s.factory();await reloaded.refresh();assert.equal(itemState(reloaded.manifest.items[0]),'succeeded');assert.equal(s.requests.length,1);
});
test('two tab runners cannot overlap or overwrite a batch held by another tab',async()=>{
 const s=await prepared();let release;s.gate=new Promise(r=>release=r);const first=s.runner.resume();await until(()=>s.requests.length===1);
 const second=s.factory();await assert.rejects(second.resume(),/another tab/);await assert.rejects(second.create('OWN',{key:'rubric',version:1}),/another tab/);
 s.runner.pause();release();await first;assert.equal(s.requests.length,1);s.gate=null;await second.resume();assert.equal(s.requests.length,3);assert.equal(s.maxActive,1);
});
test('manifest corruption/duplicate request IDs fail closed without erasing recovery data',async()=>{
 const s=await prepared();s.storage.setItem(BATCH_KEY,'{bad');await assert.rejects(s.runner.resume());assert.equal(s.requests.length,0);assert.equal(s.storage.getItem(BATCH_KEY),'{bad');
 const fresh=await prepared();await fresh.runner.resume();const m=readManifest(fresh.storage);m.items[1].attempts[0].request_id=m.items[0].attempts[0].request_id;fresh.storage.setItem(BATCH_KEY,JSON.stringify(m));
 await assert.rejects(fresh.runner.resume());assert.equal(fresh.requests.length,3);
});
test('wrong saved evaluation identity cannot be shown as success or retried implicitly',async()=>{
 const s=await prepared();await s.runner.resume();const a=lastAttempt(s.runner.manifest.items[0]);s.evaluations.get(a.evaluation_id).conversation_id='OTHER';
 await s.runner.refresh();assert.equal(itemState(s.runner.manifest.items[0]),'conflict');assert.equal(lastAttempt(s.runner.manifest.items[0]).evaluation_id,null);
 await s.runner.resume();assert.equal(s.requests.length,3);
});
test('POST409 remains a conflict and cannot attach an unrelated ledger result',async()=>{
 const s=await prepared();s.mode='conflict';await s.runner.resume();assert.equal(s.requests.length,3);
 assert(s.runner.manifest.items.every(i=>itemState(i)==='conflict'&&lastAttempt(i).evaluation_id===null));
 const recovered=s.factory();await recovered.refresh();await recovered.resume();assert.equal(s.requests.length,3);
 s.mode='ok';await recovered.retry('OWN:A',true);assert.equal(s.requests.length,4);assert.deepEqual(recovered.manifest.items[0].attempts.map(a=>a.state),['conflict','succeeded']);
});
test('unavailable ledger read blocks remaining work; reconciling recovers without replay',async()=>{
 const s=await prepared(),api=s.runner.api;s.runner.api=async(p,o)=>{if(p.startsWith('/api/evaluation-requests/'))throw new ApiError(0,'NETWORK');return api(p,o);};
 await s.runner.resume();assert.equal(s.requests.length,1);assert.equal(itemState(s.runner.manifest.items[0]),'unresolved');await assert.rejects(s.runner.resume(true));
 s.runner.api=api;await s.runner.resume();assert.equal(s.requests.length,3);
});
test('forget requires explicit confirmation and terminal rows; Java history remains untouched',async()=>{
 const s=await prepared();await assert.rejects(s.runner.forget(true));await s.runner.resume();await assert.rejects(s.runner.forget(false));
 await s.runner.forget(true);assert.equal(s.storage.getItem(BATCH_KEY),null);assert.equal(s.ledger.size,3);assert.equal(s.evaluations.size,3);
});
test('Web Locks unavailable fails closed, without running the action',async()=>{
 if(globalThis.navigator?.locks)return;
 let called=false;await assert.rejects(batchLock(()=>{called=true;}));assert.equal(called,false);
});
