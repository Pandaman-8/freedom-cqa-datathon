import {parse, stringify} from '/js/json.js';
const frame=document.querySelector('#workspace'), report=document.querySelector('#checks'), status=document.querySelector('#status');
let doc, win, fixture, key, saved, originalScore; const calls=[];
const assert=(condition,message)=>{if(!condition)throw new Error(message);};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(test,label){for(let i=0;i<200;i++){if(test())return;await sleep(40);}throw new Error('Timeout: '+label);}
const all=(selector,root=doc)=>[...root.querySelectorAll(selector)];
const idle=()=>doc.querySelector('#draft-status')?.textContent.startsWith('Несохранённых');
function named(label,root=doc){const rows=all('label',root).filter(l=>(l.querySelector('span')?.textContent??l.firstChild?.textContent??'').trim()===label);assert(rows.length===1,'Unique label: '+label);return rows[0].querySelector('input,select,textarea');}
function fill(label,value,root=doc){const input=named(label,root);if(input.type==='checkbox')input.checked=value;else input.value=value;input.dispatchEvent(new win.Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));}
function click(text,root=doc){const buttons=all('button',root).filter(b=>b.textContent.trim()===text);assert(buttons.length===1,'Unique button: '+text);buttons[0].click();}
const nav=name=>doc.querySelector('[data-view="'+name+'"]').click();
function source(id){const button=all('.list-row',doc.querySelector('#conversation-workspace')).find(b=>b.querySelector('strong').textContent===id);assert(button,'Conversation listed');button.click();}
async function selectedSource(id){await until(()=>doc.querySelector('#conversation-workspace .conversation-grid > :last-child h3')?.textContent===id,'selected conversation '+id);}
async function api(path,method='GET',body){const response=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:stringify(body)});const data=parse(await response.text());assert(response.ok,'Harness HTTP '+response.status);return data;}
async function test(name,fn){await until(idle,'ready before '+name);await fn();await until(idle,'settled after '+name);const li=document.createElement('li');li.textContent='PASS: '+name;report.append(li);}
async function checklistVersion(version){fill('Version (пусто = latest)',version);click('Открыть версию');await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('/ v'+version+'.'),'checklist version '+version);}
function answer(id){const card=all('#manual-workspace .answer-card').find(c=>c.dataset.criterionId===id);assert(card,'criterion '+id);return card;}
async function appeal(criterion,comment){const root=doc.querySelector('#evaluation-workspace');fill('Критерий апелляции',criterion,root);fill('Комментарий апелляции',comment,root);click('Отправить апелляцию',root);await until(()=>all('.appeal-card',root).some(c=>c.textContent.includes(comment))&&idle(),'appeal saved');}
function pendingReview(criterion){const card=all('.appeal-card').find(c=>c.querySelector('form')&&c.querySelector('.badge:nth-child(2)')?.textContent===criterion);assert(card,'pending review '+criterion);return card;}

