import {request, pathId} from './api.js';
import {Latest} from './state.js';
import {el, button, field, note, messageNode, status} from './ui.js';

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const storedId=()=>{try{return sessionStorage.getItem('cqa:last-auto-request')||'';}catch{return '';}};
const remember=id=>{try{sessionStorage.setItem('cqa:last-auto-request',id);}catch{/* Manual UUID recovery remains available. */}};

export function automatic(source,checklist,{drafts,onSaved}) {
  const key='auto:'+JSON.stringify([source.id,checklist.key,String(checklist.version)]);
  const entry=drafts.get(key,()=>({id:'',view:null,checked:false})).value;
  const reads=new Latest(),feedback=messageNode(),node=el('section',{class:'panel','data-auto-workspace':''});
  let active=true,busy=false,recovery=entry.id,ack=false;
  const idField=field('AI request_id',recovery,value=>{recovery=value;});
  const idInput=idField.querySelector('input');
  const start=button('AI evaluation',submit,'primary');
  const refresh=button('Проверить AI статус',check);
  const open=button('Открыть AI результат',async()=>{if(entry.view?.evaluation_id)await onSaved(entry.view.evaluation_id);});
  const retry=button('Новая попытка с новым UUID',()=>{
    if(!ack||!entry.checked||entry.view?.status==='pending'||busy||drafts.pending)return;
    entry.id='';entry.view=null;entry.checked=false;recovery='';idInput.value='';ack=false;
    acknowledgement.querySelector('input').checked=false;render();
    status(feedback,'Подготовлена новая попытка. Отправка — только кнопкой AI evaluation.');
  });
  const acknowledgement=field('Я проверил статус и допускаю повторную стоимость',false,value=>{ack=value;render();},{type:'checkbox'});
  function render(){
    start.disabled=busy||!!entry.id;refresh.disabled=busy;idInput.disabled=busy;
    retry.disabled=busy||!entry.id||!entry.checked||entry.view?.status==='pending'||!ack;
    open.hidden=!entry.view?.evaluation_id;
  }
  function display(view){
    entry.view=view;entry.checked=true;
    const labels={pending:'Выполняется. Проверяйте статус; повторного POST не будет.',succeeded:'Оценка сохранена в Java.',
      failed:'Запрос завершился ошибкой. Автоматического повтора нет.',unknown:'Исход неизвестен. Inference мог завершиться и быть оплачен. Повтор этого UUID запрещён.'};
    status(feedback,`${entry.id} · ${view.status}: ${labels[view.status]||'Неизвестный статус.'}`,
      ['failed','unknown'].includes(view.status)?'error':'ok');render();
  }
  async function check(){
    if(busy||drafts.pending)return;
    if(!uuid.test(recovery)){status(feedback,'Укажите request_id UUID из предыдущей отправки.','error');return;}
    entry.id=recovery;entry.checked=false;remember(entry.id);const ticket=reads.next();busy=true;render();
    try{const view=await request('/api/evaluation-requests/'+pathId(entry.id),ticket);if(active&&ticket.current())display(view);}
    catch(e){if(active&&ticket.current()){
      if(e.status===404){entry.checked=true;entry.view={status:'not_found'};status(feedback,'Этот request_id не найден в ledger. Новая отправка требует явного действия.','error');}
      else status(feedback,e.message,'error');
    }}finally{if(active&&ticket.current()){busy=false;render();}}
  }
  async function submit(){
    if(busy||drafts.pending||entry.id)return;
    entry.id=crypto.randomUUID();recovery=entry.id;idInput.value=entry.id;remember(entry.id);
    entry.checked=false;entry.view=null;busy=true;drafts.pending++;drafts.changed();render();
    const ticket=reads.next();status(feedback,`${entry.id} · AI evaluation выполняется…`,'loading');
    try{
      const result=await request('/api/evaluations/auto',{method:'POST',timeout:75000,signal:ticket.signal,
        body:{request_id:entry.id,conversation_id:source.id,checklist_key:checklist.key,checklist_version:checklist.version}});
      if(!active||!ticket.current())return;
      if(result.status==='pending')display(result);
      else {display({status:'succeeded',evaluation_id:result.id});await onSaved(result.id);}
    }catch(e){if(active&&ticket.current())status(feedback,`${e.message} Request ID: ${entry.id}. Сначала проверьте AI статус.`, 'error');}
    finally{drafts.pending--;drafts.changed();busy=false;if(active)render();}
  }
  node.append(el('h3',{text:'AI evaluation'}),note('Java → локальный Python ML. Доступно только при серверной настройке и точном совпадении с собственной ML fixture. Без настройки Java возвращает 501. Реальные данные запрещены.'),
    note('Timeout не гарантирует отмену inference. UUID сохраняется до отправки; status ledger переживает перезапуск Java. Автоматических повторов POST нет.'),idField,
    el('div',{class:'toolbar'},start,refresh,open),feedback,acknowledgement,retry);
  const last=storedId();if(uuid.test(last))node.append(button('Восстановить последний AI запрос',()=>{if(busy||drafts.pending)return;recovery=last;idInput.value=last;check();}));
  if(entry.view)display(entry.view);render();
  return {node,dispose(){active=false;reads.cancel();}};
}
