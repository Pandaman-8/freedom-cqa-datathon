import {request, getChecklist, pathId} from './api.js';
import {Latest} from './state.js';
import {display} from './json.js';
import {answerEditor, blankAnswer, validateAnswers} from './answers.js';
import {review} from './review.js';
import {automatic} from './auto.js';
import {answerText, originText, reviewText, assessmentChanged} from './presentation.js';
import {transcript} from './conversations.js';
import {el, button, select, note, badge, messageNode, formShell, mutation, status} from './ui.js';
export function manual(root,{drafts,onSaved}) {
  let conversation=null, checklist=null, activeKey=null, auto=null;
  function render() {
    auto?.dispose();
    if(!conversation||!checklist) {activeKey=null;root.replaceChildren(note('Выберите диалог и версию чек-листа для оценки.'));return;}
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
        status(feedback,'Ручная оценка сохранена.');
        if(activeKey===key) await onSaved(saved.id);
      });
    });
    auto=automatic(source,pinned,{drafts,onSaved});
    root.replaceChildren(auto.node,el('details',{'data-manual':'',open:entry.dirty},el('summary',{text:'Оценить вручную'}),form));
  }
  render();
  return {conversation(value){conversation=value;render();},checklist(value){checklist=value;render();}};
}
function scoreCard(title, score, answers, checklist, jump) {
  const card=el('section',{class:'panel score-card','aria-label':title},el('h3',{text:title}),
    el('div',{class:'score-number',text:score.overall_score===null?'Нет применимых критериев':`${display(score.overall_score)} / ${display(score.max_score)}`}));
  if(score.critical_violation) card.append(el('p',{class:'critical',text:'Обнаружено грубое нарушение. Флаг учитывается отдельно от балла.'}));
  const meta=el('details',{},el('summary',{text:'Подробности расчёта'}),note(`Применимый вес: ${display(score.applicable_weight)}. N/A исключён из знаменателя.`),note(`Критерии грубых нарушений: ${score.critical_criterion_ids.join(', ')||'нет'}`));
  const sections=el('table',{},el('thead',{},el('tr',{},...['Раздел','Баллы','Вес','Процент'].map(t=>el('th',{text:t})))));
  const sectionBody=el('tbody');
  for(const s of score.sections) sectionBody.append(el('tr',{},el('td',{text:checklist.sections.find(x=>x.id===s.section_id)?.title??s.section_id}),
    el('td',{text:display(s.earned_points)}),el('td',{text:display(s.applicable_weight)}),el('td',{text:display(s.percent)})));
  sections.append(sectionBody);meta.append(el('div',{class:'table-scroll'},sections));card.append(meta);
  for(const row of score.criteria) {
    const criterion=checklist.criteria.find(c=>c.id===row.criterion_id), answer=answers.find(a=>a.criterion_id===row.criterion_id);
    const details=el('article',{class:'criterion-result','data-score-criterion':row.criterion_id},
      el('div',{class:'section-heading'},el('h4',{text:criterion?.title??row.criterion_id}),badge(answerText(row))),
      note(row.answer==='na'?'N/A · вес исключён':row.kind==='flag'||criterion.kind==='flag'?'Отдельный флаг':`Баллы: ${display(row.earned_points)} · вес: ${display(row.configured_weight)}`));
    const numbers=el('dl',{class:'score-meta'});
    for(const [label,value] of [['Вес в чек-листе',row.configured_weight],['Эффективный вес',row.effective_weight],['Нормализованные баллы',row.earned_points],['Исходные баллы',row.raw_points]]) numbers.append(el('dt',{text:label}),el('dd',{text:display(value)}));
    details.append(el('p',{class:'source-text',text:answer.explanation}),el('details',{},el('summary',{text:'Подробности'}),note(`Критерий: ${row.criterion_id}`),numbers));
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
      list.replaceChildren(...rows.map(e=>el('button',{type:'button',class:'list-row','data-evaluation-id':e.id,'aria-pressed':e.id===selectedId,onclick:()=>open(e.id)},
        el('strong',{text:`${e.conversation_id} · ${display(e.final_score.overall_score)} / 100 · ${originText(e.origin)}`}),
        el('small',{text:`${e.checklist_key} / v${e.checklist_version} · ${reviewText(e.review_status)} · ${e.created_at}`}))));
      if(!rows.length) list.append(note('Сохранённых оценок нет. Откройте диалог и выберите «Оценить с ИИ» или ручную оценку.'));
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
      const view=transcript(source); const transcriptPanel=el('details',{class:'panel'},el('summary',{text:'Диалог и доказательства'}),view.node);
      const jump=(messageId,quote)=>{transcriptPanel.open=true;return view.jump(messageId,quote);};
      detail.append(el('div',{class:'panel'},el('h2',{class:'inline-id',text:evaluation.conversation_id}),
        el('div',{class:'toolbar'},badge(originText(evaluation.origin)),badge(reviewText(evaluation.review_status)),badge(`${checklist.title} / v${evaluation.checklist_version}`)),
        el('details',{},el('summary',{text:'Подробности оценки'}),note(`Evaluation: ${evaluation.id} · ${evaluation.created_at}`),
        note(`contract_version: ${evaluation.contract_version} · scoring_version: ${evaluation.scoring_version} · review_revision: ${evaluation.review_revision}`),
        note('Баллы рассчитывает Java. N/A исключает вес; флаг грубого нарушения не обнуляет общий балл.')),
        button('Перечитать выбранную оценку',()=>open(id))),
        el('div',{class:'result-scores'},scoreCard('Итоговая оценка',evaluation.final_score,evaluation.final_answers,checklist,jump),
          assessmentChanged(evaluation)?el('details',{'data-original':''},el('summary',{text:`До проверки: ${display(evaluation.original_score.overall_score)} / 100`}),scoreCard('Исходная оценка',evaluation.original_score,evaluation.original_answers,checklist,jump)):null),transcriptPanel,
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
