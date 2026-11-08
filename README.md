# Freedom CQA

Локальное рабочее место для оценки качества диалогов: **Java 21 + Spring Boot 3.5.16 + SQLite**, HTML/CSS/Vanilla JS и отдельный **Python HTTP ML service**. Java отвечает за проверку evidence, scoring, хранение, апелляции и историю. Python возвращает ответы по полному чек-листу через контракт **2.0.0**, `POST /v1/evaluate`.

Работают импорт/Organizer fetch, RU/KZ/EN, редактор версий, ручная и разрешённая AI-оценка, original/final, evidence jump, review с CAS и последовательный batch с pause/resume/reload. По умолчанию AI разрешён для шести точных fixture-пар. Java поддерживает отдельный approval v2: точный dataset/IDs, ограниченный диапазон версий одного checklist key, выключенный по умолчанию opt-in и подтверждение рубрики через UI. Python admission v2 Нуртаса интегрирован; совместный DEV HTTP-прогон прошёл с изолированным offline provider. Это не проверка качества Groq. Это ограничение безопасности, а не отсутствие импорта или ручной оценки.

Подробности BETA и настройки допуска: [BETA_READINESS](docs/BETA_READINESS.md).
Текущая приёмка PR #17: [CONTROL admission и результаты](docs/DYNAMIC_ADMISSION.md#pr17-final-acceptance-2026-11-08).

## Quick Start — без внешних модельных вызовов

Linux/macOS: JDK 21 (`java` и `javac`), Python 3.12+ с venv, Git, curl. Проверенные версии и результаты — в [release report](docs/RELEASE_READINESS.md). Maven Wrapper скачивает Maven 3.9.11; нужны доступ к Maven Central/PyPI и место под зависимости. Node.js 22 нужен только для JS-тестов, не для запуска UI.

Из корня свежего checkout. Для review PR #17 до merge используется его ветка
`codex/control-readiness`; после merge — актуальный main:

```bash
git clone https://github.com/Pandaman-8/freedom-cqa-datathon.git
cd freedom-cqa-datathon
./server/mvnw -f server/pom.xml clean verify
python3 -m venv ml-service/.venv
ml-service/.venv/bin/python -m pip install -r ml-service/requirements.txt
```

Терминал 1, из корня репозитория — настоящий Python service, намеренно без ключа:

```bash
GROQ_API_KEY= GROQ_FREE_PLAN_CONFIRMED=false ML_DATA_POLICY=synthetic_only \
  ml-service/.venv/bin/python -m uvicorn app.main:app --app-dir ml-service \
  --host 127.0.0.1 --port 8001 --workers 1 --no-access-log
```

Не добавляйте `--env-file`: этот безопасный запуск не читает приватный `.env`.

Терминал 2, также из корня — Java и отдельная временная база:

```bash
CQA_DEMO_DIR=$(mktemp -d /tmp/freedom-cqa-demo.XXXXXX)
CQA_ORGANIZER_URL= CQA_DB_PATH="$CQA_DEMO_DIR/cqa.sqlite" \
  CQA_ML_URL=http://127.0.0.1:8001/v1/evaluate \
  java -jar server/target/freedom-cqa-server-0.1.0.jar
```

Откройте **http://127.0.0.1:8080/**. Проверка из третьего терминала:

```bash
curl -i http://127.0.0.1:8080/api/health
curl -i http://127.0.0.1:8001/health
curl -sS http://127.0.0.1:8080/api/datasets/import \
  -H 'Content-Type: application/json' --data-binary @examples/synthetic_dataset.json
```

Ожидается Java health **200**, Python health **503** с `EVALUATOR_UNCONFIGURED`: процесс работает, но внешний провайдер не включён. Ручная оценка и редактор доступны. Этот пример импорта не входит в AI allowlist; кнопка AI не должна показывать успешную фиктивную оценку. Java без `CQA_ML_URL` возвращает 501; настроенная Java с непринятой парой — 503 до ML. Оба процесса останавливаются Ctrl+C.

Для сохранения истории задайте собственный абсолютный `CQA_DB_PATH` и используйте его при следующем запуске. Без override Java использует `~/.local/share/freedom-cqa/java/cqa.sqlite`. Один Java-процесс владеет одной базой; Python запускается с одним worker. Не открывайте сервисы на `0.0.0.0`: аутентификации нет.

