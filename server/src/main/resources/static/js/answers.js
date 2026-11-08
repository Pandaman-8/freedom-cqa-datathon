import {display, clone, equalDecimal} from './json.js';
import {el, button, field, select, note, exactEvidence} from './ui.js';
export const blankAnswer = criterion => ({criterion_id:criterion.id,answer:'',value:null,explanation:'',evidence:[]});
// Shared manual/review composer; the user supplies every answer and every quote.
export function answerEditor(criterion, answer, conversation, changed) {
  const node=el('div',{class:'answer-card','data-criterion-id':criterion.id});
  function render() {
    const choices=[['','Выберите ответ']];
    if(criterion.kind==='scale') criterion.levels.forEach((l,i)=>choices.push(['level:'+i,`${display(l.value)} — ${l.description}`]));
    else choices.push(['yes','Да'],['no','Нет']);
    if(criterion.allow_na) choices.push(['na','N/A']);
    const levelIndex=criterion.levels.findIndex(l=>equalDecimal(l.value,answer.value));
    const selected=answer.answer==='scale'?'level:'+levelIndex:answer.answer;
    node.replaceChildren(el('h4',{text:criterion.title}),note(criterion.instruction),note(`Тип: ${{binary:'Да / нет',scale:'Шкала',flag:'Флаг нарушения'}[criterion.kind]} · Вес: ${display(criterion.weight)}`));
    if(criterion.allow_na) node.append(note(`N/A: ${criterion.na_rule}`));
    node.append(select('Ответ',choices,selected,v=>{
      answer.answer=v.startsWith('level:')?'scale':v;
      answer.value=answer.answer==='scale'?criterion.levels[Number(v.slice(6))].value:null; changed(); render();
    }),field('Обоснование',answer.explanation,v=>{answer.explanation=v;changed();},{required:true,multiline:true}));
    answer.evidence.forEach((ev,index)=>{
      const preview=el('p',{class:'quote-preview',text:conversation.messages.find(m=>m.id===ev.message_id)?.text??'Выберите исходное сообщение.'});
      const quoteField=field('Точная цитата',ev.quote,v=>{ev.quote=v;changed();},{required:true,multiline:true});
      const row=el('div',{class:'evidence-row'},select('Сообщение',[['','Выберите сообщение'],...conversation.messages.map(m=>[m.id,`${m.id} · ${m.speaker} · ${m.timestamp}`])],ev.message_id,v=>{
        ev.message_id=v; changed(); preview.textContent=conversation.messages.find(m=>m.id===v)?.text??'';
      }),preview,quoteField);
      row.append(button('Взять текст сообщения',()=>{
        const m=conversation.messages.find(m=>m.id===ev.message_id); if(!m) return;
        ev.quote=m.text;quoteField.querySelector('textarea').value=m.text;changed();
      }),button('Вставить выделенный фрагмент',()=>{
        const text=window.getSelection()?.toString()??'';
        if(text&&conversation.messages.find(m=>m.id===ev.message_id)?.text.includes(text)) {ev.quote=text;quoteField.querySelector('textarea').value=text;changed();}
      }),button('Удалить доказательство',()=>{answer.evidence.splice(index,1);changed();render();},'danger'));
      node.append(row);
    });
    node.append(button('Добавить доказательство',()=>{answer.evidence.push({message_id:'',quote:''});changed();render();}));
  }
  render(); return node;
}
export function validateAnswers(checklist, answers, conversation) {
  if(answers.length!==checklist.criteria.length||answers.some(a=>!a.answer||!a.explanation.trim()||!exactEvidence(conversation,a.evidence)))
    throw new Error('Заполните каждый ответ, обоснование и доказательство: непустая точная цитата из выбранного message_id, без изменения пробелов и Unicode.');
}
export const copiedAnswer = value => clone(value);
