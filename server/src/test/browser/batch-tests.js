const frame=document.querySelector('#workspace'),report=document.querySelector('#checks'),status=document.querySelector('#status');
const KEY='cqa:batch:v1',calls=[];let doc,win,loads=0;
const assert=(condition,label)=>{if(!condition)throw new Error(label);};
async function until(check,label){for(let i=0;i<400;i++){if(await check())return;await new Promise(r=>setTimeout(r,40));}throw new Error('Timeout: '+label);}
const all=(selector,root=doc)=>[...root.querySelectorAll(selector)];
const batch=()=>doc.querySelector('#batch-workspace'),idle=()=>doc.querySelector('#draft-status')?.textContent.startsWith('Несохранённых');
const manifest=()=>JSON.parse(win.localStorage.getItem(KEY));
const state=item=>item.attempts.at(-1)?.state||'queued';
function button(text,root=doc){const rows=all('button',root).filter(n=>n.textContent.trim()===text);assert(rows.length===1,'Unique button '+text);return rows[0];}
const click=(text,root=doc)=>button(text,root).click();
function field(label,root=doc){const rows=all('label',root).filter(n=>n.querySelector('span')?.textContent===label);assert(rows.length===1,'Unique label '+label);return rows[0].querySelector('input,select,textarea');}
function fill(label,value,root=doc){const input=field(label,root);if(input.type==='checkbox')input.checked=value;else input.value=value;input.dispatchEvent(new win.Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));}
const nav=name=>doc.querySelector('[data-view="'+name+'"]').click();
async function api(path,method='GET',body,expected=200){const r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});assert(r.status===expected,path+' HTTP '+r.status);return r.json();}
const fake=()=>api('/__tests/state');
const mode=value=>api('/__tests/mode','POST',{mode:value});
const ack=()=>fill('Я проверил статусы и допускаю повторную стоимость; разрешаю продолжение после unknown/404',true,batch());
const queued=()=>manifest().items.filter(i=>!i.attempts.length).length;
async function load(){
 frame.src='/?batch-regression='+(++loads)+'#batch';await new Promise(r=>frame.addEventListener('load',r,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;
 await until(()=>doc.querySelector('#connection').dataset.state==='ok'&&doc.querySelector('#checklist-picker .notice').textContent.includes('Выбрано:'),'app initialized');
 const native=win.fetch.bind(win);win.fetch=async(path,options={})=>{calls.push({path:String(path),method:options.method||'GET',body:options.body});return native(path,options);};
 await until(()=>!button('Сверить статусы batch',batch()).disabled||!manifest(),'restore finished');
}
async function selectVersion(version){
 fill('Checklist key','synthetic-local');await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('synthetic-local'),'checklist key');
 fill('Version (пусто = latest)',String(version));click('Открыть версию');
 await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('synthetic-local / v'+version+'.'),'pinned version');
}
async function prepare(version=1,group='SYNTHETIC'){
 await selectVersion(version);nav('batch');click('Обновить группы batch',batch());await until(()=>[...field('Группа для batch',batch()).options].some(n=>n.value===group),'group loaded');
 fill('Группа для batch',group,batch());click('Зафиксировать batch',batch());await until(()=>manifest()&&idle()&&!button('Запустить / продолжить batch',batch()).disabled,'manifest created');
}
async function runDone(){click('Запустить / продолжить batch',batch());await until(()=>idle()&&queued()===0,'batch complete');}
async function forget(){const original=win.confirm;win.confirm=()=>true;click('Убрать завершённый batch',batch());await until(()=>!manifest()&&idle(),'manifest removed');win.confirm=original;}
async function refresh(){click('Сверить статусы batch',batch());await until(()=>!button('Сверить статусы batch',batch()).disabled&&idle(),'reconciled');}
async function test(name,run){await run();const li=document.createElement('li');li.textContent='PASS: '+name;report.append(li);}

