const frame=document.querySelector('#workspace'),report=document.querySelector('#checks'),output=document.querySelector('#status');
let doc,win,selection,source,first,second;
const assert=(ok,label)=>{if(!ok)throw new Error(label);};
const all=(selector,root=doc)=>[...root.querySelectorAll(selector)];
const panel=()=>doc.querySelector('[data-auto-workspace]');
const idle=()=>doc.querySelector('#draft-status').textContent.startsWith('Несохранённых');
async function until(check,label){for(let i=0;i<1000;i++){if(await check())return;await new Promise(r=>setTimeout(r,40));}throw new Error(label);}
async function api(path){const r=await fetch(path);assert(r.ok,'Local API read failed');return r.json();}
function click(text,root=doc){const n=all('button',root).filter(x=>x.textContent.trim()===text);assert(n.length===1,'Unique action: '+text);n[0].click();}
function field(text,root=doc){const n=all('label',root).filter(x=>x.querySelector('span')?.textContent===text);assert(n.length===1,'Unique field: '+text);return n[0].querySelector('input,select,textarea');}
function fill(text,value,root=doc){const n=field(text,root);if(n.type==='checkbox')n.checked=value;else n.value=value;n.dispatchEvent(new win.Event(n.tagName==='SELECT'?'change':'input',{bubbles:true}));}
const nav=name=>doc.querySelector('[data-view="'+name+'"]').click();
const singleConsent='Подтверждаю передачу этого диалога и выбранной версии чек-листа в Groq GPT-OSS 20B';
const batchConsent='Подтверждаю передачу диалогов этого пакета и закреплённой версии чек-листа в Groq GPT-OSS 20B';
const manifest=()=>JSON.parse(win.localStorage.getItem('cqa:batch:v1'));
async function load(){frame.src='/';await new Promise(r=>frame.addEventListener('load',r,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('Выбрано:'),'Workspace loaded');}
async function select(){nav('conversations');await until(()=>all('#conversation-workspace .list-row').length===selection.total,'Existing source list');all('#conversation-workspace .list-row').find(n=>n.querySelector('strong').textContent===selection.selected[0]).click();await until(()=>panel()?.dataset.aiState==='ready','Both admissions ready');}
async function test(name,run){await run();const li=document.createElement('li');li.textContent='PASS: '+name;report.append(li);}
document.querySelector('#run').addEventListener('click',async()=>{
 document.querySelector('#run').disabled=true;output.textContent='RUNNING';
 try{
  selection=await api('/__tests/state');await load();
  await test('UI JSON upload / exact archived bytes / complete group and source fields',async()=>{
   assert((await api('/api/conversations')).length===0&&!selection.archive_verified,'Fresh browser DB and no source archive');
   nav('datasets');const response=await fetch('/__tests/source');assert(response.ok,'Private local source');
   const bytes=await response.arrayBuffer(), original=JSON.parse(new TextDecoder().decode(bytes));
   const transfer=new win.DataTransfer();transfer.items.add(new win.File([bytes],'private-source.json',{type:'application/json'}));
   doc.querySelector('#dataset-file').files=transfer.files;click('Импортировать JSON',doc.querySelector('#upload-form'));
   await until(()=>doc.querySelector('#conversation-count').textContent===String(selection.total)&&idle(),'UI upload complete');
   assert((await api('/__tests/state')).archive_verified,'Exact original bytes, not reconstructed JSON');
   const rows=await api('/api/conversations');assert(rows.length===selection.total,'All records imported');
   for(const r of original.data.records){const saved=await api('/api/conversations/'+encodeURIComponent(selection.group+':'+r.conversation_id));
    assert(saved.dataset_group_id===selection.group&&saved.language===r.language&&saved.channel===r.channel,'Source identity');
    assert(saved.transcript.length===r.transcript.length&&saved.transcript.every((t,i)=>['timestamp','speaker','text'].every(k=>t[k]===r.transcript[i][k]))&&saved.audio_url===r.audio_url,'Exact source fields');
    assert(saved.messages.every((m,i)=>m.id==='m'+String(i+1).padStart(4,'0')),'Positional IDs');}
  });
  await test('five calls / exact timestamps / audio controls / explicit AI denial without audio requests',async()=>{
   nav('conversations');await until(()=>all('#conversation-workspace .list-row').length===selection.total,'List after upload');
   const calls=(await api('/api/conversations')).filter(r=>r.channel==='voice call');assert(calls.length===5,'Five source calls');
   const before=(await api('/__tests/state')).ml_posts;
   for(const row of calls){all('#conversation-workspace .list-row').find(n=>n.querySelector('strong').textContent===row.id).click();
    await until(()=>doc.querySelector('#conversation-workspace .audio-box a')&&panel()?.dataset.aiState==='blocked','Call and policy refusal');
    const saved=await api('/api/conversations/'+encodeURIComponent(row.id));
    const turns=all('#conversation-workspace .turn');assert(turns.length===saved.messages.length,'All call turns');
    for(let i=0;i<turns.length;i++){assert(turns[i].dataset.messageId===saved.messages[i].id&&turns[i].textContent.includes(saved.messages[i].timestamp),'Original call timestamp');}
    const audio=doc.querySelector('#conversation-workspace audio');assert(audio.preload==='none'&&!audio.getAttribute('src'),'Audio is not sent or loaded');
    assert(doc.querySelector('#conversation-workspace .audio-box a').getAttribute('href')===saved.audio_url,'Source audio link preserved');
   }
   assert((await api('/__tests/state')).ml_posts===before,'No ML requests for calls');
  });
  await select();source=await api('/api/conversations/'+encodeURIComponent(selection.selected[0]));
  await test('existing DEV / both admissions / no UUID or POST until rubric confirmation',async()=>{
   assert(!field(singleConsent,panel()).checked,'Consent is not implicit');
   const before=(await api('/__tests/state')).ml_posts;click('Оценить с ИИ',panel());
   assert(field('Идентификатор запроса',panel()).value==='','No UUID while unconfirmed');assert((await api('/__tests/state')).ml_posts===before,'No ML POST');
   fill(singleConsent,true,panel());click('Оценить с ИИ',panel());
   await until(()=>panel()?.dataset.requestState==='succeeded'&&idle(),'Saved v1 from actual Python HTTP / offline provider');
   const ledger=await api('/api/evaluation-requests/'+field('Идентификатор запроса',panel()).value);first=await api('/api/evaluations/'+ledger.evaluation_id);
   assert(first.checklist_version===1&&first.original_answers.length===8&&first.origin==='model','Complete v1 output');
   assert(first.original_answers.every(a=>a.explanation.startsWith('OFFLINE TEST ONLY')),'Explicit offline labels');
  });
  await test('eight answers / exact evidence and NA / Java scoring / separate critical flag',async()=>{
   const rubric=await api('/api/checklists/chat-quality?version=1');assert(rubric.criteria.length===8,'C01-C08');
   const expected=[['C01','binary',10,false,[]],['C02','binary',15,true,[]],['C03','binary',20,true,[]],
    ['C04','scale',20,true,[0,5,10,15,20]],['C05','binary',15,false,[]],['C06','scale',15,false,[0,4,7,10]],
    ['C07','binary',5,true,[]],['C08','flag',0,false,[]]];
   assert(JSON.stringify(rubric.criteria.map(c=>[c.id,c.kind,c.weight,c.allow_na,c.levels.map(l=>l.value)]))===JSON.stringify(expected),'User-supplied official C01-C08 configuration');
   for(const a of first.original_answers){assert(a.evidence.every(e=>source.messages.find(m=>m.id===e.message_id)?.text.includes(e.quote)),'Exact evidence');}
   assert(first.original_answers.some(a=>a.answer==='na'),'Configured NA');assert(first.original_score.overall_score===0,'Java structural test score');
   assert(first.original_score.applicable_weight===40&&first.original_score.max_score===100,'NA weight exclusion and normalization');
   assert(first.original_score.criteria.find(c=>c.criterion_id==='C01').effective_weight===25,'Effective C01 weight after NA');
   assert(first.original_answers.find(a=>a.criterion_id==='C08').answer==='no','Separate violation flag');
   doc.querySelector('.evidence-link').click();assert(doc.querySelector('#evaluation-workspace .turn.focused'),'Evidence jump');
  });
  await test('review changes final and retains immutable original model snapshot',async()=>{
   const root=doc.querySelector('#evaluation-workspace');fill('Критерий апелляции','C01',root);fill('Комментарий апелляции','OFFLINE TEST ONLY: review.',root);click('Отправить апелляцию',root);
   await until(()=>root.querySelector('.appeal-card form')&&idle(),'Appeal saved');const card=root.querySelector('.appeal-card');
   fill('Решение','change',card);fill('Причина решения','OFFLINE TEST ONLY: scoring check.',card);fill('Ответ','yes',card);click('Сохранить решение',card);
   await until(()=>!root.querySelector('.appeal-card form')&&idle(),'Review persisted');const view=await api('/api/evaluations/'+first.id);
   assert(JSON.stringify(view.original_answers)===JSON.stringify(first.original_answers),'Original answers immutable');
   assert(view.original_score.overall_score===0&&view.final_score.overall_score===25,'Final alone changes through Java scoring');first=view;
  });
  await test('replace criterion through UI / v2 requires fresh confirmation / both pinned histories',async()=>{
   nav('checklists');const card=doc.querySelector('[data-criterion-index="0"]');fill('ID критерия','DYNAMIC_REVIEW_ITEM',card);
   fill('Название критерия','Новый критерий проверки',card);fill('Инструкция','Проверьте, уточнил ли оператор результат обращения. Обоснуйте вывод цитатой. OFFLINE TEST: quality is not measured.',card);
   click('Сохранить новую версию');await until(()=>all('button').some(n=>n.textContent==='Оценить по новой версии')&&idle(),'New version saved');click('Оценить по новой версии');
   await until(()=>panel()?.dataset.aiState==='ready','Dynamic v2 admitted without grant edits');assert(!field(singleConsent,panel()).checked,'New rubric is not preconfirmed');
   const before=(await api('/__tests/state')).ml_posts;click('Оценить с ИИ',panel());assert((await api('/__tests/state')).ml_posts===before,'No unconfirmed v2 POST');
   fill(singleConsent,true,panel());click('Оценить с ИИ',panel());await until(()=>panel()?.dataset.requestState==='succeeded'&&idle(),'v2 saved');
   const ledger=await api('/api/evaluation-requests/'+field('Идентификатор запроса',panel()).value);second=await api('/api/evaluations/'+ledger.evaluation_id);
   assert(second.checklist_version===2&&second.original_answers.some(a=>a.criterion_id==='DYNAMIC_REVIEW_ITEM'),'New criterion returned');
   assert(JSON.stringify(await api('/api/evaluations/'+first.id))===JSON.stringify(first),'v1 remains unchanged');
  });
  await test('batch pins v2 / confirmation / pause-reload-resume / exact approved membership',async()=>{
   nav('batch');const root=doc.querySelector('#batch-workspace');click('Обновить группы',root);await until(()=>all('select option',root).some(n=>n.value===selection.group),'DEV group');
   fill('Группа для оценки',selection.group,root);click('Подготовить пакет',root);await until(()=>manifest()&&idle(),'Pinned batch');
   assert(manifest().checklist_version==='2'&&!field(batchConsent,root).checked,'Pinned v2 and fresh consent');
   const before=(await api('/__tests/state')).ml_posts;click('Запустить / продолжить',root);assert((await api('/__tests/state')).ml_posts===before,'No unconfirmed batch');
   fill(batchConsent,true,root);click('Запустить / продолжить',root);await until(()=>manifest().items.some(i=>i.attempts.length),'First durable intent');click('Пауза после текущего диалога',root);await until(idle,'Pause settled');
   const paused=(await api('/__tests/state')).ml_posts;await load();nav('batch');const reloaded=doc.querySelector('#batch-workspace');
   // Reload reconciliation is a background GET: drafts.pending alone does not mean it has finished.
   await until(()=>idle()&&all('button',reloaded).some(n=>n.textContent==='Проверить статусы'&&!n.disabled),'Reload reconciliation');
   assert((await api('/__tests/state')).ml_posts===paused,'Reload is GET only');assert(!field(batchConsent,reloaded).checked,'Reload loses consent');
   fill(batchConsent,true,reloaded);click('Запустить / продолжить',reloaded);
   await until(()=>manifest().items.every(i=>i.blocked_code||i.attempts.at(-1)?.state==='succeeded')&&idle(),'Batch accounted for every source');
   const m=manifest();assert(m.items.length===selection.total,'Full frozen membership');
   assert(m.items.filter(i=>i.attempts.at(-1)?.state==='succeeded').length===selection.selected.length,'Exactly selected chats');
   assert(m.items.filter(i=>i.blocked_code&&i.attempts.length===0).length===selection.total-selection.selected.length,'Other chats and all calls denied without UUID');
   assert((await api('/__tests/state')).ml_posts===before+selection.selected.length,'One POST per allowed item, no replays');
   assert((await api('/__tests/state')).groq_calls===0,'External networking forbidden');
  });
  await test('batch invalid ML output / failed ledger / pause prevents another POST',async()=>{
   const root=doc.querySelector('#batch-workspace'), previous=win.confirm;win.confirm=()=>true;
   try{click('Убрать завершённый пакет',root);}finally{win.confirm=previous;}
   await until(()=>!manifest()&&idle(),'Completed manifest removed without deleting Java results');
   const fault=await fetch('/__tests/fault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'invalid'})});assert(fault.ok,'Local fault dependency');
   fill('Группа для оценки',selection.group,root); // Reload restores the manifest, not the next batch's selector.
   click('Подготовить пакет',root);await until(()=>manifest()&&idle(),'New explicit batch');fill(batchConsent,true,root);
   const before=(await api('/__tests/state')).ml_posts;click('Запустить / продолжить',root);
   await until(()=>manifest().items.some(i=>i.attempts.length),'Durable error intent');click('Пауза после текущего диалога',root);
   await until(()=>manifest().items.some(i=>i.attempts.at(-1)?.state==='failed')&&idle(),'Failed response persisted');
   const attempt=manifest().items.find(i=>i.attempts.at(-1)?.state==='failed').attempts.at(-1);
   assert((await api('/api/evaluation-requests/'+attempt.request_id)).status==='failed','Failed Java ledger');
   assert((await api('/__tests/state')).ml_posts===before+1,'Only one Java-to-ML POST despite provider validation attempts');
  });
  await test('batch timeout / unknown ledger / reload and restart never replay inference',async()=>{
   const fault=await fetch('/__tests/fault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'slow'})});assert(fault.ok,'Local timeout dependency');
   let root=doc.querySelector('#batch-workspace');const before=(await api('/__tests/state')).ml_posts;
   fill(batchConsent,true,root);click('Запустить / продолжить',root);
   await until(()=>manifest().items.some(i=>i.attempts.at(-1)?.state==='unknown')&&idle(),'Unknown outcome stops batch');
   const attempt=manifest().items.find(i=>i.attempts.at(-1)?.state==='unknown').attempts.at(-1);
   assert((await api('/api/evaluation-requests/'+attempt.request_id)).status==='unknown','Unknown Java ledger');
   assert((await api('/__tests/state')).ml_posts===before+1,'One timeout POST');
   const restored=await fetch('/__tests/fault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'normal'})});assert(restored.ok,'Restore normal deadline and restart');
   await load();nav('batch');root=doc.querySelector('#batch-workspace');
   await until(()=>idle()&&all('button',root).some(n=>n.textContent==='Проверить статусы'&&!n.disabled),'Unknown reconciliation');
   assert(manifest().items.some(i=>i.attempts.at(-1)?.state==='unknown'),'Unknown retained');
   assert((await api('/__tests/state')).ml_posts===before+1,'No reload/restart POST');
   assert(JSON.stringify(await api('/api/evaluations/'+first.id))===JSON.stringify(first),'Original/review/v1 survive restart');
   assert(JSON.stringify(await api('/api/evaluations/'+second.id))===JSON.stringify(second),'v2 survives restart');
  });
  output.textContent='PASS: '+report.children.length+' private DEV Java/Python admission browser scenarios. OFFLINE provider only; Groq=0.';
 }catch(error){output.textContent='FAIL: '+error.message;}
});