Успешный импорт/fetch сохраняет исходный JSON без изменения байтов в приватный каталог
`dataset-sources/` рядом с SQLite (либо абсолютный `CQA_DATASET_SOURCE_DIR`). Файлы
`<SHA-256>.dataset-source.json` имеют права0600, каталог0700; они нужны для проверки
`dataset_path`/`dataset_sha256` в approval v2. Не публикуйте их. Подробности и поведение при
ошибке записи — в [инструкции Java](server/README.md).

## Новый набор и approval v2

1. В «Загрузка данных» введите выданный `group_id` → «Загрузить группу», либо выберите
   существующий JSON → «Импортировать JSON». Для fetch настройте Java `CQA_ORGANIZER_URL`
   приватно, например `read -r -s -p 'Organizer URL: ' CQA_ORGANIZER_URL`, затем
   `export CQA_ORGANIZER_URL` перед запуском. Не вставляйте signed URL в команды/Git.
   Новый group_id не требует изменения кода; доступ к нему должен предоставить Organizer.
2. Проверьте количество диалогов и группу. Выберите соответствующий файл из приватного
   `dataset-sources/`. Исходные байты загрузки сохраняются, включая пробелы/Unicode.
3. Подготовьте список кандидатов командой ниже. Он **не даёт разрешения** и содержит пустой
   `selected_ids`. Заполните только явно согласованные составные IDs из `candidates`.
   Звонки/аудио не допускаются, wildcard не работает. Нет лимита15 или особых прав у имени DEV.

```bash
umask 077
mkdir -p "$HOME/.local/share/freedom-cqa"
CQA_SESSION_DIR=$(mktemp -d "$HOME/.local/share/freedom-cqa/approval.XXXXXX")
read -r -p 'Абсолютный путь к выбранному архиву JSON: ' CQA_SOURCE
ml-service/.venv/bin/python -B scripts/prepare-approval.py inspect \
  --source "$CQA_SOURCE" --output "$CQA_SESSION_DIR/selected.approval-selection.json"
```

Локально отредактируйте `selected_ids` в этом файле; сохраните права0600. **Только после
фактического подтверждения условий передачи и бюджета Farhat/Nurtas**, а не одного
технического APPROVED, подготовьте grant. Все значения срока и scope выбираются явно:

```bash
read -r -p 'Ссылка/номер фактического согласования передачи (не секрет): ' CQA_APPROVAL_REFERENCE
read -r -p 'Окончание разрешения UTC, YYYY-MM-DDTHH:MM:SSZ: ' CQA_APPROVAL_EXPIRY
ml-service/.venv/bin/python -B scripts/prepare-approval.py create \
  --source "$CQA_SOURCE" --selection "$CQA_SESSION_DIR/selected.approval-selection.json" \
  --output "$CQA_SESSION_DIR/session.ml-approval.json" \
  --session-id control-reviewed-session --approval-reference "$CQA_APPROVAL_REFERENCE" \
  --expires-at "$CQA_APPROVAL_EXPIRY" --ml-url http://127.0.0.1:8001/v1/evaluate \
  --checklist-key chat-quality --min-version 1 --max-version 10 --max-criteria 100 \
  --confirm-external-transfer
```

Команда не обращается к модели и не включает сервисы. Она проверяет hash, точные IDs,
scope/срок и пишет0600, без перезаписи существующего grant. Обеим службам нужен один и тот
же абсолютный путь, одна исходная копия архива и одинаковый локальный пользователь.

Java: `CQA_ML_DATA_MODE=approved_dataset`, `CQA_ML_APPROVAL_FILE` = путь grant,
`CQA_ML_URL=http://127.0.0.1:8001/v1/evaluate`. Python: `ML_DATA_POLICY=approved_dataset`,
`ML_APPROVAL_FILE` = **тот же** путь, `ML_ADMISSION_URL` = **тот же** URL,
`GROQ_MODEL=openai/gpt-oss-20b`. Provider key хранится только в приватной среде Python.
`CQA_ML_EXTERNAL_INFERENCE_ENABLED` и `ML_EXTERNAL_TRANSFER_AUTHORIZED` по умолчанию
false; оба включаются только после отдельного разрешения передачи. `GROQ_FREE_PLAN_CONFIRMED`
также требует фактического подтверждения соответствующего режима провайдера. Технические
проверки ниже не требуют настоящего ключа и не дают этих разрешений.

