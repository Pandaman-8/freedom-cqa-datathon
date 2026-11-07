// This module owns only connection status. Future views can use separate ES modules.
const card = document.querySelector('#connection');
const status = document.querySelector('#connection-status');
const detail = document.querySelector('#connection-detail');
const version = document.querySelector('#service-version');
const button = document.querySelector('#check-connection');

async function checkConnection() {
  button.disabled = true;
  button.textContent = 'Проверяем…';
  card.dataset.state = 'checking';
  status.textContent = 'Проверяем подключение…';
  detail.textContent = 'Ожидаем ответ Java Backend.';
  version.textContent = '—';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);

  try {
    const response = await fetch('/api/health', {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!response.ok) {
      status.textContent = 'Сервер вернул ошибку';
      detail.textContent = `HTTP ${response.status}. Попробуйте проверить подключение ещё раз.`;
      card.dataset.state = 'error';
      return;
    }
    let health;
    try {
      health = await response.json();
    } catch (error) {
      if (controller.signal.aborted) throw error;
      throw new Error('INVALID_HEALTH_RESPONSE');
    }
    if (health?.status !== 'ok' || health.service !== 'freedom-cqa-java'
        || typeof health.version !== 'string' || !health.version.trim()) {
      throw new Error('INVALID_HEALTH_RESPONSE');
    }
    card.dataset.state = 'ok';
    status.textContent = 'Сервер доступен';
    detail.textContent = 'Java Backend отвечает. Оценивание и ML пока недоступны.';
    version.textContent = health.version;
  } catch (error) {
    card.dataset.state = 'error';
    status.textContent = 'Нет подключения';
    if (controller.signal.aborted) {
      detail.textContent = 'Сервер не ответил за 5 секунд. Повторите проверку.';
    } else if (error.message === 'INVALID_HEALTH_RESPONSE') {
      status.textContent = 'Неожиданный ответ сервера';
      detail.textContent = 'Не удалось подтвердить состояние Java Backend. Повторите проверку.';
    } else {
      detail.textContent = 'Не удалось связаться с Java Backend. Проверьте запуск сервера и повторите попытку.';
    }
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
    button.textContent = 'Проверить подключение';
  }
}

button.addEventListener('click', checkConnection);
checkConnection();
