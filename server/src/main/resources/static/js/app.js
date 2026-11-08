import {Drafts, Latest} from './state.js';
import {el} from './ui.js';
import {conversations} from './conversations.js';
import {checklists} from './checklists.js';
import {manual, evaluations} from './evaluations.js';
import {datasets} from './datasets.js';
import {batch} from './batch.js';
import {request, ApiError} from './api.js';
import {aiStatusText} from './presentation.js';
const draftStatus=document.querySelector('#draft-status');
const drafts=new Drafts(()=>{
  draftStatus.textContent=drafts.pending?'Сохранение выполняется. Дождитесь результата перед сменой контекста.':
    `Несохранённых черновиков: ${drafts.count()}. Переключение экранов сохраняет их в памяти; закрытие страницы — нет.`;
});
window.addEventListener('beforeunload',event=>{if(drafts.count()||drafts.pending||drafts.unknown.size){event.preventDefault();event.returnValue='';}});
function canSwitch(){if(drafts.pending){draftStatus.textContent='Дождитесь завершения сохранения. Текущий черновик защищён.';return false;}return true;}
const names={overview:'Обзор',conversations:'Диалоги',checklists:'Чек-листы',results:'Результаты и апелляции',datasets:'Загрузка данных',batch:'Массовая оценка'};
function show(name,internal=false){
  if(!Object.hasOwn(names,name)||(!internal&&!canSwitch()))return;
  for(const panel of document.querySelectorAll('[data-panel]'))panel.hidden=panel.dataset.panel!==name;
  for(const b of document.querySelectorAll('[data-view]')){
    if(b.dataset.view===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
  }
  document.querySelector('#page-title').textContent=names[name];
  history.replaceState(null,'','#'+name); window.scrollTo({top:0,behavior:'instant'});
}
for(const b of document.querySelectorAll('[data-view]'))b.addEventListener('click',()=>show(b.dataset.view));
document.querySelector('.brand').addEventListener('click',event=>{event.preventDefault();show('overview');});
const totals={conversations:null,checklists:null,evaluations:null};
function counts(key,rows){totals[key]=rows.length;document.querySelector('#overview-counts').replaceChildren(...Object.entries({conversations:'Диалогов в SQLite',checklists:'Чек-листов (latest)',evaluations:'Сохранённых оценок'}).map(([k,label])=>el('div',{class:'metric'},el('strong',{text:totals[k]??'—'}),el('span',{text:label}))));}
const results=evaluations(document.querySelector('#evaluation-workspace'),{drafts,canSwitch,onList:rows=>counts('evaluations',rows)});
const batches=batch(document.querySelector('#batch-workspace'),{drafts,onOpen:async id=>{show('results',true);await results.open(id);},onSaved:()=>results.load()});
const composer=manual(document.querySelector('#manual-workspace'),{drafts,onSaved:async id=>{show('results',true);await results.open(id);await results.load();}});
const chats=conversations(document.querySelector('#conversation-workspace'),{canSwitch,composerNode:document.querySelector('#manual-workspace'),onSelect:source=>composer.conversation(source),onList:rows=>{counts('conversations',rows);results.conversations(rows);}});
const lists=checklists(document.querySelector('#checklist-picker'),document.querySelector('#checklist-editor'),{drafts,canSwitch,onSelect:list=>{composer.checklist(list);batches.checklist(list);},onEvaluate:()=>{show('conversations');document.querySelector('#manual-workspace')?.scrollIntoView({block:'center'});},onList:rows=>counts('checklists',rows)});
const imports=datasets({drafts,onImported:()=>chats.load()});
const healthReads=new Latest();
async function health(){
  const ticket=healthReads.next(), card=document.querySelector('#connection'), label=document.querySelector('#connection-status'), detail=document.querySelector('#connection-detail'), retry=document.querySelector('#check-connection');
  retry.disabled=true;card.dataset.state='checking';label.textContent='Проверяем…';
  const timer=setTimeout(()=>healthReads.controller.abort(),5000);
  try{
    const response=await fetch('/api/health',{cache:'no-store',signal:ticket.signal,headers:{Accept:'application/json'}});
    const data=await response.json();if(!ticket.current())return;
    if(!response.ok||data.status!=='ok'||data.service!=='freedom-cqa-java')throw new Error();
    card.dataset.state='ok';label.textContent='Java доступен';document.querySelector('#service-version').textContent=data.version;
    detail.textContent='Ручная оценка доступна.';
    const ai=await request('/api/ai/status',ticket);if(!ticket.current())return;
    document.querySelector('#ai-connection').textContent=aiStatusText(ai);
    if(ai.reason)detail.textContent=new ApiError(0,ai.reason).message;
  }catch{if(ticket.current()){if(card.dataset.state!=='ok'){card.dataset.state='error';label.textContent='Java недоступен';}document.querySelector('#ai-connection').textContent='Готовность ИИ не подтверждена';detail.textContent='Проверьте запуск сервисов и повторите чтение.';}}
  finally{clearTimeout(timer);if(ticket.current())retry.disabled=false;}
}
document.querySelector('#check-connection').addEventListener('click',health);
show(location.hash.slice(1)||'overview');health();chats.load();lists.load();results.load();imports.load();drafts.changed();
