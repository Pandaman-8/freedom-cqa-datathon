import {request, pathId} from './api.js';
import {Latest} from './state.js';
import {el, button, field, select, note, badge, status, messageNode, safeAudio} from './ui.js';
import {display} from './json.js';
export function transcript(conversation) {
  const nodes = new Map(); const feedback = messageNode();
  const turns = el('div', {class:'transcript', 'aria-label':'Исходные сообщения'});
  for (const m of conversation.messages) {
    const turn = el('article', {class:'turn', tabIndex:-1, 'data-message-id':m.id, 'data-speaker':m.speaker},
      el('div', {class:'turn-meta'}, el('strong', {text:m.speaker}), el('span', {class:'mono', text:m.id}), el('span', {text:m.timestamp})),
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
  const node = el('div', {}, el('div', {class:'toolbar'}, badge(conversation.language), badge(conversation.channel), badge(conversation.dataset_group_id)),
    el('h3', {class:'inline-id', text:conversation.id}), note('Исходные роли, время и ID сохранены. Выделите точный фрагмент для evidence.'), audio, feedback, turns);
  return {node, jump(messageId, quote) {
    for (const turn of nodes.values()) turn.classList.remove('focused');
    const turn = nodes.get(messageId);
    if (!turn) { status(feedback, 'Evidence ссылается на отсутствующий message_id.', 'error'); return false; }
    if (!conversation.messages.find(m => m.id === messageId).text.includes(quote)) { status(feedback, 'Цитата не совпадает с исходным сообщением.', 'error'); return false; }
    turn.classList.add('focused'); status(feedback, `Evidence · ${messageId}\n${quote}`);
    turn.scrollIntoView({behavior:'auto', block:'center'}); turn.focus({preventScroll:true}); return true;
  }};
}
export function conversations(root, {onSelect, onList, canSwitch}) {
  let rows = [], selected = null, currentId = null, view = null;
  const detailRead = new Latest(), listRead = new Latest();
  const filters = {search:'', group:'', language:'', channel:''};
  const feedback = messageNode(), detailFeedback = messageNode();
  const list = el('div', {class:'panel list-panel', 'aria-label':'Список диалогов'});
  const detail = el('div', {class:'panel'}, note('Выберите диалог слева.'));
  const groupField = select('Группа', [['','Все группы']], '', v => { filters.group = v; renderList(); });
  const toolbar = el('div', {class:'toolbar'}, field('Поиск по ID', '', v => { filters.search=v; renderList(); }, {type:'search'}), groupField,
    select('Язык', [['','Все языки'],['RU','RU'],['KZ','KZ'],['EN','EN']], '', v => { filters.language=v; renderList(); }),
    select('Канал', [['','Все каналы'],['agent chat','agent chat'],['voice call','voice call']], '', v => { filters.channel=v; renderList(); }),
    button('Обновить диалоги', load));
  root.append(toolbar, feedback, el('div', {class:'conversation-grid'}, list, detail));
  function renderList() {
    const found = rows.filter(r => (!filters.search || r.id.toLocaleLowerCase().includes(filters.search.toLocaleLowerCase())) &&
      (!filters.group || r.dataset_group_id === filters.group) && (!filters.language || r.language === filters.language) && (!filters.channel || r.channel === filters.channel));
    list.replaceChildren(note(`${found.length} из ${rows.length} диалогов`));
    for (const row of found) list.append(el('button', {type:'button', class:'list-row', 'aria-pressed':row.id === currentId, onclick:() => choose(row.id)},
      el('strong', {text:row.id}), el('small', {text:`${row.language} · ${row.channel} · ${display(row.message_count)} сообщений`}))) ;
    if (!found.length) list.append(el('p', {class:'empty', text:'Диалоги не найдены. Измените фильтры или загрузите набор.'}));
  }
  async function load() {
    const ticket = listRead.next(); status(feedback, 'Загружаем список…', 'loading');
    try {
      const result = await request('/api/conversations', ticket); if (!ticket.current()) return;
      rows = result; const input = groupField.querySelector('select');
      input.replaceChildren(el('option', {value:'', text:'Все группы'}), ...[...new Set(rows.map(r => r.dataset_group_id))].map(g => el('option', {value:g, text:g})));
      input.value = filters.group; if (input.value !== filters.group) filters.group='';
      renderList(); onList(rows); status(feedback, `${rows.length} диалогов из Java SQLite.`);
    } catch(e) { if (ticket.current()) status(feedback,e.message,'error'); }
  }
  async function choose(id) {
    if (!canSwitch()) return;
    currentId=id; selected=null; view=null; onSelect(null); renderList();
    const ticket = detailRead.next(); detail.replaceChildren(detailFeedback); status(detailFeedback, 'Загружаем исходные сообщения…', 'loading');
    try {
      const result = await request('/api/conversations/' + pathId(id), ticket); if (!ticket.current()) return;
      selected=result; view=transcript(result); detail.replaceChildren(view.node); onSelect(result);
    } catch(e) { if (ticket.current()) { status(detailFeedback,e.message,'error'); detail.append(button('Повторить чтение диалога', () => choose(id))); } }
  }
  return {load, choose, get selected() { return selected; }};
}
