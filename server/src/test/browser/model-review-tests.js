const frame=document.querySelector('#workspace'),report=document.querySelector('#checks'),status=document.querySelector('#status');
let doc,win,fixture,model,manual,original,checklistV1,initialCalls,setup;
const calls=[];
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
async function until(test,label){for(let i=0;i<375;i++){if(test())return;await new Promise(r=>setTimeout(r,40));}throw new Error('Timeout: '+label);}
const all=(selector,root=doc)=>[...root.querySelectorAll(selector)];
const idle=()=>doc.querySelector('#draft-status')?.textContent.startsWith('Несохранённых');
const nav=name=>{if(name==='batch')doc.querySelector('[data-view="results"]').click();doc.querySelector('[data-view="'+name+'"]').click();};
const workspace=()=>doc.querySelector('#evaluation-workspace');
function click(text,root=doc){const nodes=all('button',root).filter(n=>n.textContent.trim()===text);assert(nodes.length===1,'Unique button '+text);reveal(nodes[0]);nodes[0].click();}
function field(text,root=doc){const labels=all('label',root).filter(n=>n.querySelector('span')?.textContent===text);assert(labels.length===1,'Unique field '+text);return labels[0].querySelector('input,textarea,select');}
function reveal(node){const parents=[];for(let p=node.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open)parents.unshift(p);for(const p of parents)p.querySelector('summary').click();}
function fill(text,value,root=doc){const n=field(text,root);reveal(n);if(n.type==='checkbox')n.checked=value;else n.value=value;n.dispatchEvent(new win.Event(n.tagName==='SELECT'?'change':'input',{bubbles:true}));}
async function api(route,method='GET',body,code=200){
 const response=await fetch(route,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json();assert(response.status===code,'Harness '+route+' HTTP '+response.status+' expected '+code);return data;
}
const view=()=>api('/api/evaluations/'+model.id);
const resolutions=()=>calls.filter(c=>c.method==='POST'&&c.path.includes('/resolve'));
function immutable(value){assert(JSON.stringify([value.original_answers,value.original_score])===original,'Original answers/score unchanged');assert(value.origin==='model'&&value.checklist_version===1,'Origin and pinned v1 unchanged');}
async function test(name,run){await until(idle,'ready');await run();await until(idle,'settled');const li=document.createElement('li');li.textContent='PASS: '+name;report.append(li);}
async function load(){
 frame.src='/';await new Promise(r=>frame.addEventListener('load',r,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;
 await until(()=>doc.querySelector('#connection').dataset.state==='ok'&&doc.querySelector('#checklist-picker .notice').textContent.includes('Выбрано:'),'workspace ready');
 const nativeFetch=win.fetch.bind(win);
 win.fetch=async(path,options={})=>{const response=await nativeFetch(path,options);calls.push({path:String(path),method:options.method||'GET',status:response.status});return response;};
}
async function openResult(id){
 nav('results');click('Обновить оценки');
 await until(()=>all('.evaluation-list .list-row').some(n=>n.dataset.evaluationId===id),'result list');
 all('.evaluation-list .list-row').find(n=>n.dataset.evaluationId===id).click();
 await until(()=>all('.score-card').length>=1&&workspace().textContent.includes('Evaluation: '+id),'result detail');
}
async function appeal(criterion,comment){
 fill('Критерий апелляции',criterion,workspace());fill('Комментарий апелляции',comment,workspace());click('Отправить апелляцию',workspace());
 await until(()=>all('.appeal-card').some(n=>n.textContent.includes(comment))&&idle(),'appeal saved');
}
function pending(criterion){const card=all('.appeal-card').find(n=>n.querySelector('form')&&n.dataset.appealCriterion===criterion);assert(card,'Open appeal '+criterion);return card;}
async function resolved(criterion){await until(()=>!all('.appeal-card').some(n=>n.querySelector('form')&&n.dataset.appealCriterion===criterion)&&idle(),'resolved '+criterion);}
async function conversation(){
 nav('conversations');await until(()=>all('#conversation-workspace .list-row').length,'conversation list');
 const row=all('#conversation-workspace .list-row').find(n=>n.dataset.conversationId===fixture.conversation.id);assert(row,'Synthetic source');row.click();
 await until(()=>doc.querySelector('#conversation-workspace .conversation-detail [data-conversation-id]')?.dataset.conversationId===fixture.conversation.id,'source loaded');
}

document.querySelector('#run').addEventListener('click',async()=>{
 document.querySelector('#run').disabled=true;status.textContent='RUNNING';
 try{
  fixture=await api('/__tests/fixture.json');const initial=await api('/__tests/state');initialCalls=initial.calls;setup=initial.setup||'fake HTTP setup';
  model=(await api('/api/evaluations')).find(e=>e.origin==='model'&&e.checklist_version===1&&!e.appeals.length);
  assert(model,'Pre-existing model evaluation in isolated database');
  original=JSON.stringify([model.original_answers,model.original_score]);
  checklistV1=await api('/api/checklists/synthetic-local?version=1');await load();
  await test('open existing model evaluation and jump to exact evidence without inference',async()=>{
   await openResult(model.id);assert(all('.score-card .score-number').every(n=>parseFloat(n.textContent)===100),'Original/Final100 from Java');
   const details=doc.querySelector('.score-card [data-score-criterion="LOCAL_CLARITY"]');details.open=true;details.querySelector('.evidence-link').click();
   assert(doc.querySelector('#evaluation-workspace .turn.focused')?.dataset.messageId==='m0002','Exact message ID jump');
   assert(doc.querySelector('#evaluation-workspace .turn.focused .source-text').textContent===fixture.conversation.messages[1].text,'Original source text');immutable(await view());
  });
  await test('appeal/change: reject forged evidence; real CAS409 keeps draft and explicit retry scores60',async()=>{
   await appeal('LOCAL_CLARITY','T14 clarity appeal');let card=pending('LOCAL_CLARITY');
   fill('Решение','change',card);fill('Причина решения','T14 retained reason <img src=x onerror=alert(1)>',card);fill('Ответ','level:1',card);
   const quote=field('Точная цитата',card).value,before=resolutions().length;
   fill('Точная цитата','NOT IN SOURCE',card);click('Сохранить решение',card);
   await until(()=>card.querySelector('.notice[data-state="error"]')&&idle(),'invalid evidence');
   assert(resolutions().length===before,'Invalid quote blocked before POST');fill('Точная цитата',quote,card);
   const state=await view(),a=state.appeals.find(a=>a.status==='open');
   const invalid={...state.final_answers.find(a=>a.criterion_id==='LOCAL_CLARITY'),evidence:[{message_id:'m9999',quote}]};
   const failure=await api('/api/appeals/'+a.id+'/resolve?expected_revision=1','POST',{decision:'change',reason:'Synthetic validation probe',replacement:invalid},422);
   assert(failure.detail.code==='INVALID_INPUT'&&JSON.stringify(await view())===JSON.stringify(state),'Java rejects invalid evidence atomically');
   await api('/api/evaluations/'+model.id+'/appeals','POST',{criterion_id:'LOCAL_GREETING',comment:'T14 concurrent reviewer'},201);
   click('Сохранить решение',card);
   await until(()=>workspace().querySelector(':scope > .notice').textContent.includes('Конфликт')&&idle(),'real409');
   assert(resolutions().length===before+1&&resolutions().at(-1).status===409,'Exactly one rejected POST, no automatic retry');
   card=pending('LOCAL_CLARITY');assert(field('Причина решения',card).value.includes('T14 retained reason'),'Reason draft retained');
   assert(field('Ответ',card).value==='level:1'&&field('Точная цитата',card).value===quote,'Answer/evidence draft retained');
   click('Сохранить решение',card);await resolved('LOCAL_CLARITY');
   const final=await view();immutable(final);assert(final.review_revision===3&&final.final_score.overall_score===60,'Revision3 final60');
   assert(resolutions().at(-1).path.endsWith('expected_revision=2'),'Explicit retry uses freshly read revision');
   assert(!workspace().querySelector('img'),'Reviewer reason is literal text');
   const replacement=all('.appeal-card').find(n=>n.textContent.includes('T14 clarity appeal')).querySelector('.evidence-link');replacement.click();
   assert(workspace().querySelector('.turn.focused')?.dataset.messageId==='m0002','Replacement evidence jump');
  });
  await test('confirm and repeated critical-flag decisions preserve numeric score, N/A and full history',async()=>{
   let card=pending('LOCAL_GREETING');fill('Причина решения','T14 confirm current greeting',card);click('Сохранить решение',card);await resolved('LOCAL_GREETING');
   for(const value of ['yes','no']){
    await appeal('LOCAL_GROSS','T14 synthetic flag '+value);card=pending('LOCAL_GROSS');fill('Решение','change',card);
    fill('Причина решения','Structural workflow test '+value+'; not a semantic quality label.',card);fill('Ответ',value,card);click('Сохранить решение',card);await resolved('LOCAL_GROSS');
    const state=await view();immutable(state);assert(state.final_score.critical_violation===(value==='yes'),'Critical flag toggled');
    assert(state.final_score.overall_score===60&&state.final_score.applicable_weight===75,'Weightless flag and N/A denominator');
    assert(JSON.stringify(state.final_score.critical_criterion_ids)===JSON.stringify(value==='yes'?['LOCAL_GROSS']:[]),'Critical IDs');
   }
   const state=await view();assert(state.review_revision===8&&state.appeals.length===4&&state.review_status==='reviewed','Complete history revision8');
   assert(JSON.stringify(state.appeals.map(a=>[a.created_revision,a.resolved_revision]))==='[[1,3],[2,4],[5,6],[7,8]]','Decision order recorded');
   assert(state.appeals[1].decision==='confirm'&&state.appeals[1].replacement===null,'Confirm preserved');
   assert(state.appeals[2].replacement.answer==='yes'&&state.appeals[3].replacement.answer==='no','Re-appeal keeps earlier decision');
   assert(all('.appeal-card').length===4&&!all('.appeal-card form').length,'All decisions visible in UI');
  });
  await test('UI appends v2 with arbitrary extra criterion; historical v1 remains byte-equivalent JSON',async()=>{
   nav('checklists');fill('Чек-лист','synthetic-local');
   await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('synthetic-local / v1.'),'v1 selected');
   const editor=()=>doc.querySelector('#checklist-editor');click('Добавить критерий',editor());
   const c=editor().querySelector('[data-criterion-index="4"]');assert(c,'Additional criterion editor');
   fill('ID критерия','JURY_EXTRA_42',c);fill('Название критерия','Opening time <script>alert(1)</script>',c);
   fill('Инструкция','Check whether the reply states opening time.',c);fill('Вес','25',c);click('Сохранить новую версию',editor());
   await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('synthetic-local / v2.')&&idle(),'v2 saved');
   const v2=await api('/api/checklists/synthetic-local');assert(v2.version===2&&v2.criteria.length===5&&v2.criteria[4].id==='JURY_EXTRA_42','Java persisted arbitrary v2');
   assert(JSON.stringify(await api('/api/checklists/synthetic-local?version=1'))===JSON.stringify(checklistV1),'Historical v1 intact');
   assert(!editor().querySelector('script'),'Criterion title rendered safely');immutable(await view());
  });
  await test('manual v2 answers persist with score75 while model v1 keeps original100/final60',async()=>{
   await conversation();await until(()=>all('#manual-workspace .answer-card').length===5,'v2 manual composer');
   for(const [id,value,message] of [['LOCAL_GREETING','yes','m0002'],['LOCAL_IDENTITY','na','m0001'],['LOCAL_CLARITY','level:2','m0002'],['LOCAL_GROSS','no','m0002'],['JURY_EXTRA_42','no','m0002']]){
    const card=doc.querySelector('#manual-workspace [data-criterion-id="'+id+'"]');fill('Ответ',value,card);
    fill('Обоснование','Synthetic manual v2 workflow, not a quality annotation.',card);click('Добавить доказательство',card);fill('Сообщение',message,card);click('Взять текст сообщения',card);
   }
   click('Сохранить ручную оценку');await until(()=>workspace().textContent.includes('/ v2')&&all('.score-card').length>=1&&idle(),'manual v2 result');
   manual=(await api('/api/evaluations')).find(e=>e.origin==='manual'&&e.checklist_key==='synthetic-local'&&e.checklist_version===2);
   assert(manual?.original_score.overall_score===75&&manual.original_answers.length===5,'Java v2 score75 including arbitrary criterion');
   assert(all('.score-card .score-number').every(n=>parseFloat(n.textContent)===75),'UI displays Java score75');
   const old=await view();immutable(old);assert(old.final_score.overall_score===60&&old.final_answers.length===4,'v1 remains pinned');
   await openResult(model.id);assert(field('Критерий апелляции',workspace()).querySelectorAll('option').length===5,'v1 review selector excludes v2 criterion');
  });
  await test('dynamic v2 AI is honestly policy-blocked before any fake or real ML request',async()=>{
   await conversation();const panel=doc.querySelector('[data-auto-workspace]');click('Оценить с ИИ',panel);
   await until(()=>panel.querySelector('.notice[data-state="error"]')&&idle(),'policy rejection');
   assert(all('button',panel).find(n=>n.textContent==='Оценить с ИИ').disabled,'Readiness blocks unapproved version');
   const requestId=crypto.randomUUID();const denied=await api('/api/evaluations/auto','POST',{request_id:requestId,conversation_id:fixture.conversation.id,checklist_key:'synthetic-local',checklist_version:2},503);assert(denied.detail.code==='PRIVACY_POLICY_UNCONFIGURED','Server independently rejects bypass');
   assert((await api('/api/evaluation-requests/'+requestId,'GET',undefined,404)).detail.code==='NOT_FOUND','No inference ledger entry');
   assert((await api('/__tests/state')).calls===initialCalls,'No additional ML POST in entire T14 workflow');
  });
  await test('actual Java restart and browser reload preserve model review history, v1/v2 and manual v2',async()=>{
   const before=await view(),restart=await api('/__tests/restart','POST',{});assert(restart.originals_unchanged,'SQLite original rows unchanged across restart');
   await load();await openResult(model.id);assert(JSON.stringify(await view())===JSON.stringify(before),'Model history/revisions/final survive JVM restart');
   assert(all('.appeal-card').length===4,'History reloaded in UI');immutable(await view());
   assert(JSON.stringify(await api('/api/checklists/synthetic-local?version=1'))===JSON.stringify(checklistV1),'v1 survives restart');
   assert((await api('/api/checklists/synthetic-local')).version===2,'Latest v2 survives restart');
   assert(JSON.stringify(await api('/api/evaluations/'+manual.id))===JSON.stringify(manual),'Manual v2 survives restart');
   await openResult(manual.id);assert(all('.score-card .score-number').every(n=>parseFloat(n.textContent)===75),'Manual result reloaded in UI');
   assert((await api('/__tests/state')).calls===initialCalls,'Reload and restart never infer');
  });
  status.textContent='PASS: '+report.children.length+' T14 browser scenarios ('+setup+'). No new live calls; dynamic live AI remains BLOCKED.';
 }catch(error){status.textContent='FAIL: '+error.message;status.className='fail';}
});
