const form = document.querySelector('#dataset-form');
const input = document.querySelector('#group-id');
const submit = document.querySelector('#fetch-dataset');
const result = document.querySelector('#dataset-result');
const refresh = document.querySelector('#refresh-datasets');
const count = document.querySelector('#conversation-count');
const groups = document.querySelector('#dataset-groups');
const listStatus = document.querySelector('#dataset-list-status');

// Only fixed messages: even an unexpected proxy error must not display its body or URL.
const messages = {
  INVALID_INPUT: 'Проверьте group_id: требуется непустой текст до 200 символов.',
  VERSION_CONFLICT: 'Данные этой группы изменились. Сохранённые диалоги не перезаписаны.',
  ORGANIZER_UNCONFIGURED: 'Подключение к API организаторов пока не настроено на сервере.',
  ORGANIZER_CONFIGURATION_ERROR: 'Проверьте настройку подключения к API организаторов на сервере.',
  ORGANIZER_ACCESS_DENIED: 'Организаторы отклонили доступ. Возможно, срок ссылки истёк или группа недоступна.',
  ORGANIZER_NOT_FOUND: 'Запрошенный набор не найден. Проверьте group_id.',
  ORGANIZER_RATE_LIMITED: 'Организаторы ограничили частоту запросов. Попробуйте позднее.',
  ORGANIZER_REDIRECT_REJECTED: 'Адрес API перенаправляет запрос. Проверьте подключение на сервере.',
  ORGANIZER_UPSTREAM_ERROR: 'API организаторов вернул ошибку. Попробуйте позднее.',
  ORGANIZER_UNAVAILABLE: 'Не удалось связаться с API организаторов.',
  ORGANIZER_TIMEOUT: 'API организаторов не ответил вовремя. Попробуйте позднее.',
  ORGANIZER_RESPONSE_TOO_LARGE: 'Набор превышает допустимый размер 16 MiB.',
  ORGANIZER_INVALID_RESPONSE: 'API организаторов вернул некорректный набор. Импорт отменён.',
  ORGANIZER_GROUP_MISMATCH: 'Получена другая группа. Импорт отменён.',
};

async function loadGroups() {
  refresh.disabled = true;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch('/api/conversations', { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error('LIST_UNAVAILABLE');
    const records = await response.json();
    if (!Array.isArray(records) || records.some(r => typeof r?.dataset_group_id !== 'string')) throw new Error('INVALID_LIST');
    const totals = new Map();
    for (const row of records) totals.set(row.dataset_group_id, (totals.get(row.dataset_group_id) || 0) + 1);
    const items = [...totals].sort(([a], [b]) => a.localeCompare(b)).map(([group, total]) => {
      const item = document.createElement('li');
      item.textContent = `${group}: ${total}`;
      return item;
    });
    groups.replaceChildren(...items);
    count.textContent = String(records.length);
    listStatus.textContent = records.length ? 'Группы хранятся отдельно.' : 'Пока нет сохранённых диалогов.';
  } catch {
    listStatus.textContent = 'Не удалось обновить список. Показанные ранее значения могут быть устаревшими.';
  } finally {
    clearTimeout(timer);
    refresh.disabled = false;
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submit.disabled) return;
  const group = input.value;
  if (!group.trim()) { result.textContent = messages.INVALID_INPUT; result.dataset.state = 'error'; return; }
  submit.disabled = true;
  input.disabled = true;
  form.setAttribute('aria-busy', 'true');
  submit.textContent = 'Загружаем…';
  result.dataset.state = 'loading';
  result.textContent = 'Запрашиваем набор у организаторов…';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 35000);
  try {
    const response = await fetch('/api/datasets/fetch', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ group_id: group }), signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      result.textContent = Object.hasOwn(messages, data?.detail?.code) ? messages[data.detail.code] : 'Не удалось загрузить набор. Попробуйте позднее.';
      result.dataset.state = 'error';
      return;
    }
    if (data?.dataset_group_id !== group || !Number.isSafeInteger(data.imported_records) || data.imported_records < 0) throw new Error('INVALID_RESULT');
    result.textContent = `Группа ${group}: принято записей ${data.imported_records}. Идентичные записи повторно не добавляются.`;
    result.dataset.state = 'ok';
  } catch {
    result.dataset.state = 'error';
    result.textContent = 'Не удалось подтвердить результат загрузки. Обновите список перед повторной попыткой.';
  } finally {
    clearTimeout(timer);
    submit.disabled = false;
    input.disabled = false;
    submit.textContent = 'Fetch dataset';
    form.setAttribute('aria-busy', 'false');
    await loadGroups();
  }
});
refresh.addEventListener('click', loadGroups);
loadGroups();
