const frame=document.querySelector('#workspace'),report=document.querySelector('#checks'),status=document.querySelector('#status');
let doc,win,fixture;
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
async function until(test,label){for(let i=0;i<250;i++){if(test())return;await new Promise(r=>setTimeout(r,40));}throw new Error('Timeout: '+label);}
const all=(selector,root=doc)=>[...root.querySelectorAll(selector)];
const panel=()=>doc.querySelector('[data-auto-workspace]');
const idle=()=>doc.querySelector('#draft-status').textContent.startsWith('Несохранённых');
function click(text,root=doc){const nodes=all('button',root).filter(n=>n.textContent===text);assert(nodes.length===1,'Unique button '+text);nodes[0].click();}
function field(text,root=doc){const labels=all('label',root).filter(n=>n.querySelector('span')?.textContent===text);assert(labels.length===1,'Unique field '+text);return labels[0].querySelector('input,textarea,select');}
function fill(text,value,root=doc){const n=field(text,root);if(n.type==='checkbox')n.checked=value;else n.value=value;n.dispatchEvent(new win.Event(n.tagName==='SELECT'?'change':'input',{bubbles:true}));}
async function api(route,body){const response=await fetch(route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});assert(response.ok,'Harness API '+response.status);return response.json();}
async function context(){
 doc.querySelector('[data-view="conversations"]').click();
 await until(()=>all('#conversation-workspace .list-row').length,'conversations');
 const row=all('#conversation-workspace .list-row').find(n=>n.querySelector('strong')?.textContent===fixture.conversation.id);assert(row,'fixture conversation');row.click();
 fill('Чек-лист',fixture.checklist.key);
 await until(()=>panel()&&doc.querySelector('#checklist-picker .notice').textContent.includes(fixture.checklist.key+' / v1.'),'fixture context');
}
async function load(){frame.src='/';await new Promise(r=>frame.addEventListener('load',r,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;
 await until(()=>doc.querySelector('#connection').dataset.state==='ok'&&doc.querySelector('#checklist-picker .notice').textContent.includes('Выбрано:'),'workspace loaded');await context();await until(()=>panel()?.dataset.aiState==='ready','ML readiness');}
async function test(name,run){await run();const li=document.createElement('li');li.textContent='PASS: '+name;report.append(li);}
async function newAttempt(mode){await api('/__tests/mode',{mode});fill('Я проверил статус и допускаю повторную стоимость',true,panel());click('Подготовить новую попытку',panel());assert(field('Идентификатор запроса',panel()).value==='','explicit new UUID preparation');}
async function checked(expected){click('Проверить результат запроса',panel());await until(()=>panel().dataset.requestState===expected,'ledger '+expected);}
document.querySelector('#run').addEventListener('click',async()=>{
 document.querySelector('#run').disabled=true;status.textContent='RUNNING';
 try{
  fixture=await api('/__tests/fixture.json');await load();let firstId,unknownId;
  await test('rubric confirmation is explicit and a changed grant clears consent before UUID/POST (readiness response simulated)',async()=>{
   const native=win.fetch.bind(win);let scope='test-grant-a';const before=(await api('/__tests/state')).calls;
   win.fetch=async(path,options)=>{
    const response=await native(path,options);
    if(String(path).startsWith('/api/ai/status'))return new win.Response(JSON.stringify({...await response.json(),rubric_confirmation_required:true,confirmation_scope:scope}),{status:response.status,headers:{'Content-Type':'application/json'}});
    return response;
   };
   try{
    click('Проверить готовность ИИ',panel());await until(()=>panel()?.dataset.aiState==='ready'&&!panel().querySelector('[data-rubric-confirmation]').hidden,'confirmation displayed');
    const label='Подтверждаю передачу этого диалога и выбранной версии чек-листа в Groq GPT-OSS 20B';
    assert(!field(label,panel()).checked,'Consent not implicit');click('Оценить с ИИ',panel());assert(field('Идентификатор запроса',panel()).value==='','No unconfirmed UUID');
    fill(label,true,panel());scope='test-grant-b';click('Оценить с ИИ',panel());await until(()=>idle()&&!field(label,panel()).checked,'Changed grant clears consent');
    assert(field('Идентификатор запроса',panel()).value==='','No stale-consent UUID');assert((await api('/__tests/state')).calls===before,'No inference POST');
   }finally{win.fetch=native;click('Проверить готовность ИИ',panel());await until(()=>panel()?.dataset.aiState==='ready'&&panel().querySelector('[data-rubric-confirmation]').hidden,'Original readiness restored');}
  });
  await test('stale ready indicator is checked again before UUID allocation; known ML refusal sends no POST',async()=>{
   const before=(await api('/__tests/state')).calls;
   await api('/__tests/mode',{mode:'unconfigured'});
   click('Оценить с ИИ',panel());
   await until(()=>panel()?.dataset.aiState==='blocked'&&idle(),'fresh readiness refusal');
   assert(field('Идентификатор запроса',panel()).value==='','no inference UUID for known refusal');
   assert((await api('/__tests/state')).calls===before,'no inference POST for known refusal');
   await api('/__tests/mode',{mode:'ok'});click('Проверить готовность ИИ',panel());
   await until(()=>panel()?.dataset.aiState==='ready','readiness restored explicitly');
  });
  await test('AI button -> Java -> fake HTTP -> SQLite model score100; double submit blocked; manual draft survives',async()=>{
   fill('Обоснование','Retained manual draft',doc.querySelector('[data-criterion-id="LOCAL_GREETING"]'));
   const before=(await api('/__tests/state')).calls;
   await until(()=>panel()?.dataset.aiState==='ready','ML readiness');click('Оценить с ИИ',panel());await until(()=>panel()?.dataset.aiState==='ready','ML readiness');click('Оценить с ИИ',panel());
   await until(()=>all('#evaluation-workspace .score-card').length===1&&idle(),'AI result');
   firstId=field('Идентификатор запроса',panel()).value;const saved=await api('/api/evaluation-requests/'+firstId);
   assert(saved.status==='succeeded','durable success');const view=await api('/api/evaluations/'+saved.evaluation_id);
   assert(view.origin==='model'&&view.original_score.overall_score===100,'actual Java result');
   assert((await api('/__tests/state')).calls===before+1,'single inference');
   await context();await until(()=>panel()?.dataset.aiState==='ready','ML readiness');assert(field('Обоснование',doc.querySelector('[data-criterion-id="LOCAL_GREETING"]')).value==='Retained manual draft','manual draft intact');
  });
  await test('invalid evidence shows safe failure, durable failed status and no automatic POST retry',async()=>{
   const before=(await api('/__tests/state')).calls;await newAttempt('invalid');await until(()=>panel()?.dataset.aiState==='ready','ML readiness');click('Оценить с ИИ',panel());
   await until(()=>panel().querySelector('.notice[data-state="error"]')&&idle(),'invalid output');
   assert(field('Идентификатор запроса',panel()).value!==firstId,'new UUID');await checked('failed');
   await until(()=>panel()?.dataset.aiState==='ready','ML readiness');click('Оценить с ИИ',panel());assert((await api('/__tests/state')).calls===before+1,'failed ID not replayed');
  });
  await test('timeout is unknown; reload restores UUID and checks ledger without inference replay',async()=>{
   await newAttempt('timeout');await until(()=>panel()?.dataset.aiState==='ready','ML readiness');click('Оценить с ИИ',panel());
   await until(()=>panel().querySelector('.notice[data-state="error"]')&&idle(),'timeout');await checked('unknown');
   unknownId=field('Идентификатор запроса',panel()).value;const before=(await api('/__tests/state')).calls;
   await load();click('Восстановить последний запрос',panel());
   await until(()=>panel().dataset.requestState==='unknown','recovered unknown status');
   assert(field('Идентификатор запроса',panel()).value===unknownId,'UUID recovered across reload');
   await until(()=>panel()?.dataset.aiState==='ready','ML readiness');click('Оценить с ИИ',panel());assert((await api('/__tests/state')).calls===before,'no POST on reload/status/disabled button');
  });
  await test('explicit acknowledged new attempt saves a separate model result; previous unknown stays unknown',async()=>{
   await newAttempt('ok');await until(()=>panel()?.dataset.aiState==='ready','ML readiness');click('Оценить с ИИ',panel());await until(()=>all('#evaluation-workspace .score-card').length===1&&idle(),'explicit second result');
   const latest=field('Идентификатор запроса',panel()).value;assert(latest!==unknownId,'fresh UUID');
   assert((await api('/api/evaluation-requests/'+latest)).status==='succeeded','new success');
   assert((await api('/api/evaluation-requests/'+unknownId)).status==='unknown','unknown history immutable');
  });
  status.textContent='PASS: '+report.children.length+' AI browser scenarios. Fake ML only; live Python/provider E2E NOT RUN.';
 }catch(error){status.textContent='FAIL: '+error.message;status.className='fail';}
});
