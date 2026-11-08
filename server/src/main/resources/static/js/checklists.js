import {request, getChecklist, pathId} from './api.js';
import {decimal, display, integer} from './json.js';
import {Latest} from './state.js';
import {el, button, field, select, note, status, messageNode, mutation} from './ui.js';
const editable = c => ({title:c.title, description:c.description, sections:c.sections.map(s => ({...s})),
  criteria:c.criteria.map(r => ({...r, weight:display(r.weight), levels:r.levels.map(l => ({...l,value:display(l.value)}))}))});
const blank = () => ({title:'', description:'', sections:[], criteria:[]});
export function checklists(picker, editor, {drafts, onSelect, onList, canSwitch, onEvaluate}) {
  let latest = [], selected = null, activeDraft = null, loading = false;
  const reads = new Latest(), listReads = new Latest(); const feedback = messageNode();
  const expanded=new WeakSet(), advanced=new WeakSet();
  const selectedSummary=el('p',{class:'picker-summary'});
  const keySelect = select('Чек-лист', [['','Выберите чек-лист']], '', key => load(key));
  const versionField = field('Версия (пусто = последняя)', '', () => {}, {class:'version', inputMode:'numeric'});
  const keyInput = keySelect.querySelector('select'), versionInput = versionField.querySelector('input');
  picker.append(el('div', {class:'picker-row'}, keySelect),selectedSummary,
    el('details',{class:'picker-history'},el('summary',{text:'Версии и обновление списка'}),
      el('div',{class:'toolbar'},versionField,button('Открыть версию', () => load(keyInput.value, versionInput.value || undefined)),
        button('Последняя версия', () => load(keyInput.value)),button('Обновить чек-листы',loadList,'quiet'))),feedback);
  function touch() { drafts.touch(activeDraft); }
  async function loadList() {
    const ticket = listReads.next();
    try {
      const rows = await request('/api/checklists', ticket); if (!ticket.current()) return;
      latest = rows; keyInput.replaceChildren(...rows.map(c => el('option', {value:c.key, text:c.title})));
      if (selected) keyInput.value = selected.key;
      onList(rows); if (!selected && !loading && !activeDraft && rows.length) await load(rows[0].key);
    } catch(e) { if(ticket.current()) status(feedback,e.message,'error'); }
  }
  async function load(key, version) {
    if (!key || !canSwitch()) { if(selected) keyInput.value=selected.key; return; }
    try { if(version !== undefined) integer(version); } catch(e) { status(feedback,e.message,'error'); return; }
    const ticket = reads.next(); selected=null; loading=true; onSelect(null); editor.replaceChildren(note('Загружаем чек-лист…'));
    selectedSummary.textContent='';status(feedback, 'Загружаем выбранную версию…', 'loading');
    try {
      const [checklist, head] = await Promise.all([getChecklist(key,version,ticket), getChecklist(key,undefined,ticket)]);
      if (!ticket.current()) return;
      selected=checklist; keyInput.value=key; versionInput.value=String(checklist.version);
      activeDraft='checklist:' + JSON.stringify([key,String(checklist.version)]);
      drafts.get(activeDraft, () => ({key,mode:'version',baseVersion:String(head.version),originVersion:String(checklist.version),draft:editable(checklist)}));
      status(feedback, `Выбрано: ${key} / v${checklist.version}. Последняя: v${head.version}. Исторические версии неизменны.`);
      selectedSummary.textContent=`Версия ${checklist.version} · ${checklist.criteria.length} критериев`;
      renderEditor(); onSelect(checklist);
    } catch(e) { if(ticket.current()) { status(feedback,e.message,'error'); editor.replaceChildren(note('Версия не загружена. Повторите чтение.')); } }
    finally { if(ticket.current()) loading=false; }
  }
  function newChecklist() {
    if (!canSwitch()) return;
    activeDraft='checklist:new'; drafts.get(activeDraft, () => ({key:'',mode:'create',draft:blank()})); renderEditor();
  }
  function renderEditor() {
    const draftKey=activeDraft, entry=drafts.items.get(draftKey), data=entry.value, d=data.draft;
    const form = el('form', {'data-draft-key':draftKey}), fields = el('fieldset'), output=messageNode();
    form.addEventListener('invalid',event=>{for(let parent=event.target.parentElement;parent&&parent!==form;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;},true);
    const edit = (obj,key,value) => { obj[key]=value; drafts.touch(draftKey); };
    const top=el('div', {class:'section-heading'}, el('h2', {text:data.mode==='create'?'Новый чек-лист':d.title}), button('Создать новый чек-лист',newChecklist));
    const baseline=note(data.mode==='create'?'Новый чек-лист начнётся с версии v1.':`Источник v${data.originVersion}. Сохранение добавит версию после последней версии v${data.baseVersion}; источник не изменится.`);
    if (data.mode==='create') fields.append(field('Ключ нового чек-листа', data.key, v => edit(data,'key',v), {required:true}));
    fields.append(el('details',{class:'editor-advanced',open:data.mode==='create'},el('summary',{text:'Название и описание чек-листа'}),field('Название чек-листа',d.title,v=>edit(d,'title',v),{required:true}),field('Описание чек-листа',d.description,v=>edit(d,'description',v),{multiline:true})));
    const sections=el('details', {class:'editor-advanced',open:data.mode==='create'}, el('summary', {text:'Разделы чек-листа'}));
    d.sections.forEach((section,index)=>sections.append(el('div',{class:'editor-card form-grid'},
      field('ID раздела', section.id,v=>edit(section,'id',v),{required:true}),field('Название раздела',section.title,v=>edit(section,'title',v),{required:true}),
      button('Удалить раздел',()=>{d.sections.splice(index,1);touch();renderEditor();},'danger'))));
    sections.append(button('Добавить раздел',()=>{d.sections.push({id:'',title:''});touch();renderEditor();}));
    fields.append(sections, el('div',{class:'section-heading'},el('h3',{text:`Критерии · ${d.criteria.length}`}),note('Измените нужный критерий и сохраните новую версию.')));
    d.criteria.forEach((c,index)=>{
      const grid=el('div',{class:'form-grid'},field('ID критерия',c.id,v=>edit(c,'id',v),{required:true}),
        field('ID раздела критерия',c.section_id,v=>edit(c,'section_id',v),{required:true}),
        select('Тип критерия',[['binary','Да / нет'],['scale','Шкала'],['flag','Флаг нарушения']],c.kind,v=>{edit(c,'kind',v);renderEditor();}),
        field('Вес',c.weight,v=>edit(c,'weight',v),{required:true,inputMode:'decimal'}),
        field('Разрешить N/A',null,v=>{edit(c,'allow_na',v);renderEditor();},{type:'checkbox',checked:c.allow_na}));
      const options=el('details',{class:'editor-advanced',open:advanced.has(c)||!c.id,ontoggle:event=>{if(event.currentTarget.open)advanced.add(c);else advanced.delete(c);}},
        el('summary',{text:'Тип, вес, N/A и дополнительные параметры'}),grid,
        field('Правило N/A',c.na_rule??'',v=>edit(c,'na_rule',v),{required:c.allow_na,multiline:true}));
      const card=el('details',{class:'editor-card criterion-editor','data-criterion-index':String(index),open:expanded.has(c)||!c.id,
        ontoggle:event=>{if(event.currentTarget.open)expanded.add(c);else expanded.delete(c);}},
        el('summary',{},el('div',{},el('h4',{text:(c.id?c.id+' — ':'')+(c.title||'Новый критерий')}),el('p',{text:c.instruction||'Добавьте название и инструкцию для оценки.'})),el('span',{class:'edit-label',text:'Изменить критерий'})),
        field('Название критерия',c.title,v=>edit(c,'title',v),{required:true}),
        field('Инструкция',c.instruction,v=>edit(c,'instruction',v),{required:true,multiline:true}),options);
      if(c.kind==='scale') {
        options.append(el('h4',{text:'Уровни шкалы'}));
        c.levels.forEach((level,i)=>options.append(el('div',{class:'level-row'},field('Значение уровня',level.value,v=>edit(level,'value',v),{required:true,inputMode:'decimal'}),
          field('Описание уровня',level.description,v=>edit(level,'description',v),{required:true}),button('Удалить уровень',()=>{c.levels.splice(i,1);touch();renderEditor();},'danger'))));
        options.append(button('Добавить уровень',()=>{c.levels.push({value:'',description:''});touch();renderEditor();}));
      }
      options.append(button('Удалить критерий',()=>{d.criteria.splice(index,1);touch();renderEditor();},'danger')); fields.append(card);
    });
    fields.append(button('Добавить критерий',()=>{d.criteria.push({id:'',section_id:d.sections[0]?.id??'',title:'',instruction:'',kind:'binary',weight:'1',allow_na:false,na_rule:null,levels:[]});touch();renderEditor();}),
      el('div',{class:'toolbar editor-save'},el('button',{type:'submit',text:data.mode==='create'?'Создать чек-лист':'Сохранить новую версию'})));
    form.append(fields,output);
    async function refreshBase() {
      if(!canSwitch()) return;
      try {
        const head=await getChecklist(data.key); if(activeDraft!==draftKey) return;
        data.baseVersion=String(head.version);
        baseline.textContent=`Новая базовая версия: v${head.version}. Ваш черновик из v${data.originVersion} сохранён. Сравните изменения перед явным сохранением.`;
        status(output,'Последняя версия перечитана. Автоматической отправки не было.');
      } catch(e) { if(activeDraft===draftKey) status(output,e.message,'error'); }
    }
    form.addEventListener('submit',event=>{
      event.preventDefault(); let savedVersion; mutation(form,output,drafts,async()=>{
        const sectionIds=new Set(d.sections.map(s=>s.id)), criterionIds=new Set(d.criteria.map(c=>c.id));
        if(!d.sections.length||!d.criteria.length||d.criteria.length>100||sectionIds.size!==d.sections.length||criterionIds.size!==d.criteria.length||d.criteria.some(c=>!sectionIds.has(c.section_id)))
          throw new Error('Нужны разделы и 1–100 критериев с уникальными ID. Укажите существующий раздел для каждого критерия.');
        const body={title:d.title,description:d.description,sections:d.sections,criteria:d.criteria.map(c=>({...c,weight:decimal(c.weight),levels:c.kind==='scale'?c.levels.map(l=>({...l,value:decimal(l.value)})):[]}))};
        const saved=await request('/api/checklists/'+pathId(data.key)+(data.mode==='version'?'?expected_version='+integer(data.baseVersion):''),{method:data.mode==='create'?'POST':'PUT',body});
        if(data.mode==='create') drafts.remove(draftKey);
        else drafts.clean(draftKey);
        status(output,`Сохранена версия ${saved.version}.`);
        // Read back the immutable snapshot; never publish a locally computed checklist result.
        if(activeDraft===draftKey) {
          selected=saved; await loadList();
          // load() is deferred until mutation releases the navigation lock.
          savedVersion=saved;
        }
      }).then(async()=>{if(savedVersion && activeDraft===draftKey) {
        await load(savedVersion.key,String(savedVersion.version));
        if(selected?.key===savedVersion.key && String(selected.version)===String(savedVersion.version)) {
          editor.prepend(el('div',{class:'notice'},note('Новая версия сохранена. Предыдущие оценки остались на прежней версии.'),
            button('Оценить по новой версии',()=>onEvaluate?.(),'primary')));
        }
      }});
    });
    editor.replaceChildren(top,baseline,form);
    if(data.mode==='version') editor.append(el('details',{class:'technical-note'},el('summary',{text:'Версии и конфликт сохранения'}),note(`Ключ: ${data.key}. Исходная версия: ${data.originVersion}. Последняя прочитанная: ${data.baseVersion}.`),button('Обновить базовую версию черновика',refreshBase)));
    editor.append(note(entry.dirty?'Есть несохранённые изменения. Переключение сохраняет черновик в памяти.':'Изменения создают новую версию. Java проверяет состав и допустимые значения.'));
  }
  editor.append(button('Создать новый чек-лист',newChecklist));
  return {load:loadList, get selected(){return selected;}};
}
