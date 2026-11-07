import {request} from './api.js';
import {parse, display} from './json.js';
import {el, mutation, status} from './ui.js';
import {Latest} from './state.js';
export function datasets({drafts, onImported}) {
  const form = document.querySelector('#dataset-form'), input = document.querySelector('#group-id');
  const result = document.querySelector('#dataset-result'), refresh = document.querySelector('#refresh-datasets');
  const count = document.querySelector('#conversation-count'), groups = document.querySelector('#dataset-groups');
  const listStatus = document.querySelector('#dataset-list-status'); const reads = new Latest();
  async function loadGroups() {
    const ticket = reads.next(); refresh.disabled = true;
    try {
      const records = await request('/api/conversations', ticket); if (!ticket.current()) return;
      const totals = new Map(); for (const row of records) totals.set(row.dataset_group_id, (totals.get(row.dataset_group_id) || 0) + 1);
      groups.replaceChildren(...[...totals].map(([group,total]) => el('li', {text:`${group}: ${total}`})));
      count.textContent = String(records.length); listStatus.textContent = records.length ? 'Группы хранятся отдельно.' : 'Пока нет сохранённых диалогов.';
    } catch { if(ticket.current()) listStatus.textContent = 'Не удалось обновить список. Предыдущие значения могут быть устаревшими.'; }
    finally { if(ticket.current()) refresh.disabled = false; }
  }
  form.addEventListener('submit', event => {
    event.preventDefault(); const group = input.value;
    if (!group.trim() || [...group].length > 200) { status(result, 'group_id: непустой текст до 200 символов.', 'error'); return; }
    mutation(form, result, drafts, async () => {
      const data = await request('/api/datasets/fetch', {method:'POST', body:{group_id:group}, timeout:35000});
      status(result, `Группа ${group}: принято записей ${display(data.imported_records)}. Идентичные записи повторно не добавляются.`);
      await loadGroups(); await onImported();
    });
  });
  refresh.addEventListener('click', loadGroups);
  const upload = document.querySelector('#upload-form'), file = document.querySelector('#dataset-file'), output = document.querySelector('#upload-result');
  upload.addEventListener('submit', event => {
    event.preventDefault(); const selected = file.files[0];
    if (!selected || selected.size > 16*1024*1024) { status(output, 'Выберите JSON-файл до 16 MiB.', 'error'); return; }
    mutation(upload, output, drafts, async () => {
      let body; try { body = parse(await selected.text()); } catch { throw new Error('Файл не содержит корректный JSON.'); }
      const saved = await request('/api/datasets/import', {method:'POST', body, timeout:35000});
      status(output, `Принято записей: ${display(saved.imported_records)}. Группа: ${saved.dataset_group_id}.`);
      file.value=''; await loadGroups(); await onImported();
    });
  });
  return {load:loadGroups};
}