После запуска/перезапуска с прежней SQLite `/health` Python и `/api/ai/status` Java должны
подтвердить одну policy, protocol2, grant SHA-256, Groq/model. В UI выберите checklist key/version,
подтвердите рубрику и нажмите «Оценить с ИИ». Сохранённая новая версия внутри scope не требует
редактирования grant/Prompt. В «Массовая оценка» выберите группу и версию, подготовьте пакет,
подтвердите рубрику и запустите. Reload только сверяет ledger; resume — явное действие.
Ошибочные/неизвестные исходы не повторяются автоматически. Удаление grant, изменение source
или истечение срока блокирует новые вызовы в обеих службах.

## Проверка интеграции без Groq

```bash
ml-service/.venv/bin/python -B server/src/test/python/release_smoke.py \
  --ml-python "$PWD/ml-service/.venv/bin/python"
```

Тест запускает собственные Java и настоящий Python HTTP app, временную SQLite и подставной provider только внутри теста. Сетевая защита Python запрещает внешние соединения. Проверяется 65 разных синтетических записей: **6 разрешены, 59 явно блокируются политикой**. Дополнительно проходят **65 оценок шести разрешённых fixtures**, restart, replay без новых вызовов и review. Это не 65 разных успешных AI-диалогов и не измерение качества LLM.

Для проверки существующего приватного DEV настоящими Java/Python HTTP без Groq:

```bash
ml-service/.venv/bin/python -B server/src/test/python/admission_dev_smoke.py \
  --dataset data/dev/invoke.json --ml-python "$PWD/ml-service/.venv/bin/python" --serve
```

Это изолированная тестовая зависимость с запрещённой внешней сетью. По умолчанию разрешены
15 чатов,50 записей блокируются. `--all-chats` проверяет60 чатов/5 запрещённых звонков;
`--group-id CONTROL-REGRESSION-ONLY` дополнительно меняет только metadata приватной копии
для проверки нового набора. Это не настоящий CONTROL и не результат Groq. Напечатанный
`/__tests/` запускает9 browser scenarios; Enter завершает тестовые процессы/временную базу.

Для отдельной синтетической репетиции с fake HTTP ML:

```bash
python3 -B server/src/test/python/batch_smoke.py --serve
```

Откройте напечатанный адрес без `/__tests/` для workspace либо `/__tests/` для девяти browser checks. Сервер содержит только синтетические данные. Enter останавливает его процессы и удаляет временную базу. [Сценарий демонстрации до 5 минут](docs/DEMO.md) явно отделяет fake ML от настоящего inference.

## Проверки и документация

- [Результаты, команды, ограничения и release blockers](docs/RELEASE_READINESS.md).
- [Архитектура](docs/architecture.md), [Java REST API](docs/api-contract.md), [требования](docs/requirements.md).
- [Полная инструкция Java/UI](server/README.md), [ML service](ml-service/README.md), [ML handoff](docs/ml-contract.md).
- [Контракт и 72 fixtures](contracts/README.md), [нормативный transport contract](docs/INTEGRATION_CONTRACT.md), [задачи](plan.json), [правила разработки](AGENTS.md).

`backend/`, `frontend/` и `scripts/run-backend.sh` / `run-frontend.sh` — сохранённая legacy Python/React реализация. Она не участвует в Quick Start; её тесты не заменяют Java/Python ML/browser проверки. Vite, React и порт 8000 не нужны целевому приложению.

## Безопасность и границы сдачи

Не публикуйте `.env`, SQLite/WAL, записи/аудио, DEV/CONTROL, signed URLs и официальные PDF. Guide содержит signed API URI. Публичные smoke tests используют собственную синтетику; приватные acceptance tests читают существующий DEV только локально. Настоящий Groq в этих проверках не вызывается. `.gitignore` снижает риск, но не удаляет уже опубликованное из истории; `python3 -B scripts/check-public-safety.py` проверяет tracked files и достижимую Git-историю без вывода найденных значений.

Точный checklist PDF **отсутствует**: ожидается `data/official/chat_quality_checklist.pdf`.
Seed C01–C08 сверяется с правилами, переданными Farhat в финальном задании; полная сверка
оригинального PDF не заявляется. CONTROL admission теперь конфигурируется через approval v2;
временная копия DEV с другим group_id — техническая регрессия, не настоящий CONTROL.
Внешняя обработка требует отдельного разрешения. Новый live quality pass Prompt v4,
семантическая оценка evidence/объяснений и реальные стоимость/задержка — NOT TESTED.
