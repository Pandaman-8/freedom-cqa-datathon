import {request, ApiError} from './api.js';
import {Latest} from './state.js';
import {BatchRunner, BATCH_KEY, lastAttempt, itemState} from './batch-state.js';
import {el,button,field,select,note,badge,messageNode,status} from './ui.js';

export function batch(root,{drafts,onOpen,onSaved}) {
  let selected=null,group='',ack=false,runner,broken=false,acting=false;
  const reads=new Latest(),feedback=messageNode(),progress=messageNode(),list=el('div'),pinned=el('div'),selectedNote=note('Выберите чек-лист сверху.');
  const groupField=select('Группа для оценки',[['','Выберите группу']],group,v=>{group=v;});
  const groupInput=groupField.querySelector('select');
  const create=button('Подготовить пакет',()=>action(()=>runner.create(group,selected)));
  const run=button('Запустить / продолжить',()=>action(()=>runner.resume(ack)),'primary');
  const pause=button('Пауза после текущего диалога',()=>{try{runner.pause();status(feedback,'Пауза запрошена. Текущая обработка не отменяется; следующий диалог не отправится.');}catch{status(feedback,'Пауза запрошена, но список не сохранён. Сохраните идентификатор запроса; после перезагрузки сверяйте ledger.','error');}});
  const refresh=button('Проверить статусы',()=>action(()=>runner.refresh()));
  const acknowledgement=field('Я проверил статусы и допускаю повторную стоимость; разрешаю продолжение при неизвестном исходе',false,v=>{ack=v;render();},{type:'checkbox'});
  const forget=button('Убрать завершённый пакет',()=>{
    if(window.confirm('Удалить локальный список завершённого пакета? Оценки и журнал запросов останутся в Java.'))action(()=>runner.forget(true));
  },'quiet');
  root.append(el('div',{class:'panel'},el('h2',{text:'Массовая оценка'}),
    note('Последовательно, один диалог за раз. Используется выбранная сверху версия чек-листа. Состав группы фиксируется перед запуском; новые импорты не добавляются в текущий batch.'),
    note('Для каждого диалога и снимка чек-листа требуется серверное разрешение. Название группы не даёт права передавать данные модели.'),
    el('div',{class:'toolbar'},groupField,button('Обновить группы',loadGroups),create),selectedNote,pinned,
    el('div',{class:'toolbar'},run,pause,refresh,forget),acknowledgement,feedback,progress,
    note('Список хранится в этом браузере для этого адреса: только ID, UUID, версия и статусы. После перезагрузки автоматической отправки нет. Не очищайте данные сайта и не меняйте Java SQLite, пока batch не завершён. Пауза и закрытие вкладки не отменяют текущую обработку.'),list));
  function render(){
    const m=runner?.manifest,busy=!!runner?.running||acting;
    create.disabled=broken||busy||!!m||!selected;groupInput.disabled=busy||!!m;
    run.disabled=broken||busy||!m||!m.items.some(i=>!i.attempts.length);
    pause.disabled=!runner?.running||!m;refresh.disabled=broken||busy||!m;
    forget.disabled=broken||busy||!m||m.items.some(i=>!['succeeded','failed','conflict'].includes(itemState(i)));
    acknowledgement.querySelector('input').disabled=busy;
    if(!m){pinned.replaceChildren();progress.textContent='Пакет ещё не создан.';list.replaceChildren();return;}
    pinned.replaceChildren(badge(m.group),badge(`${m.checklist_key} / v${m.checklist_version}`),note(`Пакет · ${busy?(runner.stopRequested?'пауза запрошена':'выполняется'):m.paused?'остановлен; продолжение только вручную':'незавершённый запуск или другая вкладка; сверьте статусы'}`));
    const counts={queued:0,succeeded:0,failed:0,pending:0,unknown:0};
    for(const item of m.items){const s=itemState(item);counts[s==='conflict'?'failed':['sending','pending'].includes(s)?'pending':['unresolved','not_found'].includes(s)?'unknown':s]++;}
    const done=counts.succeeded+counts.failed;
    status(progress,`Всего ${m.items.length} · завершено ${done} · успешно ${counts.succeeded} · ошибок ${counts.failed} · в работе ${counts.pending} · неизвестно ${counts.unknown} · ожидают ${counts.queued}`);
    const bar=el('progress',{max:m.items.length,value:done,'aria-label':'Прогресс batch'});
    list.replaceChildren(bar,...m.items.map(item=>{
      const a=lastAttempt(item),s=itemState(item);
      const card=el('article',{class:'batch-item','data-batch-conversation':item.conversation_id,'data-batch-state':s},
        el('h3',{class:'inline-id',text:item.conversation_id}),badge(({queued:'Ожидает',sending:'Отправляется',pending:'Выполняется',succeeded:'Готово',failed:'Ошибка',unknown:'Исход неизвестен',not_found:'Запрос не найден',unresolved:'Нужна проверка',conflict:'Конфликт'})[s]??s));
      if(a){
        card.append(el('details',{},el('summary',{text:'Подробности запроса'}),note(`request_id: ${a.request_id}`)));
        if(a.code)card.append(note(new ApiError(0,a.code).message));
        if(['unknown','not_found','unresolved','sending','pending'].includes(s))card.append(note('Исход требует сверки с Java. Никакого автоматического повторного POST. 404 после потери связи не доказывает отмену обработки.'));
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
    status(feedback,'Сверяем пакет с журналом запросов…','loading');
    try{await work();status(feedback,'Состояние пакета сохранено. Отправлялись только явно запущенные элементы.');await onSaved();}
    catch(error){status(feedback,error instanceof Error&&error.name==='Error'||error instanceof ApiError?error.message:'Не удалось прочитать или сохранить список. Отправка остановлена; проверьте UUID в Java.','error');}
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
  }catch{broken=true;status(feedback,'Локальный список недоступен или повреждён. Массовая оценка заблокирована; сохраните идентификатор запроса и проверьте историю в Java.','error');}
  window.addEventListener('storage',event=>{if(event.key!==BATCH_KEY||runner?.running)return;try{runner.load();}catch{broken=true;status(feedback,'Локальный список изменён другой вкладкой и не может быть прочитан. Отправка заблокирована.','error');}render();});
  loadGroups();render();
  return {checklist(value){selected=value;selectedNote.textContent=value?`Для нового пакета: ${value.key} / v${value.version}. Существующий пакет сохраняет свою версию.`:'Выберите конкретную версию чек-листа сверху.';render();}};
}
