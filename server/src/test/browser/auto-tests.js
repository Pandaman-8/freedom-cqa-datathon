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
 fill('Checklist key',fixture.checklist.key);
 await until(()=>panel()&&doc.querySelector('#checklist-picker .notice').textContent.includes(fixture.checklist.key+' / v1.'),'fixture context');
}
async function load(){frame.src='/';await new Promise(r=>frame.addEventListener('load',r,{once:true}));doc=frame.contentDocument;win=frame.contentWindow;
 await until(()=>doc.querySelector('#connection').dataset.state==='ok'&&doc.querySelector('#checklist-picker .notice').textContent.includes('Выбрано:'),'workspace loaded');await context();}
async function test(name,run){await run();const li=document.createElement('li');li.textContent='PASS: '+name;report.append(li);}
async function newAttempt(mode){await api('/__tests/mode',{mode});fill('Я проверил статус и допускаю повторную стоимость',true,panel());click('Новая попытка с новым UUID',panel());assert(field('AI request_id',panel()).value==='','explicit new UUID preparation');}
async function checked(expected){click('Проверить AI статус',panel());await until(()=>panel().querySelector('.notice').textContent.includes(' · '+expected+':'),'ledger '+expected);}
document.querySelector('#run').addEventListener('click',async()=>{
 document.querySelector('#run').disabled=true;status.textContent='RUNNING';
 try{
  fixture=await api('/__tests/fixture.json');await load();let firstId,unknownId;
  await test('AI button -> Java -> fake HTTP -> SQLite model score100; double submit blocked; manual draft survives',async()=>{
   fill('Обоснование','Retained manual draft',doc.querySelector('[data-criterion-id="LOCAL_GREETING"]'));
   const before=(await api('/__tests/state')).calls;
   click('AI evaluation',panel());click('AI evaluation',panel());
   await until(()=>all('#evaluation-workspace .score-card').length===2&&idle(),'AI result');
   firstId=field('AI request_id',panel()).value;const saved=await api('/api/evaluation-requests/'+firstId);
   assert(saved.status==='succeeded','durable success');const view=await api('/api/evaluations/'+saved.evaluation_id);
   assert(view.origin==='model'&&view.original_score.overall_score===100,'actual Java result');
   assert((await api('/__tests/state')).calls===before+1,'single inference');
   await context();assert(field('Обоснование',doc.querySelector('[data-criterion-id="LOCAL_GREETING"]')).value==='Retained manual draft','manual draft intact');
  });
  await test('invalid evidence shows safe failure, durable failed status and no automatic POST retry',async()=>{
   const before=(await api('/__tests/state')).calls;await newAttempt('invalid');click('AI evaluation',panel());
   await until(()=>panel().querySelector('.notice[data-state="error"]')&&idle(),'invalid output');
   assert(field('AI request_id',panel()).value!==firstId,'new UUID');await checked('failed');
   click('AI evaluation',panel());assert((await api('/__tests/state')).calls===before+1,'failed ID not replayed');
  });
  await test('timeout is unknown; reload restores UUID and checks ledger without inference replay',async()=>{
   await newAttempt('timeout');click('AI evaluation',panel());
   await until(()=>panel().querySelector('.notice[data-state="error"]')&&idle(),'timeout');await checked('unknown');
   unknownId=field('AI request_id',panel()).value;const before=(await api('/__tests/state')).calls;
   await load();click('Восстановить последний AI запрос',panel());
   await until(()=>panel().querySelector('.notice').textContent.includes(' · unknown:'),'recovered unknown status');
   assert(field('AI request_id',panel()).value===unknownId,'UUID recovered across reload');
   click('AI evaluation',panel());assert((await api('/__tests/state')).calls===before,'no POST on reload/status/disabled button');
  });
  await test('explicit acknowledged new attempt saves a separate model result; previous unknown stays unknown',async()=>{
   await newAttempt('ok');click('AI evaluation',panel());await until(()=>all('#evaluation-workspace .score-card').length===2&&idle(),'explicit second result');
   const latest=field('AI request_id',panel()).value;assert(latest!==unknownId,'fresh UUID');
   assert((await api('/api/evaluation-requests/'+latest)).status==='succeeded','new success');
   assert((await api('/api/evaluation-requests/'+unknownId)).status==='unknown','unknown history immutable');
  });
  status.textContent='PASS: '+report.children.length+' AI browser scenarios. Fake ML only; live Python/provider E2E NOT RUN.';
 }catch(error){status.textContent='FAIL: '+error.message;status.className='fail';}
});
