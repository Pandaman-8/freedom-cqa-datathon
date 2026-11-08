import {parse, stringify} from './json.js';
const messages = {
  INVALID_INPUT: 'Проверьте обязательные поля, тип ответа, уровни, N/A и точность цитат. Сервер отклонил запрос.',
  NOT_FOUND: 'Запись или версия не найдена. Обновите список.',
  VERSION_CONFLICT: 'Конфликт версии или исходных данных. Обновите данные и сравните их с сохранённым черновиком.',
  REVIEW_CONFLICT: 'Оценка уже изменена другим решением. Данные обновлены; проверьте черновик перед новым решением.',
  PAYLOAD_TOO_LARGE: 'Размер запроса превышает ограничение сервера.',
  EVALUATOR_UNCONFIGURED: 'Сервис ИИ не настроен. Ручная оценка доступна.',
  EVALUATOR_INVALID_OUTPUT: 'ML ответ не прошёл строгую проверку. Оценка не сохранена.',
  EVALUATOR_PROVIDER_ERROR: 'ML вызов завершился ошибкой. Проверьте состояние запроса.',
  EVALUATOR_TIMEOUT: 'Время ожидания ML истекло. Исход может быть неизвестен; проверьте состояние запроса.',
  EVALUATOR_BUSY: 'ML сервис занят или недоступен. Проверьте состояние запроса.',
  EVALUATOR_AUTH: 'ML сервис сообщил об ошибке доступа. Проверьте его серверную конфигурацию.',
  EVALUATOR_RATE_LIMITED: 'ML сервис сообщил об ограничении запросов. Автоматического повтора нет.',
  PRIVACY_POLICY_UNCONFIGURED: 'Обработка выбранного диалога и версии чек-листа не разрешена. Нужно согласование доступа к данным на сервере; переименование группы не даёт разрешения.',
  REQUEST_ID_CONFLICT: 'Этот идентификатор уже связан с другим запросом. Повторная обработка не запускалась.',
  ORGANIZER_UNCONFIGURED: 'Подключение к API организаторов пока не настроено на сервере.',
  ORGANIZER_CONFIGURATION_ERROR: 'Проверьте настройку подключения к API организаторов на сервере.',
  ORGANIZER_ACCESS_DENIED: 'Организаторы отклонили доступ к набору.',
  ORGANIZER_NOT_FOUND: 'Набор не найден. Проверьте group_id.',
  ORGANIZER_RATE_LIMITED: 'Организаторы ограничили частоту запросов.',
  ORGANIZER_REDIRECT_REJECTED: 'Перенаправление API отклонено. Проверьте подключение на сервере.',
  ORGANIZER_UPSTREAM_ERROR: 'API организаторов вернул ошибку.',
  ORGANIZER_UNAVAILABLE: 'Не удалось связаться с API организаторов.',
  ORGANIZER_TIMEOUT: 'API организаторов не ответил вовремя.',
  ORGANIZER_RESPONSE_TOO_LARGE: 'Набор превышает 16 MiB.',
  ORGANIZER_INVALID_RESPONSE: 'Некорректный набор. Импорт отменён.',
  ORGANIZER_GROUP_MISMATCH: 'Получена другая группа. Импорт отменён.',
};
export class ApiError extends Error {
  constructor(status, code, unknown = false) {
    super(unknown ? 'Результат сохранения неизвестен. Проверьте историю или список перед повторной отправкой.' :
      (messages[code] || 'Не удалось получить корректный ответ сервера. Проверьте подключение и повторите чтение.'));
    this.status = status; this.code = code; this.unknown = unknown;
  }
}
export async function request(path, {method = 'GET', body, signal, timeout = 10000} = {}) {
  if (!path.startsWith('/api/')) throw new Error('Разрешён только Java API текущего сайта.');
  const controller = new AbortController();
  const abort = () => controller.abort(); signal?.addEventListener('abort', abort, {once:true});
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, timeout); const mutation = method !== 'GET';
  // Serialize before sending: local validation failures never imply an unknown saved outcome.
  let encoded;
  try { if (body !== undefined) encoded = stringify(body); }
  catch (e) { clearTimeout(timer); signal?.removeEventListener('abort', abort); throw e; }
  try {
    const response = await fetch(path, {method, body:encoded, cache:'no-store', signal:controller.signal,
      headers:{Accept:'application/json', ...(body !== undefined ? {'Content-Type':'application/json'} : {})}});
    let data;
    try { data = parse(await response.text()); }
    catch { throw new ApiError(response.status, 'INVALID_RESPONSE', mutation && (response.ok || response.status >= 500)); }
    if (!response.ok) throw new ApiError(response.status, data?.detail?.code, mutation && response.status >= 500 && !data?.detail?.code);
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, 'NETWORK', mutation);
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
export const pathId = value => encodeURIComponent(value);
export const getChecklist = (key, version, options) => request('/api/checklists/' + pathId(key) +
  (version === undefined ? '' : '?version=' + encodeURIComponent(String(version))), options);
