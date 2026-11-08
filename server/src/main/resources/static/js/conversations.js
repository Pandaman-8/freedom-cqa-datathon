import {request, pathId} from './api.js';
import {Latest} from './state.js';
import {el, button, field, select, note, badge, status, messageNode, safeAudio} from './ui.js';
import {display} from './json.js';
export const conversationLabel = (conversation, index) => `${conversation.channel==='voice call'?'Звонок':'Диалог'} ${index===undefined?'· '+conversation.language:String(index+1).padStart(2,'0')}`;
export function transcript(conversation, title=conversationLabel(conversation)) {
  const nodes = new Map(); const feedback = messageNode();
  const turns = el('div', {class:'transcript', 'aria-label':'Исходные сообщения'});
  for (const m of conversation.messages) {
    const turn = el('article', {class:'turn', tabIndex:-1, 'data-message-id':m.id, 'data-speaker':m.speaker},
      el('div', {class:'turn-meta'}, el('strong', {title:m.speaker,text:({operator:'Оператор',client:'Клиент',bot:'Бот',system:'Система'})[m.speaker]??m.speaker}), el('span', {text:m.timestamp}), el('details', {},el('summary',{text:'ID'}),el('span', {class:'mono', text:m.id}))),
      el('p', {class:'source-text', text:m.text}));
    nodes.set(m.id, turn); turns.append(turn);
  }
  const audio = el('div', {class:'audio-box'});
  if (conversation.audio_url) {
    const source = safeAudio(conversation.audio_url);
    if (source) {
      const player = el('audio', {controls:true, preload:'none', hidden:true});
      const info = messageNode();
      player.addEventListener('error', () => status(info, 'Не удалось воспроизвести аудио. Попробуйте открыть источник.', 'error'));
      const load = button('Подключить аудио', () => { player.src = source; player.hidden = false; load.disabled = true; });
      audio.append(load, el('a', {href:source, target:'_blank', rel:'noopener noreferrer', referrerPolicy:'no-referrer', text:'Открыть источник аудио'}), player, info);
    } else audio.append(note('Аудио недоступно: неподдерживаемый адрес.'));
  } else if (conversation.channel === 'voice call') audio.append(note('Аудио недоступно.'));
  const actions=el('div');
  const node = el('div', {'data-conversation-id':conversation.id}, el('div', {class:'toolbar'}, badge(conversation.language), badge(conversation.channel==='voice call'?'Звонок':'Чат'), badge(conversation.dataset_group_id)),
    el('h3', {class:'source-heading', text:title}), el('details',{class:'technical-note'},el('summary',{text:'Подробности диалога'}),note(conversation.id),note('Исходные роли, время и ID сохранены. Выделите точный фрагмент для доказательства.')), audio, feedback, turns);
  node.insertBefore(actions,turns);
  return {node, actions, jump(messageId, quote) {
    for (const turn of nodes.values()) turn.classList.remove('focused');
    const turn = nodes.get(messageId);
    if (!turn) { status(feedback, 'Доказательство ссылается на отсутствующее сообщение.', 'error'); return false; }
    if (!conversation.messages.find(m => m.id === messageId).text.includes(quote)) { status(feedback, 'Цитата не совпадает с исходным сообщением.', 'error'); return false; }
    turn.classList.add('focused'); status(feedback, `Доказательство · ${messageId}\n${quote}`);
    turn.scrollIntoView({behavior:'auto', block:'center'}); turn.focus({preventScroll:true}); return true;
  }};
}
export function conversations(root, {onSelect, onList, canSwitch, composerNode, pickerNode}) {
  let rows = [], selected = null, currentId = null, view = null;
  const detailRead = new Latest(), listRead = new Latest();
  const filters = {search:'', group:'', language:'', channel:''};
  const feedback = messageNode(), detailFeedback = messageNode();
  const list = el('div', {class:'list-panel', 'aria-label':'Список диалогов'});
  const detail = el('div', {class:'panel conversation-detail'},el('div',{class:'empty'},el('h3',{text:'Выберите диалог'}),note('Прочитайте разговор, выберите критерии и нажмите «Оценить с ИИ».')));
  const groupField = select('Группа', [['','Все группы']], '', v => { filters.group = v; renderList(); });
  const search=field('Найти диалог', '', v => { filters.search=v; renderList(); }, {type:'search',placeholder:'Номер, идентификатор или группа'});
  const toolbar = el('div', {class:'toolbar'}, groupField,
    select('Язык', [['','Все языки'],['RU','RU'],['KZ','KZ'],['EN','EN']], '', v => { filters.language=v; renderList(); }),
    select('Канал', [['','Все каналы'],['agent chat','Чат'],['voice call','Звонок']], '', v => { filters.channel=v; renderList(); }),
    button('Обновить диалоги', load,'quiet'));
  const grid=el('div', {class:'conversation-grid','data-mobile':'list'},el('aside',{class:'panel conversation-sidebar'},search,el('details',{class:'filter-details'},el('summary',{text:'Фильтры'}),toolbar),feedback,list),detail);
  root.append(grid);
  function renderList() {
    const found = rows.filter(r => (!filters.search || (r.id+' '+conversationLabel(r,rows.indexOf(r))).toLocaleLowerCase().includes(filters.search.toLocaleLowerCase())) &&
      (!filters.group || r.dataset_group_id === filters.group) && (!filters.language || r.language === filters.language) && (!filters.channel || r.channel === filters.channel));
    list.replaceChildren(note(`${found.length} из ${rows.length} диалогов`));
    for (const row of found) list.append(el('button', {type:'button', class:'list-row', 'data-conversation-id':row.id, 'aria-pressed':row.id === currentId, onclick:() => choose(row.id)},
      el('strong', {text:conversationLabel(row,rows.indexOf(row))}), el('small', {text:`${row.language} · ${row.dataset_group_id} · ${display(row.message_count)} сообщений`}))) ;
    if (!found.length) list.append(el('p', {class:'empty', text:'Диалоги не найдены. Измените фильтры или загрузите набор.'}));
  }
  async function load() {
    const ticket = listRead.next(); status(feedback, 'Загружаем список…', 'loading');
    try {
      const result = await request('/api/conversations', ticket); if (!ticket.current()) return;
      rows = result; const input = groupField.querySelector('select');
      input.replaceChildren(el('option', {value:'', text:'Все группы'}), ...[...new Set(rows.map(r => r.dataset_group_id))].map(g => el('option', {value:g, text:g})));
      input.value = filters.group; if (input.value !== filters.group) filters.group='';
      renderList(); onList(rows); status(feedback, '');
    } catch(e) { if (ticket.current()) status(feedback,e.message,'error'); }
  }
  async function choose(id) {
    if (!canSwitch()) return;
    currentId=id;grid.dataset.mobile='detail'; selected=null; view=null; onSelect(null); renderList();
    const back=button('К списку диалогов',()=>{grid.dataset.mobile='list';list.querySelector('[aria-pressed=true]')?.focus();},'secondary mobile-back');
    const focusMobileBack=()=>{if(back.getClientRects().length)back.focus();};
    const ticket = detailRead.next(); detail.replaceChildren(back,detailFeedback); status(detailFeedback, 'Загружаем исходные сообщения…', 'loading');
    focusMobileBack();
    try {
      const result = await request('/api/conversations/' + pathId(id), ticket); if (!ticket.current()) return;
      selected=result; view=transcript(result,conversationLabel(result,rows.findIndex(r=>r.id===id)));
      detail.replaceChildren(back,view.node);
      const slot=el('div',{id:'conversation-checklist-slot'});view.actions.append(slot);
      if(pickerNode&&!root.closest('[data-panel]')?.hidden)slot.append(pickerNode);
      if(composerNode)view.actions.append(composerNode);onSelect(result);
      focusMobileBack();
    } catch(e) { if (ticket.current()) { status(detailFeedback,e.message,'error'); detail.append(button('Повторить чтение диалога', () => choose(id))); } }
  }
  return {load, choose, get selected() { return selected; }};
}
