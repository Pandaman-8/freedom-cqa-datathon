import {request, ApiError} from './api.js';
import {Latest} from './state.js';
import {BatchRunner, BATCH_KEY, lastAttempt, itemState} from './batch-state.js';
import {el,button,field,select,note,badge,messageNode,status} from './ui.js';

export function batch(root,{drafts,onOpen,onSaved}) {
  let selected=null,group='',ack=false,runner,broken=false,acting=false;
  const reads=new Latest(),feedback=messageNode(),progress=messageNode(),list=el('div'),pinned=el('div'),selectedNote=note('Выберите чек-лист сверху.');
  const groupField=select('Группа для batch',[['','Выберите группу']],group,v=>{group=v;});
  const groupInput=groupField.querySelector('select');
  const create=button('Зафиксировать batch',()=>action(()=>runner.create(group,selected)));
  const run=button('Запустить / продолжить batch',()=>action(()=>runner.resume(ack)),'primary');
  const pause=button('Пауза после текущего диалога',()=>{try{runner.pause();status(feedback,'Пауза запрошена. Текущий inference не отменяется; следующий диалог не отправится.');}catch{status(feedback,'Пауза запрошена, но manifest не записан. Сохраните UUID; после reload сверяйте ledger.','error');}});
  const refresh=button('Сверить статусы batch',()=>action(()=>runner.refresh()));
  const acknowledgement=field('Я проверил статусы и допускаю повторную стоимость; разрешаю продолжение после unknown/404',false,v=>{ack=v;render();},{type:'checkbox'});
  const forget=button('Убрать завершённый batch',()=>{
    if(window.confirm('Удалить локальный manifest завершённого batch? Оценки и request ledger останутся в Java.'))action(()=>runner.forget(true));
  },'quiet');
  root.append(el('div',{class:'panel'},el('h2',{text:'Массовая AI-оценка'}),
    note('Последовательно, один диалог за раз. Используется выбранная сверху версия чек-листа. Состав группы фиксируется перед запуском; новые импорты не добавляются в текущий batch.'),
    note('Java разрешает только точные опубликованные собственные ML fixtures. Имя группы SYNTHETIC само по себе не даёт разрешения. DEV/CONTROL не отправляются внешнему провайдеру.'),
    el('div',{class:'toolbar'},groupField,button('Обновить группы batch',loadGroups),create),selectedNote,pinned,
    el('div',{class:'toolbar'},run,pause,refresh,forget),acknowledgement,feedback,progress,
    note('Manifest хранится в этом браузере для этого адреса: только ID, UUID, версия и статусы. После reload автоматической отправки нет. Не очищайте данные сайта и не меняйте Java SQLite, пока batch не завершён. Пауза и закрытие вкладки не отменяют текущий inference.'),list));
  function render(){
    const m=runner?.manifest,busy=!!runner?.running||acting;
    create.disabled=broken||busy||!!m||!selected;groupInput.disabled=busy||!!m;
    run.disabled=broken||busy||!m||!m.items.some(i=>!i.attempts.length);
    pause.disabled=!runner?.running||!m;refresh.disabled=broken||busy||!m;
    forget.disabled=broken||busy||!m||m.items.some(i=>!['succeeded','failed','conflict'].includes(itemState(i)));
    acknowledgement.querySelector('input').disabled=busy;
    if(!m){pinned.replaceChildren();progress.textContent='Batch ещё не создан.';list.replaceChildren();return;}
    pinned.replaceChildren(badge(m.group),badge(`${m.checklist_key} / v${m.checklist_version}`),note(`Batch ${m.id} · ${busy?(runner.stopRequested?'пауза запрошена':'выполняется'):m.paused?'остановлен; продолжение только вручную':'незавершённый запуск или другая вкладка; сверьте статусы'}`));
    const counts={queued:0,succeeded:0,failed:0,pending:0,unknown:0};
    for(const item of m.items){const s=itemState(item);counts[s==='conflict'?'failed':['sending','pending'].includes(s)?'pending':['unresolved','not_found'].includes(s)?'unknown':s]++;}
    const done=counts.succeeded+counts.failed;
    status(progress,`Всего ${m.items.length} · завершено ${done} · success ${counts.succeeded} · error ${counts.failed} · pending ${counts.pending} · unknown ${counts.unknown} · queued ${counts.queued}`);
    const bar=el('progress',{max:m.items.length,value:done,'aria-label':'Прогресс batch'});
    list.replaceChildren(bar,...m.items.map(item=>{
      const a=lastAttempt(item),s=itemState(item);
      const card=el('article',{class:'batch-item','data-batch-conversation':item.conversation_id,'data-batch-state':s},
        el('h3',{class:'inline-id',text:item.conversation_id}),badge(s));
      if(a){
        card.append(note(`request_id: ${a.request_id}`));
        if(a.code)card.append(note(`${a.code}: ${new ApiError(0,a.code).message}`));
        if(['unknown','not_found','unresolved','sending','pending'].includes(s))card.append(note('Исход требует сверки с Java. Никакого автоматического повторного POST. 404 после потери связи не доказывает отмену inference.'));
        if(a.evaluation_id){const open=button('Открыть результат',()=>onOpen(a.evaluation_id));open.disabled=busy;card.append(open);}
        if(['failed','unknown','not_found','conflict'].includes(s)){
          const retry=button('Новая попытка для этого диалога',()=>action(()=>runner.retry(item.conversation_id,ack)));
          retry.disabled=busy||!ack||broken;card.append(retry);
        }
        card.append(el('details',{},el('summary',{text:`История попыток: ${item.attempts.length}`}),...item.attempts.map(a=>note(`${a.request_id} · ${a.state}${a.code?' · '+a.code:''}${a.evaluation_id?' · evaluation '+a.evaluation_id:''}`))));
      }
      return card;
    }));
  }
  async function action(work,background=false){
    if(broken||acting||runner.running||(!background&&drafts.pending))return;
    acting=true;if(!background){drafts.pending++;drafts.changed();}render();
    status(feedback,'Сверяем manifest и request ledger…','loading');
    try{await work();status(feedback,'Состояние batch сохранено. Отправлялись только явно запущенные элементы.');await onSaved();}
    catch(error){status(feedback,error instanceof Error&&error.name==='Error'||error instanceof ApiError?error.message:'Не удалось прочитать или сохранить manifest. Отправка остановлена; проверьте UUID в Java.','error');}
    finally{acting=false;if(!background){drafts.pending--;drafts.changed();}ack=false;acknowledgement.querySelector('input').checked=false;render();}
  }
  async function loadGroups(){
    const ticket=reads.next();
    try{
      const rows=await request('/api/conversations',ticket);if(!ticket.current())return;
      const groups=new Map();for(const row of rows)groups.set(row.dataset_group_id,(groups.get(row.dataset_group_id)||0)+1);
      groupInput.replaceChildren(el('option',{value:'',text:'Выберите группу'}),...[...groups].map(([id,n])=>el('option',{value:id,text:`${id} (${n})`})));
      groupInput.value=group;
    }catch(error){if(ticket.current())status(feedback,error.message,'error');}
  }
  try{
    runner=new BatchRunner({storage:localStorage,changed:render});
    runner.load();if(runner.manifest)action(()=>runner.refresh(),true);
  }catch{broken=true;status(feedback,'Manifest недоступен или повреждён. Batch заблокирован; сохраните UUID и проверьте историю в Java.','error');}
  window.addEventListener('storage',event=>{if(event.key!==BATCH_KEY||runner?.running)return;try{runner.load();}catch{broken=true;status(feedback,'Manifest изменён другой вкладкой и не может быть прочитан. Отправка заблокирована.','error');}render();});
  loadGroups();render();
  return {checklist(value){selected=value;selectedNote.textContent=value?`Для нового batch: ${value.key} / v${value.version}. Существующий batch сохраняет свою версию.`:'Выберите конкретную версию чек-листа сверху.';render();}};
}
