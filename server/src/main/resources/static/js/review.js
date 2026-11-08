import {answerText, reviewText} from './presentation.js';
import {request, pathId} from './api.js';
import {display, integer} from './json.js';
import {answerEditor, copiedAnswer, validateAnswers} from './answers.js';
import {el, button, field, select, note, badge, formShell, mutation, status} from './ui.js';
export function review(evaluation, checklist, conversation, {drafts, reload, jump}) {
  const root=el('div',{},el('h3',{text:'Апелляции'}),note('Выберите критерий и объясните, что нужно пересмотреть.'));
  const appealKey='appeal:'+evaluation.id;
  const appeal=drafts.get(appealKey,()=>({criterion_id:'',comment:''})).value;
  const create=formShell('Открыть апелляцию'); create.form.dataset.draftKey=appealKey;
  create.fields.append(select('Критерий апелляции',[['','Выберите критерий'],...checklist.criteria.map(c=>[c.id,c.title])],appeal.criterion_id,v=>{appeal.criterion_id=v;drafts.touch(appealKey);}),
    field('Комментарий апелляции',appeal.comment,v=>{appeal.comment=v;drafts.touch(appealKey);},{required:true,multiline:true}),el('button',{type:'submit',text:'Отправить апелляцию'}));
  create.form.addEventListener('submit',event=>{
    event.preventDefault(); mutation(create.form,create.feedback,drafts,async()=>{
      if(!appeal.criterion_id||!appeal.comment.trim()||[...appeal.comment].length>3000) throw new Error('Выберите критерий и укажите комментарий до 3000 символов.');
      await request('/api/evaluations/'+pathId(evaluation.id)+'/appeals',{method:'POST',body:appeal});
      drafts.remove(appealKey); await reload(evaluation.id,'Апелляция сохранена. Получена актуальная ревизия.');
    },()=>reload(evaluation.id,'Конфликт апелляции. Данные перечитаны, черновик сохранён. Автоматического повтора не было.'));
  });
  root.append(create.form);
  if(!evaluation.appeals.length) root.append(note('Апелляций пока нет.'));
  for(const a of evaluation.appeals) {
    const card=el('article',{class:'appeal-card','data-appeal-id':a.id,'data-appeal-criterion':a.criterion_id},el('div',{class:'toolbar'},badge(reviewText(a.status)),badge(checklist.criteria.find(c=>c.id===a.criterion_id)?.title??a.criterion_id)),
      el('p',{class:'source-text',text:a.comment}),note(`Создана: ${a.created_at}`));
    if(a.status==='resolved') {
      card.append(el('p',{text:`Решение: ${a.decision==='confirm'?'подтверждено':'ответ изменён'}`}),el('p',{class:'source-text',text:a.reason}),note(`Завершена: ${a.resolved_at}`));
      if(a.replacement) {
        card.append(note(`Новый ответ: ${answerText(a.replacement)}`),el('p',{class:'source-text',text:a.replacement.explanation}));
        for(const e of a.replacement.evidence) card.append(button(`${e.message_id} · ${e.quote}`,()=>jump(e.message_id,e.quote),'evidence-link'));
      }
    } else {
      const key='review:'+a.id, criterion=checklist.criteria.find(c=>c.id===a.criterion_id);
      const draft=drafts.get(key,()=>({decision:'confirm',reason:'',replacement:copiedAnswer(evaluation.final_answers.find(v=>v.criterion_id===a.criterion_id))})).value;
      const shell=formShell('Решение: '+criterion.title); shell.form.dataset.draftKey=key;
      function fields() {
        shell.fields.replaceChildren(select('Решение',[['confirm','Подтвердить ответ'],['change','Изменить ответ']],draft.decision,v=>{draft.decision=v;drafts.touch(key);fields();}),
          field('Причина решения',draft.reason,v=>{draft.reason=v;drafts.touch(key);},{required:true,multiline:true}));
        if(draft.decision==='change') shell.fields.append(answerEditor(criterion,draft.replacement,conversation,()=>drafts.touch(key)));
        shell.fields.append(el('button',{type:'submit',text:'Сохранить решение'}));
      }
      fields(); shell.form.addEventListener('submit',event=>{
        event.preventDefault(); mutation(shell.form,shell.feedback,drafts,async()=>{
          if(!draft.reason.trim()||[...draft.reason].length>3000) throw new Error('Укажите причину решения до 3000 символов.');
          if(draft.decision==='change') validateAnswers({criteria:[criterion]},[draft.replacement],conversation);
          const revision=integer(evaluation.review_revision,0n);
          await request('/api/appeals/'+pathId(a.id)+'/resolve?expected_revision='+revision,{method:'POST',body:{decision:draft.decision,reason:draft.reason,replacement:draft.decision==='change'?draft.replacement:null}});
          drafts.remove(key); await reload(evaluation.id,'Решение сохранено. Исходная оценка сохранена; итог пересчитан.');
        },()=>reload(evaluation.id,'Конфликт: данные перечитаны. Проверьте сохранённый черновик и новое состояние; автоматического повтора не было.'));
      });
      card.append(shell.form);
    }
    root.append(card);
  }
  // A concurrent reviewer may already have resolved this appeal. Keep its unsent draft visible.
  for(const a of evaluation.appeals.filter(a=>a.status==='resolved')) {
    const key='review:'+a.id, retained=drafts.items.get(key);
    if(retained?.dirty) root.append(el('div',{class:'notice','data-state':'error'},
      el('p',{text:`Сохранён черновик для уже закрытой апелляции ${a.criterion_id}. Повторная отправка заблокирована.`}),
      el('p',{class:'source-text',text:retained.value.reason}),
      el('p',{class:'source-text',text:retained.value.replacement.explanation}),
      button('Удалить этот черновик',()=>{if(window.confirm('Удалить несохранённое решение?')){drafts.remove(key);reload(evaluation.id);}},'danger')));
  }
  return root;
}