document.querySelector('#run').addEventListener('click',async()=>{
 document.querySelector('#run').disabled=true;status.textContent='RUNNING';report.replaceChildren();
 try{
  fixture=await api('/__tests/fixture.json');
  frame.src='/';await new Promise(resolve=>frame.addEventListener('load',resolve,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;
  await until(()=>doc.querySelector('#connection').dataset.state==='ok'&&doc.querySelector('#checklist-picker .notice').textContent.includes('Выбрано:'),'initial workspace');
  const nativeFetch=win.fetch.bind(win);
  win.fetch=async(path,options={})=>{calls.push({path:String(path),method:options.method||'GET',body:options.body});return nativeFetch(path,options);};
  await test('real overview counts, RU/KZ/EN filters, exact source text/roles/timestamps/IDs, no DOM XSS',async()=>{
   nav('conversations');await until(()=>all('#conversation-workspace .list-row').length>=3,'conversation list');fill('Группа','UI-SYNTHETIC',doc.querySelector('#conversation-workspace'));assert(all('#conversation-workspace .list-row').length===3,'group filter');
   fill('Язык','KZ',doc.querySelector('#conversation-workspace'));assert(all('#conversation-workspace .list-row').length===1,'language filter');
   fill('Язык','',doc.querySelector('#conversation-workspace'));fill('Поиск по ID','RU',doc.querySelector('#conversation-workspace'));assert(all('#conversation-workspace .list-row').length===1,'search');
   fill('Поиск по ID','',doc.querySelector('#conversation-workspace'));source('UI-SYNTHETIC:RU');await selectedSource('UI-SYNTHETIC:RU');
   assert(all('#conversation-workspace .turn').length===5,'all turns');assert(all('#conversation-workspace .turn-meta').every(n=>n.textContent.includes('00:01')),'repeated times preserved');
   assert(doc.querySelector('#conversation-workspace [data-message-id="m0003"] .source-text').textContent===fixture.quote,'exact Unicode/newline');
   assert(doc.querySelector('#conversation-workspace [data-message-id="m0001"] .source-text').textContent==='<img src=x onerror=alert(1)>','literal hostile text');
   assert(all('#conversation-workspace img, #conversation-workspace script').length===0,'no executable source nodes');
  });
  await test('conversation race ignores delayed A after B; draft remains scoped to its conversation',async()=>{
   let release,started=false;
   const before=win.fetch;
   win.fetch=async(path,options={})=>{
    if(String(path)==='/api/conversations/UI-SYNTHETIC%3ARU') {started=true;const response=await nativeFetch(path,{...options,signal:undefined});await new Promise(resolve=>release=resolve);return response;}
    return before(path,options);
   };
   source('UI-SYNTHETIC:RU');await until(()=>started&&release,'delayed A');source('UI-SYNTHETIC:KZ');await selectedSource('UI-SYNTHETIC:KZ');release();await sleep(100);
   assert(doc.querySelector('#conversation-workspace .conversation-grid > :last-child h3').textContent==='UI-SYNTHETIC:KZ','late A discarded');win.fetch=before;
   source('UI-SYNTHETIC:RU');await selectedSource('UI-SYNTHETIC:RU');
  });
  await test('historical checklist selection and version race; context drafts are not overwritten',async()=>{
   fill('Checklist key','ui-synthetic');await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('ui-synthetic / v2.'),'custom checklist');
   let release;const before=win.fetch;
   win.fetch=async(path,options={})=>{if(String(path)==='/api/checklists/ui-synthetic?version=1'){const response=await nativeFetch(path,{...options,signal:undefined});await new Promise(resolve=>release=resolve);return response;}return before(path,options);};
   fill('Version (пусто = latest)','1');click('Открыть версию');await until(()=>release,'delayed checklist');await checklistVersion('2');release();await sleep(100);
   assert(doc.querySelector('#checklist-picker .notice').textContent.includes('/ v2.'),'late v1 discarded');win.fetch=before;await checklistVersion('1');
   fill('Обоснование','Keep draft A',answer('WELCOME_X'));source('UI-SYNTHETIC:KZ');await selectedSource('UI-SYNTHETIC:KZ');assert(named('Обоснование',answer('WELCOME_X')).value==='','no A draft leakage');
   fill('Обоснование','Keep draft B',answer('WELCOME_X'));source('UI-SYNTHETIC:RU');await selectedSource('UI-SYNTHETIC:RU');assert(named('Обоснование',answer('WELCOME_X')).value==='Keep draft A','draft A retained');
   nav('overview');nav('conversations');assert(named('Обоснование',answer('WELCOME_X')).value==='Keep draft A','tab preserves draft');
  });
  await test('manual validation, exact evidence, duplicate POST prevention, persisted70/N-A/critical/raw10.5',async()=>{
   for(const [id,value] of [['WELCOME_X','na'],['CLARITY_X','level:1'],['RISK_X','yes']]){
    fill('Ответ',value,answer(id));fill('Обоснование','Synthetic explanation <img src=x onerror=alert(1)>',answer(id));click('Добавить evidence',answer(id));fill('Message ID','m0003',answer(id));click('Взять текст сообщения',answer(id));
   }
   fill('Точная цитата','NOT IN SOURCE',answer('WELCOME_X'));click('Сохранить ручную оценку');await until(()=>doc.querySelector('#manual-workspace .notice[data-state="error"]'),'local validation');
   assert(!calls.some(c=>c.path==='/api/evaluations/manual'&&c.method==='POST'),'invalid quote not posted');
   click('Взять текст сообщения',answer('WELCOME_X'));const form=doc.querySelector('#manual-workspace form');form.requestSubmit();form.requestSubmit();
   await until(()=>all('#evaluation-workspace .score-card').length===2&&idle(),'saved results');
   assert(calls.filter(c=>c.path==='/api/evaluations/manual'&&c.method==='POST').length===1,'exactly one manual POST');
   const rows=await api('/api/evaluations?conversation_id=UI-SYNTHETIC%3ARU');saved=rows.find(e=>e.original_answers[0].explanation.includes('<img'));
   assert(saved&&String(saved.original_score.overall_score)==='70.00','real Java snapshot70');originalScore=stringify(saved.original_score);
   assert(String(saved.original_score.criteria[1].raw_points)==='10.50','raw10.5');assert(saved.original_score.critical_violation,'independent critical flag');
   assert(all('#evaluation-workspace img').length===0,'explanation safe');
  });
  await test('evidence jumps to exact message_id with duplicate timestamps',async()=>{
   const original=doc.querySelector('.score-card');const detail=original.querySelector('details');detail.open=true;detail.querySelector('.evidence-link').click();
   assert(doc.querySelector('#evaluation-workspace .turn.focused')?.dataset.messageId==='m0003','exact message focused');
   assert(doc.querySelector('#evaluation-workspace .turn.focused .source-text').textContent===fixture.quote,'exact source retained');
  });
  await test('appeal confirm uses current expected_revision',async()=>{
   await appeal('WELCOME_X','Browser confirm appeal');let card=pendingReview('WELCOME_X');fill('Причина решения','Browser confirmed.',card);click('Сохранить решение',card);
   await until(()=>doc.querySelector('#evaluation-workspace').textContent.includes('Browser confirmed.')&&!all('.appeal-card form').length,'confirmed');
   const view=await api('/api/evaluations/'+saved.id);assert(String(view.review_revision)==='2','revision2');assert(stringify(view.original_score)===originalScore,'original unchanged');
   assert(calls.some(c=>c.path.includes('/resolve?expected_revision=1')),'CAS1 sent');
  });
  await test('review conflict409 reloads without retry, preserves draft, explicit change recomputes final only',async()=>{
   await appeal('CLARITY_X','Browser change appeal');let card=pendingReview('CLARITY_X');fill('Решение','change',card);fill('Причина решения','Retain conflict reason',card);fill('Ответ','level:0',card);
   await api('/api/evaluations/'+saved.id+'/appeals','POST',{criterion_id:'RISK_X',comment:'Concurrent synthetic appeal'});
   const before=calls.filter(c=>c.path.includes('/resolve')).length;click('Сохранить решение',card);
   await until(()=>doc.querySelector('#evaluation-workspace > .notice').textContent.includes('REVIEW_CONFLICT'),'conflict displayed');await until(idle,'mutation settled');
   card=pendingReview('CLARITY_X');assert(named('Причина решения',card).value==='Retain conflict reason','reason retained');assert(named('Ответ',card).value==='level:0','replacement retained');
   assert(calls.filter(c=>c.path.includes('/resolve')).length===before+1,'no automatic replay');click('Сохранить решение',card);
   await until(()=>!all('.appeal-card form').some(f=>f.querySelector('h3')?.textContent==='Решение по CLARITY_X'),'change saved');
   const view=await api('/api/evaluations/'+saved.id);assert(String(view.final_score.overall_score)==='0.00','final0');assert(stringify(view.original_score)===originalScore,'original70 immutable');
  });
  await test('unknown mutation outcome keeps draft and blocks repeat across context switches',async()=>{
   nav('conversations');source('UI-SYNTHETIC:RU');await selectedSource('UI-SYNTHETIC:RU');
   let attempts=0;const before=win.fetch;
   win.fetch=async(path,options={})=>{if(String(path)==='/api/evaluations/manual'&&options.method==='POST'){attempts++;throw new TypeError('Synthetic lost connection');}return before(path,options);};
   click('Сохранить ручную оценку');await until(()=>doc.querySelector('#manual-workspace .notice[data-state="error"]'),'unknown outcome');
   assert(attempts===1,'one attempted POST');assert(doc.querySelector('#manual-workspace fieldset').disabled,'unknown save disabled');
   source('UI-SYNTHETIC:KZ');await selectedSource('UI-SYNTHETIC:KZ');source('UI-SYNTHETIC:RU');await selectedSource('UI-SYNTHETIC:RU');
   click('Сохранить ручную оценку');assert(attempts===1,'context switch cannot bypass unknown outcome');
   assert(named('Точная цитата',answer('CLARITY_X')).value===fixture.quote,'quote draft retained');
   await api('/api/evaluations?conversation_id=UI-SYNTHETIC%3ARU');
   click('Я проверил историю — разрешить новую отправку',doc.querySelector('#manual-workspace'));win.fetch=before;
  });
  await test('new arbitrary checklist editor, decimal precision, levels, sections and immutable versions',async()=>{
   nav('checklists');click('Создать новый чек-лист',doc.querySelector('#checklist-editor'));key='browser-'+Date.now();
   const editor=()=>doc.querySelector('#checklist-editor');fill('Новый checklist key',key,editor());fill('Название чек-листа','Browser <script>alert(1)</script>',editor());fill('Описание чек-листа','Synthetic browser-created rubric',editor());
   click('Добавить раздел',editor());fill('Section ID','custom-section',editor());fill('Название раздела','Custom section',editor());
   click('Добавить критерий',editor());let c=editor().querySelector('[data-criterion-index="0"]');
   fill('Criterion ID','ARBITRARY_SCALE',c);fill('Название критерия','Custom scale',c);fill('Инструкция','Choose a level from actual source.',c);fill('Тип критерия','scale',c);
   c=editor().querySelector('[data-criterion-index="0"]');fill('Вес','0.123456789012345678901',c);
   for(const v of ['0','7','10']){click('Добавить уровень',c);c=editor().querySelector('[data-criterion-index="0"]');const row=all('.level-row',c).at(-1);fill('Значение уровня',v,row);fill('Описание уровня','Level '+v,row);}
   click('Создать чек-лист',editor());await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes(key+' / v1.'),'new checklist');
   assert(named('Вес',editor()).value==='0.123456789012345678901','no decimal rounding in editor');assert(all('#checklist-editor script').length===0,'title escaped');
   const raw=await (await fetch('/api/checklists/'+key)).text();assert(raw.includes('0.123456789012345678901'),'exact decimal persisted');
   fill('Название чек-листа','Unsaved retained draft',editor());
   const external=await api('/api/checklists/'+key);const draft={title:'Concurrent v2',description:external.description,sections:external.sections,criteria:external.criteria};
   await api('/api/checklists/'+key+'?expected_version=1','PUT',draft);const writes=calls.filter(c=>c.method==='PUT').length;
   click('Сохранить новую версию',editor());await until(()=>editor().querySelector('.notice[data-state="error"]'),'checklist conflict');assert(named('Название чек-листа',editor()).value==='Unsaved retained draft','checklist draft retained');
   assert(calls.filter(c=>c.method==='PUT').length===writes+1,'PUT not replayed');click('Обновить latest для черновика',editor());await until(()=>editor().textContent.includes('Новая база: latest v2'),'base refreshed');
   click('Сохранить новую версию',editor());await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes(key+' / v3.'),'v3 saved');
   assert((await api('/api/checklists/'+key+'?version=1')).title==='Browser <script>alert(1)</script>','v1 immutable');
  });
  await test('audio stays unloaded until explicit action, organizer safe503 and honest AI state',async()=>{
   nav('conversations');source('UI-SYNTHETIC:EN');await selectedSource('UI-SYNTHETIC:EN');const audio=doc.querySelector('#conversation-workspace audio');
   assert(audio&&!audio.getAttribute('src')&&audio.preload==='none','no automatic audio request');
   assert(doc.querySelector('#manual-workspace').textContent.includes('после T13'),'honest AI state');
   nav('datasets');doc.querySelector('#group-id').value='SYNTHETIC';click('Fetch dataset');await until(()=>doc.querySelector('#dataset-result').dataset.state==='error','safe organizer error');
   assert(doc.querySelector('#dataset-result').textContent.includes('не настроено'),'fixed error');
   assert(!calls.some(c=>c.path.includes('/api/evaluations/auto')),'no AI requests');
   const hostile=parse(stringify(fixture.dataset));hostile.data.dataset_group_id='<img src=x onerror=alert(1)>';
   await api('/api/datasets/import','POST',hostile);click('Обновить список');
   await until(()=>doc.querySelector('#dataset-groups').textContent.includes('<img src=x onerror=alert(1)>'),'literal group ID');
   assert(doc.querySelectorAll('#dataset-groups img').length===0,'HTML-like group is plain text');
  });
  status.textContent='PASS: '+report.children.length+' browser scenarios; actual Java API, synthetic temporary SQLite.';
 }catch(error){status.textContent='FAIL: '+error.message;status.className='fail';}
});
