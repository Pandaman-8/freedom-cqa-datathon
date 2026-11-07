import {request, getChecklist, pathId} from './api.js';
import {Latest} from './state.js';
import {display} from './json.js';
import {answerEditor, blankAnswer, validateAnswers} from './answers.js';
import {review} from './review.js';
import {transcript} from './conversations.js';
import {el, button, select, note, badge, messageNode, formShell, mutation, status} from './ui.js';
export function manual(root,{drafts,onSaved}) {
  let conversation=null, checklist=null, activeKey=null;
  function render() {
    if(!conversation||!checklist) {activeKey=null;root.replaceChildren(el('h2',{text:'Ручная оценка'}),note('Выберите диалог и конкретную версию чек-листа.'));return;}
    const source=conversation, pinned=checklist;
    const key='manual:'+JSON.stringify([source.id,pinned.key,String(pinned.version)]); activeKey=key;
    const entry=drafts.get(key,()=>pinned.criteria.map(blankAnswer));
    const {form,fields,feedback}=formShell('Ручная оценка'); form.dataset.draftKey=key;
    fields.append(note(`${source.id} · ${pinned.key} / v${pinned.version}. Оценивается оператор; bot/system — контекст.`));
    pinned.criteria.forEach((c,i)=>fields.append(answerEditor(c,entry.value[i],source,()=>drafts.touch(key))));
    fields.append(el('button',{type:'submit',text:'Сохранить ручную оценку'}));
    form.addEventListener('submit',event=>{
      event.preventDefault(); mutation(form,feedback,drafts,async()=>{
        validateAnswers(pinned,entry.value,source);
        const saved=await request('/api/evaluations/manual',{method:'POST',body:{conversation_id:source.id,checklist_key:pinned.key,checklist_version:pinned.version,answers:entry.value}});
        drafts.clean(key);
        // Successful POST is followed by GET of the saved snapshot in the results workspace.
        status(feedback,`Сохранена ручная оценка ${saved.id}.`);
        if(activeKey===key) await onSaved(saved.id);
      });
    });
    const ai=el('div',{class:'notice'},'AI evaluation будет доступна после T13. Java возвращает 501 EVALUATOR_UNCONFIGURED.');
    root.replaceChildren(ai,form);
  }
  render();
  return {conversation(value){conversation=value;render();},checklist(value){checklist=value;render();}};
}
function scoreCard(title, score, answers, checklist, jump) {
  const card=el('section',{class:'panel score-card','aria-label':title},el('h3',{text:title}),
    el('div',{class:'score-number',text:display(score.overall_score)}),note(`overall_score / max_score ${display(score.max_score)}`));
  const meta=el('dl',{class:'score-meta'},el('dt',{text:'applicable_weight'}),el('dd',{text:display(score.applicable_weight)}),
    el('dt',{text:'critical_violation'}),el('dd',{class:score.critical_violation?'critical':'',text:String(score.critical_violation)}),
    el('dt',{text:'critical_criterion_ids'}),el('dd',{text:score.critical_criterion_ids.join(', ')||'—'}));card.append(meta);
  const sections=el('table',{},el('thead',{},el('tr',{},...['Раздел','Earned','Weight','Percent'].map(t=>el('th',{text:t})))));
  const sectionBody=el('tbody');
  for(const s of score.sections) sectionBody.append(el('tr',{},el('td',{text:checklist.sections.find(x=>x.id===s.section_id)?.title??s.section_id}),
    el('td',{text:display(s.earned_points)}),el('td',{text:display(s.applicable_weight)}),el('td',{text:display(s.percent)})));
  sections.append(sectionBody);card.append(el('div',{class:'table-scroll'},sections));
  for(const row of score.criteria) {
    const criterion=checklist.criteria.find(c=>c.id===row.criterion_id), answer=answers.find(a=>a.criterion_id===row.criterion_id);
    const details=el('details',{'data-score-criterion':row.criterion_id},el('summary',{text:`${row.criterion_id} · ${criterion?.title??''} — ${row.answer==='na'?'N/A':row.answer}${row.value===null?'':' '+row.value}`}));
    const numbers=el('dl',{class:'score-meta'});
    for(const [label,value] of [['configured_weight',row.configured_weight],['effective_weight',row.effective_weight],['earned_points',row.earned_points],['raw_points',row.raw_points],['is_critical',row.is_critical]]) numbers.append(el('dt',{text:label}),el('dd',{text:display(value)}));
    details.append(numbers,el('p',{class:'source-text',text:answer.explanation}));
    if(row.answer==='na') details.append(note(`N/A исключает вес из знаменателя. ${criterion.na_rule}`));
    for(const ev of answer.evidence) details.append(button(`${ev.message_id} · ${ev.quote}`,()=>jump(ev.message_id,ev.quote),'evidence-link'));
    card.append(details);
  }
  return card;
}
export function evaluations(root,{drafts,canSwitch,onList}) {
  let selectedId=null, listRows=[]; const reads=new Latest(), listReads=new Latest();
  const feedback=messageNode(), list=el('div',{class:'evaluation-list'}), detail=el('div');
  let conversationFilter='';
  const filter=select('Оценки диалога',[['','Все диалоги']], '',value=>{conversationFilter=value;loadList();});
  root.append(el('div',{class:'panel'},el('div',{class:'toolbar'},filter,button('Обновить оценки',loadList)),list),feedback,detail);
  async function loadList() {
    const ticket=listReads.next();
    try {
      const rows=await request('/api/evaluations'+(conversationFilter?'?conversation_id='+pathId(conversationFilter):''),ticket);
      if(!ticket.current())return; listRows=rows;
      list.replaceChildren(...rows.map(e=>el('button',{type:'button',class:'list-row','aria-pressed':e.id===selectedId,onclick:()=>open(e.id)},
        el('strong',{text:`${e.conversation_id} · ${display(e.final_score.overall_score)} · ${e.origin}`}),
        el('small',{text:`${e.checklist_key} / v${e.checklist_version} · ${e.review_status} · ${e.created_at} · ${e.id}`}))));
      if(!rows.length) list.append(note('Сохранённых оценок нет. Создайте ручную оценку в диалоге.'));
      if(!conversationFilter) onList(rows);
    } catch(e) {if(ticket.current())status(feedback,e.message,'error');}
  }
  async function open(id, message='', internal=false) {
    if(!internal&&!canSwitch())return;
    selectedId=id; const ticket=reads.next(); detail.replaceChildren();status(feedback,'Загружаем сохранённую оценку…','loading');
    try {
      const evaluation=await request('/api/evaluations/'+pathId(id),ticket);
      const [checklist,source]=await Promise.all([getChecklist(evaluation.checklist_key,evaluation.checklist_version,ticket),request('/api/conversations/'+pathId(evaluation.conversation_id),ticket)]);
      if(!ticket.current())return;
      const view=transcript(source); const transcriptPanel=el('details',{class:'panel'},el('summary',{text:'Исходный transcript и evidence'}),view.node);
      const jump=(messageId,quote)=>{transcriptPanel.open=true;return view.jump(messageId,quote);};
      detail.append(el('div',{class:'panel'},el('h2',{class:'inline-id',text:evaluation.conversation_id}),
        el('div',{class:'toolbar'},badge(evaluation.origin),badge(evaluation.review_status),badge(`${evaluation.checklist_key} / v${evaluation.checklist_version}`)),
        note(`Evaluation: ${evaluation.id} · ${evaluation.created_at}`),
        note(`contract_version: ${evaluation.contract_version} · scoring_version: ${evaluation.scoring_version} · review_revision: ${evaluation.review_revision}`),
        note('Баллы получены из Java. earned_points — нормализованный вклад; raw_points — исходные взвешенные баллы. N/A исключает вес; critical flag не обнуляет общий балл.'),
        button('Перечитать выбранную оценку',()=>open(id))),
        el('div',{class:'result-scores'},scoreCard('Original',evaluation.original_score,evaluation.original_answers,checklist,jump),scoreCard('Final',evaluation.final_score,evaluation.final_answers,checklist,jump)),transcriptPanel,
        el('div',{class:'panel'},review(evaluation,checklist,source,{drafts,jump,reload:async(target,msg)=>{
          if(selectedId!==target)return;await open(target,msg,true);await loadList();
        }})));
      status(feedback,message||'Сохранённая оценка получена из Java.',message?.includes('CONFLICT')||message?.includes('Конфликт')?'error':'ok');
    } catch(e){if(ticket.current()){status(feedback,e.message,'error');detail.append(button('Повторить чтение оценки',()=>open(id)));}}
  }
  return {load:loadList,open:(id)=>open(id,'',true), conversations(rows){
    const input=filter.querySelector('select');input.replaceChildren(el('option',{value:'',text:'Все диалоги'}),...rows.map(r=>el('option',{value:r.id,text:r.id})));input.value=conversationFilter;
  }};
}