document.querySelector('#run').addEventListener('click',async()=>{
 document.querySelector('#run').disabled=true;status.textContent='RUNNING';
 try{
  await load();assert(!manifest(),'Fresh test origin required');let baseline,snapshot;
  await test('snapshot + double start + competing browser context + pause after one in-flight item',async()=>{
   await prepare();snapshot=manifest();assert(snapshot.items.length===3&&snapshot.checklist_version==='1','fixed3/v1 snapshot');
   baseline=(await fake()).calls.length;await mode('hold');click('Запустить / продолжить batch',batch());click('Запустить / продолжить batch',batch());
   await until(async()=>(await fake()).calls.length===baseline+1,'one fake request');
   const other=document.createElement('iframe');other.hidden=true;other.src='/#batch';document.body.append(other);await new Promise(r=>other.addEventListener('load',r,{once:true}));
   await until(()=>other.contentDocument.querySelector('#connection')?.dataset.state==='ok','second context');
   await until(()=>!button('Запустить / продолжить batch',other.contentDocument).disabled,'second context restored');
   click('Запустить / продолжить batch',other.contentDocument);
   await until(()=>other.contentDocument.querySelector('#batch-workspace').textContent.includes('другой вкладке'),'Web Lock contention');
   click('Пауза после текущего диалога',batch());await api('/__tests/release','POST',{});
   await until(()=>idle()&&state(manifest().items[0])==='succeeded','first result and pause');other.remove();
   assert((await fake()).calls.length===baseline+1&&queued()===2,'pause prevents next POST');
   assert((await fake()).max_active===1,'strictly one active inference');
  });
  await test('latest/checklist and group membership changes cannot change the pinned batch; result links use Java',async()=>{
   nav('checklists');fill('Название чек-листа','Synthetic batch future v2',doc.querySelector('#checklist-editor'));click('Сохранить новую версию',doc.querySelector('#checklist-editor'));
   await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('/ v2.')&&idle(),'UI v2');
   await api('/__tests/import-late','POST',{});nav('batch');await runDone();
   const m=manifest();assert(m.items.length===3&&m.checklist_version==='1','membership/version unchanged');
   assert((await fake()).calls.length===baseline+3,'only original three evaluated');
   for(const item of m.items){const a=item.attempts[0],s=await api('/api/evaluation-requests/'+a.request_id);assert(s.status==='succeeded','ledger success');const e=await api('/api/evaluations/'+s.evaluation_id);assert(e.checklist_version===1&&e.origin==='model','Java pinned v1');}
   click('Открыть результат',batch().querySelector('.batch-item'));await until(()=>doc.querySelector('[data-panel="results"]').hidden===false&&all('.score-card').length===2,'open Java result');
   nav('batch');await forget();
  });
  await test('known ML failure continues other items; explicit acknowledged retry uses a fresh UUID and preserves history',async()=>{
   await prepare();assert(manifest().items.length===4,'new batch sees late import');baseline=(await fake()).calls.length;
   await mode('invalid');await runDone();assert((await fake()).calls.length===baseline+4,'one call per item including failure');
   const failed=manifest().items.find(i=>state(i)==='failed');assert(failed,'failed row');const old=failed.attempts[0].request_id;
   let card=all('.batch-item',batch()).find(n=>n.dataset.batchConversation===failed.conversation_id);assert(button('Новая попытка для этого диалога',card).disabled,'retry needs acknowledgment');
   ack();card=all('.batch-item',batch()).find(n=>n.dataset.batchConversation===failed.conversation_id);click('Новая попытка для этого диалога',card);
   await until(()=>idle()&&manifest().items.every(i=>state(i)==='succeeded'),'retry result');
   const attempts=manifest().items.find(i=>i.conversation_id===failed.conversation_id).attempts;
   assert(attempts.length===2&&attempts[0].request_id===old&&attempts[1].request_id!==old,'attempt history/new UUID');assert((await fake()).calls.length===baseline+5,'single explicit retry');await forget();
  });
  await test('timeout unknown stops batch; reload is GET-only; explicit continue/retry never replays old UUID',async()=>{
   await prepare();baseline=(await fake()).calls.length;await mode('timeout');click('Запустить / продолжить batch',batch());
   await until(()=>idle()&&state(manifest().items[0])==='unknown','timeout unknown');const old=manifest().items[0].attempts[0].request_id;
   await load();assert((await fake()).calls.length===baseline+1&&queued()===3,'reload did not POST');
   click('Запустить / продолжить batch',batch());await until(()=>batch().textContent.includes('требуют явного согласия')&&idle(),'unknown requires consent');
   assert((await fake()).calls.length===baseline+1,'unknown not retried');ack();await runDone();
   assert(manifest().items[0].attempts[0].request_id===old&&state(manifest().items[0])==='unknown','old unknown retained');
   ack();click('Новая попытка для этого диалога',batch().querySelector('.batch-item'));await until(()=>idle()&&state(manifest().items[0])==='succeeded','explicit new UUID success');
   assert((await api('/api/evaluation-requests/'+old)).status==='unknown','old ledger immutable');assert((await fake()).calls.length===baseline+5,'only deliberate calls');await forget();
  });
  await test('reload while pending reconciles to saved result without replay or automatically starting next item',async()=>{
   await prepare();baseline=(await fake()).calls.length;await mode('hold');click('Запустить / продолжить batch',batch());await until(async()=>(await fake()).calls.length===baseline+1,'pending ML');
   const id=manifest().items[0].attempts[0].request_id;await load();assert(state(manifest().items[0])==='pending','pending recovered');
   click('Запустить / продолжить batch',batch());await until(()=>idle(),'pending blocked');assert((await fake()).calls.length===baseline+1,'no replay');
   await api('/__tests/release','POST',{});await until(async()=>(await api('/api/evaluation-requests/'+id)).status==='succeeded','Java saves disconnected result');
   await refresh();assert(state(manifest().items[0])==='succeeded'&&queued()===3,'GET reconciliation only');await runDone();assert((await fake()).calls.length===baseline+4,'remaining only');await forget();
  });
  await test('Java crash leaves unknown, retains manifest and originals, and does not rerun interrupted inference',async()=>{
   await prepare();baseline=(await fake()).calls.length;await mode('hold');click('Запустить / продолжить batch',batch());await until(async()=>(await fake()).calls.length===baseline+1,'accepted before crash');
   const id=manifest().items[0].attempts[0].request_id;assert((await api('/__tests/restart','POST',{})).originals_unchanged,'original snapshots survive');
   await load();assert(state(manifest().items[0])==='unknown','startup unknown');assert((await fake()).calls.length===baseline+1,'restart/reload do not infer');
   ack();await runDone();assert((await api('/api/evaluation-requests/'+id)).status==='unknown','interrupted UUID unchanged');
   ack();click('Новая попытка для этого диалога',batch().querySelector('.batch-item'));await until(()=>idle()&&state(manifest().items[0])==='succeeded','new deliberate attempt');await forget();
  });
  await test('v2 policy failures have no ML calls and remain failed after reload, with minimal private manifest',async()=>{
   await prepare(2);baseline=(await fake()).calls.length;await runDone();assert(manifest().items.every(i=>state(i)==='failed'),'policy failures shown');
   assert(manifest().items.every(i=>i.attempts[0].code==='PRIVACY_POLICY_UNCONFIGURED'),'safe policy code');await load();
   assert(manifest().items.every(i=>state(i)==='failed')&&(await fake()).calls.length===baseline,'no model calls or implicit retry');
   const stored=win.localStorage.getItem(KEY);assert(!/"(?:messages|transcript|answers|evidence|audio_url|diagnostics|criteria)"/.test(stored),'manifest contains no source/output/secrets');await forget();
  });
  await test('HTML-like group/IDs stay text, Java rejects unapproved own synthetic source before ML',async()=>{
   const source=await api('/api/conversations/SYNTHETIC%3Aen_public_na'),group='<img src=x onerror=alert(1)>';
   await api('/api/datasets/import','POST',{isSuccess:true,data:{dataset_group_id:group,total_records:1,records:[{conversation_id:'own-html-test',channel:source.channel,language:source.language,transcript:source.transcript}]}});
   await prepare(1,group);baseline=(await fake()).calls.length;await runDone();assert(!batch().querySelector('img'),'no DOM XSS');assert((await fake()).calls.length===baseline,'no fake provider call');await forget();
  });
  await test('corrupt local manifest blocks batch and is preserved for recovery',async()=>{
   win.localStorage.setItem(KEY,'{broken');baseline=(await fake()).calls.length;
   frame.src='/?batch-regression='+(++loads)+'#batch';await new Promise(r=>frame.addEventListener('load',r,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;
   await until(()=>batch()?.textContent.includes('Batch заблокирован'),'corrupt state blocked');
   assert(button('Запустить / продолжить batch',batch()).disabled&&button('Зафиксировать batch',batch()).disabled,'no unsafe fallback');assert(win.localStorage.getItem(KEY)==='{broken','corrupt data not discarded');assert((await fake()).calls.length===baseline,'no POST');
   win.localStorage.removeItem(KEY); // Only this disposable test origin's deliberately corrupt manifest.
  });
  status.textContent='PASS: '+report.children.length+' batch browser scenarios. Java + fake ML only; no Groq.';
 }catch(error){status.textContent='FAIL: '+error.message;status.className='fail';}
});
