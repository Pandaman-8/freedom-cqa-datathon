import {request, pathId, ApiError} from './api.js';
import {Latest} from './state.js';
import {el, button, field, note, messageNode, status} from './ui.js';

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const storedId=()=>{try{return sessionStorage.getItem('cqa:last-auto-request')||'';}catch{return '';}};
const remember=id=>{try{sessionStorage.setItem('cqa:last-auto-request',id);}catch{/* Manual UUID recovery remains available. */}};

export function automatic(source,checklist,{drafts,onSaved}) {
  const key='auto:'+JSON.stringify([source.id,checklist.key,String(checklist.version)]);
  const entry=drafts.get(key,()=>({id:'',view:null,checked:false})).value;
  const reads=new Latest(),readinessReads=new Latest(),readiness=messageNode(),feedback=messageNode(),node=el('section',{class:'panel','data-auto-workspace':''});
  feedback.dataset.requestFeedback='';
  let active=true,busy=false,recovery=entry.id,ack=false,ready=false,confirmationRequired=false,confirmed=false,confirmationScope=null;
  const rubricConfirmation=field('Подтверждаю передачу этого диалога и выбранной версии чек-листа в Groq GPT-OSS 20B',false,value=>{confirmed=value;render();},{type:'checkbox'});
  rubricConfirmation.hidden=true;rubricConfirmation.dataset.rubricConfirmation='';
  const idField=field('Идентификатор запроса',recovery,value=>{recovery=value;});
  const idInput=idField.querySelector('input');
  const start=button('Оценить с ИИ',submit,'primary');
  const refresh=button('Проверить результат запроса',check);
  const open=button('Открыть результат',async()=>{if(entry.view?.evaluation_id)await onSaved(entry.view.evaluation_id);});
  const retry=button('Подготовить новую попытку',()=>{
    if(!ack||!entry.checked||entry.view?.status==='pending'||busy||drafts.pending)return;
    entry.id='';entry.view=null;entry.checked=false;recovery='';idInput.value='';ack=false;
    acknowledgement.querySelector('input').checked=false;render();
    status(feedback,'Подготовлена новая попытка. Нажмите «Оценить с ИИ» для отправки.');
  });
  const acknowledgement=field('Я проверил статус и допускаю повторную стоимость',false,value=>{ack=value;render();},{type:'checkbox'});
  function render(){
    start.disabled=busy||!!entry.id||!ready||(confirmationRequired&&!confirmed);refresh.disabled=busy;refresh.hidden=!entry.id;idInput.disabled=busy;
    rubricConfirmation.querySelector('input').disabled=busy||!ready;
    retry.disabled=busy||!entry.id||!entry.checked||entry.view?.status==='pending'||!ack;
    open.hidden=!entry.view?.evaluation_id;
  }
  function display(view){
    entry.view=view;entry.checked=true;node.dataset.requestState=view.status;
    const labels={pending:'Выполняется. Проверяйте статус; повторного POST не будет.',succeeded:'Оценка сохранена в Java.',
      failed:'Запрос завершился ошибкой. Автоматического повтора нет.',unknown:'Исход неизвестен. Обработка могла завершиться и быть оплачена. Автоматического повтора нет.'};
    status(feedback,labels[view.status]||'Неизвестный статус.',
      ['failed','unknown'].includes(view.status)?'error':'ok');render();
  }
  async function check(){
    if(busy||drafts.pending)return;
    if(!uuid.test(recovery)){status(feedback,'Укажите идентификатор из подробностей предыдущего запроса.','error');return;}
    entry.id=recovery;entry.checked=false;remember(entry.id);const ticket=reads.next();busy=true;render();
    try{const view=await request('/api/evaluation-requests/'+pathId(entry.id),ticket);if(active&&ticket.current())display(view);}
    catch(e){if(active&&ticket.current()){
      if(e.status===404){entry.checked=true;entry.view={status:'not_found'};status(feedback,'Этот запрос не найден в журнале сервера. Новая отправка требует явного действия.','error');}
      else status(feedback,e.message,'error');
    }}finally{if(active&&ticket.current()){busy=false;render();}}
  }
  async function submit(){
    if(busy||drafts.pending||entry.id||!ready||(confirmationRequired&&!confirmed))return;
    busy=true;drafts.pending++;drafts.changed();render();
    const ticket=reads.next();
    try{
      // A previously green indicator may be stale after revocation or an ML restart.
      // Do not allocate an inference UUID or durable intent for a known refusal.
      if(!await checkReadiness()||!active||!ticket.current())return;
      if(confirmationRequired&&!confirmed){status(feedback,new ApiError(0,'RUBRIC_CONFIRMATION_REQUIRED').message,'error');return;}
      entry.id=crypto.randomUUID();recovery=entry.id;idInput.value=entry.id;remember(entry.id);
      entry.checked=false;entry.view=null;
      status(feedback,'ИИ оценивает диалог… Дождитесь результата.','loading');
      const result=await request('/api/evaluations/auto',{method:'POST',timeout:75000,signal:ticket.signal,rubricConfirmed:confirmationRequired&&confirmed,
        body:{request_id:entry.id,conversation_id:source.id,checklist_key:checklist.key,checklist_version:checklist.version}});
      if(!active||!ticket.current())return;
      if(result.status==='pending')display(result);
      else {display({status:'succeeded',evaluation_id:result.id});await onSaved(result.id);}
    }catch(e){if(active&&ticket.current())status(feedback,`${e.message} Сначала проверьте результат запроса; его идентификатор находится в подробностях.`, 'error');}
    finally{drafts.pending--;drafts.changed();busy=false;if(active)render();}
  }
  async function checkReadiness(){
    const ticket=readinessReads.next();ready=false;render();status(readiness,'Проверяем ML и разрешение на выбранные данные…','loading');
    try {
      const state=await request('/api/ai/status?conversation_id='+pathId(source.id)+'&checklist_key='+pathId(checklist.key)+'&checklist_version='+pathId(String(checklist.version)),ticket);
      if(!active||!ticket.current())return false;
      confirmationRequired=state.rubric_confirmation_required===true;
      if(confirmationScope!==state.confirmation_scope){confirmed=false;rubricConfirmation.querySelector('input').checked=false;}
      confirmationScope=state.confirmation_scope;rubricConfirmation.hidden=!confirmationRequired;
      ready=state.ready;node.dataset.aiState=ready?'ready':'blocked';
      status(readiness,ready?'ИИ доступен для этого диалога. Будут переданы сообщения и выбранная рубрика.':new ApiError(0,state.reason).message,ready?'ok':'error');
      return ready;
    }catch(e){if(active&&ticket.current()){node.dataset.aiState='unavailable';status(readiness,e.message,'error');}}
    finally{if(active&&ticket.current())render();}
  }
  const technical=el('details',{'data-ai-details':''},el('summary',{text:'Подробности и восстановление запроса'}),
    note('При потере связи запрос не повторяется автоматически. Проверьте его состояние перед новой попыткой.'),button('Проверить готовность ИИ',checkReadiness,'quiet'),idField,acknowledgement,retry);
  node.append(el('h3',{text:'Оценка диалога'}),note(`${checklist.title} · версия ${checklist.version}`),
    rubricConfirmation,el('div',{class:'toolbar'},start,open,refresh),readiness,
    feedback,technical);
  const last=storedId();if(uuid.test(last))technical.append(button('Восстановить последний запрос',()=>{if(busy||drafts.pending)return;recovery=last;idInput.value=last;check();}));
  if(entry.view)display(entry.view);render();checkReadiness();
  return {node,dispose(){active=false;reads.cancel();readinessReads.cancel();}};
}
