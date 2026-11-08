const frame=document.querySelector('#workspace'),report=document.querySelector('#checks'),output=document.querySelector('#status');
let doc,win,rows,chosen,source,rubric,saved;
const assert=(v,label)=>{if(!v)throw new Error(label);};
const all=(selector,root=doc)=>[...root.querySelectorAll(selector)];
const idle=()=>doc.querySelector('#draft-status').textContent.startsWith('Несохранённых');
async function until(check,label){for(let i=0;i<400;i++){if(check())return;await new Promise(r=>setTimeout(r,40));}throw new Error(label);}
async function api(path){const r=await fetch(path);assert(r.ok,'API read failed');return r.json();}
function click(text,root=doc){const buttons=all('button',root).filter(n=>n.textContent.trim()===text);assert(buttons.length===1,'Unique action '+text);reveal(buttons[0]);buttons[0].click();}
function reveal(node){const parents=[];for(let p=node.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open)parents.unshift(p);for(const p of parents)p.querySelector('summary').click();}
function fill(label,value,root=doc){const fields=all('label',root).filter(n=>n.querySelector('span')?.textContent===label);assert(fields.length===1,'Unique field '+label);const n=fields[0].querySelector('input,select,textarea');reveal(n);if(n.type==='checkbox')n.checked=value;else n.value=value;n.dispatchEvent(new win.Event(n.tagName==='SELECT'?'change':'input',{bubbles:true}));}
const nav=name=>{if(name==='batch')doc.querySelector('[data-view="results"]').click();doc.querySelector('[data-view="'+name+'"]').click();};
async function selectSource(row){all('#conversation-workspace .list-row').find(n=>n.dataset.conversationId===row.id).click();await until(()=>doc.querySelector('#conversation-workspace .conversation-detail [data-conversation-id]')?.dataset.conversationId===row.id,'Source selected');}
async function test(label,run){await run();await until(idle,'Pending mutation');const li=document.createElement('li');li.textContent='PASS: '+label;report.append(li);}
function compose(rubric,source){
 const message=source.messages.find(m=>m.speaker==='operator'&&m.text.trim());
 for(const c of rubric.criteria){const card=doc.querySelector('[data-criterion-id="'+c.id+'"]');fill('Ответ',c.allow_na?'na':c.kind==='scale'?'level:0':'no',card);fill('Обоснование','Техническая проверка формы, не оценка качества диалога.',card);click('Добавить доказательство',card);fill('Сообщение',message.id,card);click('Взять текст сообщения',card);}
}
document.querySelector('#run').addEventListener('click',async()=>{
 document.querySelector('#run').disabled=true;output.textContent='RUNNING';
 try{
  rows=await api('/api/conversations');assert(rows.length===65,'65 existing DEV inputs');
  frame.src='/';await new Promise(r=>frame.addEventListener('load',r,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;
  await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('Выбрано:')&&all('#conversation-workspace .list-row').length===65,'Workspace loaded');
  await test('65 DEV / language and channel filters / exact source and five audio locators',async()=>{
   nav('conversations');const root=doc.querySelector('#conversation-workspace');
   for(const language of ['RU','KZ','EN']){fill('Язык',language,root);assert(all('.list-row',root).length===rows.filter(r=>r.language===language).length,'Language filter');const row=rows.find(r=>r.language===language&&r.channel==='agent chat');await selectSource(row);const data=await api('/api/conversations/'+encodeURIComponent(row.id));assert(all('.turn',root).length===data.messages.length,'Turn count');assert(all('.turn',root).every((n,i)=>n.dataset.messageId===data.messages[i].id&&n.dataset.speaker===data.messages[i].speaker&&n.querySelector('.source-text').textContent===data.messages[i].text&&n.querySelector('.turn-meta').textContent.includes(data.messages[i].timestamp)),'Exact source DOM');}
   fill('Язык','',root);fill('Канал','voice call',root);assert(all('.list-row',root).length===5,'Five voice calls');
   for(const row of rows.filter(r=>r.channel==='voice call')){await selectSource(row);const data=await api('/api/conversations/'+encodeURIComponent(row.id));assert(root.querySelector('.audio-box a').href===new URL(data.audio_url).href,'Audio URL preserved');assert(root.querySelector('audio').getAttribute('preload')==='none'&&!root.querySelector('audio').getAttribute('src'),'No audio download');}
   fill('Канал','',root);chosen=rows.find(r=>r.channel==='agent chat'&&r.language==='RU');await selectSource(chosen);source=await api('/api/conversations/'+encodeURIComponent(chosen.id));
  });
  await test('C01–C08 / manual collapsed / honest AI readiness / technical fields collapsed',async()=>{
   fill('Чек-лист','chat-quality');fill('Версия (пусто = последняя)','1');click('Открыть версию');await until(()=>doc.querySelector('#checklist-picker .notice').textContent.includes('/ v1.'),'v1 selected');
   rubric=await api('/api/checklists/chat-quality?version=1');assert(rubric.criteria.length===8,'Eight criteria');
   await until(()=>doc.querySelector('[data-auto-workspace]')?.dataset.aiState==='blocked','Policy readiness');
   assert(!doc.querySelector('[data-manual]').open,'Manual collapsed');assert(!doc.querySelector('[data-ai-details]').open,'Technical details collapsed');
   assert(all('button',doc.querySelector('[data-auto-workspace]')).find(n=>n.textContent==='Оценить с ИИ').disabled,'No misleading AI action');
  });
  await test('manual technical evaluation / NA / exact quotes / compact single result',async()=>{
   doc.querySelector('[data-manual]').open=true;compose(rubric,source);click('Сохранить ручную оценку');await until(()=>doc.querySelector('.score-card')&&idle(),'Saved manual');
   saved=(await api('/api/evaluations?conversation_id='+encodeURIComponent(chosen.id))).find(e=>e.original_answers[0].explanation.startsWith('Техническая проверка формы'));
   assert(saved.origin==='manual'&&saved.original_answers.length===8,'Manual, not fake model');assert(saved.original_answers.some(a=>a.answer==='na'),'NA present');
   assert(all('.score-card').length===1,'No identical original/final duplication');assert(all('[data-score-criterion]').length===8,'All eight criteria visible');
   doc.querySelector('.evidence-link').click();assert(doc.querySelector('#evaluation-workspace .turn.focused'),'Evidence jump');
  });
  await test('appeal / reviewer change / immutable original / history',async()=>{
   const root=doc.querySelector('#evaluation-workspace');fill('Критерий апелляции','C01',root);fill('Комментарий апелляции','Техническая UI-проверка.',root);click('Отправить апелляцию',root);await until(()=>root.querySelector('.appeal-card form')&&idle(),'Appeal saved');
   const card=root.querySelector('.appeal-card');fill('Решение','change',card);fill('Причина решения','Техническая проверка пересчёта.',card);fill('Ответ','yes',card);click('Сохранить решение',card);await until(()=>!root.querySelector('.appeal-card form')&&idle(),'Review saved');
   const final=await api('/api/evaluations/'+saved.id);assert(final.original_score.overall_score===saved.original_score.overall_score&&JSON.stringify(final.original_answers)===JSON.stringify(saved.original_answers),'Original immutable');assert(final.final_score.overall_score>saved.original_score.overall_score,'Final rescore');assert(root.querySelector('[data-original]')&&!root.querySelector('[data-original]').open,'Original kept in collapsed history');
  });
  await test('replace criterion in UI / select new version / retain v1 / explicit AI denial',async()=>{
   nav('checklists');const card=doc.querySelector('[data-criterion-index="0"]');fill('ID критерия','UI_BETA_ITEM',card);fill('Название критерия','Технический критерий версии',card);fill('Инструкция','Техническая проверка новой версии; не экспертная рубрика.',card);
   click('Сохранить новую версию');await until(()=>all('button').some(n=>n.textContent==='Оценить по новой версии')&&idle(),'New version CTA');
   const latest=await api('/api/checklists/chat-quality');assert(latest.version===3&&latest.criteria[0].id==='UI_BETA_ITEM','New version appended after harness v2');
   click('Оценить по новой версии');await until(()=>doc.querySelector('[data-auto-workspace]')?.dataset.aiState==='blocked','Unapproved new rubric denied');
   assert(!doc.querySelector('[data-panel="conversations"]').hidden,'Return to selected conversation');assert((await api('/api/checklists/chat-quality?version=1')).criteria[0].id==='C01','v1 unchanged');assert((await api('/api/evaluations/'+saved.id)).checklist_version===1,'Result pinned');
   doc.querySelector('[data-manual]').open=true;compose(latest,source);click('Сохранить ручную оценку');await until(()=>doc.querySelector('#evaluation-workspace').textContent.includes('/ v3')&&idle(),'New manual result');
   const history=await api('/api/evaluations?conversation_id='+encodeURIComponent(chosen.id));assert(history.some(e=>e.checklist_version===1)&&history.some(e=>e.checklist_version===3),'Both versions persisted');
  });
  await test('batch accounts for 65 denied DEV requests without inference or fake success',async()=>{
   nav('batch');click('Обновить группы');await until(()=>all('#batch-workspace select option').length>1,'Groups loaded');fill('Группа для оценки',chosen.dataset_group_id,doc.querySelector('#batch-workspace'));click('Подготовить пакет');await until(()=>all('.batch-item').length===65&&idle(),'Batch pinned');click('Запустить / продолжить');await until(()=>all('.batch-item[data-batch-state="blocked"]').length===65&&idle(),'All 65 explicit failures');assert((await api('/__tests/status')).ml_posts===0,'No ML POST');
  });
  output.textContent='PASS: '+report.children.length+' DEV browser scenarios. ML POST=0; manual technical results only.';
 }catch(e){output.textContent='FAIL: '+e.message;}
});
