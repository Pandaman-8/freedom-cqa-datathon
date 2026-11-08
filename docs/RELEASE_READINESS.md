# T16 / T18 — подтверждённая готовность к технической сдаче

Дата проверки: **2026-11-08**, исходный main `7476b83deb4a7d024702d7949b3cac105f043230`,
ветка `codex/T16-release`. Production Java/Vanilla/ML, shared contract2.0.0, scoring,
SyntheticPolicy и существующие fixtures не менялись. Добавлены проверки, CI и документация.
T16/T18 остаются **in_progress до peer review**; официальная приёмка целиком не объявляется.

## Что подтверждено

| Проверка | Результат / граница |
|---|---|
| Java `clean verify` | **5964 JUnit PASS**, failures/errors/skipped=0, BUILD SUCCESS |
| Vanilla JS | **24 PASS**: 16 batch + 8 workspace |
| Shared contract | **4 schemas, 72 fixtures PASS**, drift с plan.json отсутствует |
| Scoring reference | **5184 exact Fraction cases PASS**, все score fields |
| Python ML offline | **332 PASS**, один существующий Starlette/httpx deprecation warning; production provider не вызывается |
| Privacy scanner negative probes | **4 PASS**: fake credential, signed URL, private paths, disguised PDF/SQLite |
| HTTP/JAR smoke | workspace, organizer, review, auto и batch PASS; только собственные процессы/временные SQLite/fake upstream |
| Browser batch | **9/9 PASS**: freeze membership/version, pause/resume, double start, Web Locks, failed/unknown/pending/reload, JVM crash, XSS, storage corruption |
| Browser workspace | **11/11 PASS**: RU/KZ/EN/source IDs, stale responses/drafts, manual/evidence, CAS, create A→New→B, версии |
| Browser model review | **7/7 PASS**: original/final, forged evidence, CAS409, confirm/change, critical flag, manual v2, restart |
| Browser single AI | **4/4 PASS**: double submit, invalid output, timeout/unknown/reload, явная новая попытка |
| Чистая сборка | Fresh public clone: **5964 JUnit PASS / BUILD SUCCESS**, новая Python venv и **332 ML tests PASS** |
| Защищённые файлы | SHA256 сравнение **227 файлов**: production sources, shared schemas/fixtures, ML/prompt, legacy, frontend/package-lock.json без изменений |

Использованы Linux, OpenJDK21.0.12.1, Maven3.9.11, Node22.22.2, Python3.14.7.
CI использует Java21/Node22/Python3.12. Browser — реальный Codex in-app browser;
mobile/cross-browser/Windows matrix не запускалась. Maven/pip download caches допустимо
переиспользованы; это не полностью offline/hermetic build и не новый OS install.

## 65 записей и два сервиса: точная формулировка результата

`release_smoke.py` запускает packaged Java и **настоящий Python/FastAPI HTTP app**.
Первый запуск использует обычный `uvicorn app.main:app` без `.env`/ключа: Java health200,
Python health503, разрешённый evaluate501, ledger failed и ноль provider calls.
Затем test-only launcher подставляет provider через существующий `create_app(..., provider)`;
prompt, request/result validation, identity checks и обе policies остаются настоящими.
В этом child запрещены внешние DNS/connect. Нет нового production fake режима.

1. Импортированы **65 разных собственных synthetic sources**, повторный импорт идемпотентен.
   Все messages, roles/order/timestamps/IDs сверены по Java GET.
2. **6** точных существующих fixture-пар проходят Java→Python→fixture provider→Java
   scoring→SQLite. Остальные **59** получают явный503 PRIVACY_POLICY_UNCONFIGURED
   до Java ML POST/ledger claim; отдельный Python HTTP запрос тоже блокирует их до provider.
3. Дополнительные59 запросов с новыми UUID по прежним разрешённым inputs дают суммарно
   **65 успешных оценок шести разговоров**, ровно65 вызовов stub. Это **не65 различных
   успешных AI-разговоров**. Все шесть могут использовать свои исходные v1/v2, а не latest.
4. Review меняет LOCAL_CLARITY на0: original100 остаётся, final33.33 =100×25/75 с N/A;
   повтор resolve даёт409. SQLite original rows byte-identical. Новая v3 policy-blocked.
5. Перезапускаются Java и Python, проверяются все65 UUID/results; POST replay сохранённых
   UUID не добавляет inference. История review и обе исходные версии сохраняются.

Первый полный рабочий прогон этой последовательности — **PASS**. Повтор из чистого
checkout с новой venv — **PASS**, включая обычный startup `uvicorn app.main:app`,
65 записей, 65 stub evaluations и restart обоих процессов без повторного inference.
В fresh clone добавлены только три candidate test/scanner files поверх публичного base;
рабочие `.env`, БД, datasets и локальные пакеты не копировались.

Диагностика реального Python app содержит production labels provider/model даже при
injected provider; эти поля в тестовой базе **не доказывают Groq-вызов**. Usage/cost
не выдаются за live measurement. Время fake-run не является прогнозом CONTROL capacity.

## Публичный GitHub и приватные данные

GitHub API подтвердил `Pandaman-8/freedom-cqa-datathon`: **PUBLIC**, default branch main.
Проверен свежий mirror всех опубликованных heads/tags: **36 commits, 623 reachable
objects, 364 blobs** плюс commit/tag messages и исторические имена файлов.
По credential/signature/private-path/binary detectors находок нет. Tracked working
files и ignore probes также проверяются; Guide PDF и `.env` остаются ignored.

Тестовые userinfo/signature URLs на `.invalid`/loopback — явно вымышленные отрицательные
примеры; их не трактуем как утечку действующего доступа. Сканер не выводит найденные
значения. Проверка происхождения synthetic fixtures не заменяется regex.

Это ограниченный privacy scan, **не гарантия полного отсутствия PII**. Не проверены
недостижимые удалённые объекты, PR-only refs, releases/assets, Actions artifacts/logs,
issues, внешние кэши и forks. Историю не переписывали, visibility/права не меняли.
Если секрет опубликован, удаление текущего файла недостаточно: требуется отозвать
credential и отдельно согласовать очистку истории. В этом прогоне таких находок нет.

## Что остаётся блокером

Текущая приёмка PR #17 (после исторического T16/T18 прогона): **5996 JUnit,31 JS,
368 Python,72 fixtures,5184 scoring PASS**; реальные Java/Python HTTP на существующем DEV
15/50 и60/5;9/9 browser scenarios на приватной копии с новым group_id, включая upload,
v1/v2/review/batch/failed/unknown/restart. Изолированный offline provider, Groq=0.
Полные границы и команды: [PR17 acceptance](DYNAMIC_ADMISSION.md#pr17-final-acceptance-2026-11-08).

- **Missing official checklist PDF:** `data/official/chat_quality_checklist.pdf`.
  `data/official/student_guide_v3.pdf` присутствует и приватен. Точность полного seed,
  официальных N/A/scales и rounding не подтверждена отсутствующим оригиналом.
- **CONTROL/dynamic admission:** the previous DEV/15 hardcoding is removed in PR #17 after
  Nurtas technical approval. Exact archived source hash, explicit IDs and bounded checklist_scope
  authorize arbitrary groups/versions through configuration. Default synthetic_only still restricts
  inputs to its existing fixtures. Current acceptance evidence: [DYNAMIC_ADMISSION](DYNAMIC_ADMISSION.md).
  A temporary DEV copy with changed group metadata is not a real CONTROL dataset.
- **Новый live prompt v4 quality pass, реальные DEV/CONTROL, Organizer GET, аудио,
  company KB и CONTROL latency/cost** не проверялись. Старый live T13/v3 и human review
  Нуртаса сохранены в plan.json / [T15 report](../ml-service/reports/t15-quality-and-demo.md),
  не являются новым прогоном или доказательством качества v4.
- **Peer/plan bookkeeping:** T02 всё ещё ready без записанного joint acknowledgment;
  T09/T15 planned, T14/T21 in_progress в плане при наличии более поздних reports/merged
  PR. Их статусы в этой задаче не менялись; merge не подменяет отсутствующее evidence.
  T16/T18 требуют отдельного peer review перед done.
- Python direct dependencies и Maven versions pinned, но полного hash lock транзитивных
  Python пакетов нет. Требуется доступ к package repositories. Batch recovery зависит
  от прежнего browser origin/profile/SQLite и Web Locks; это не server scheduler.

## Повторить проверки

Из корня репозитория после Quick Start; Python ML dev dependencies установите в его venv:

```bash
ml-service/.venv/bin/python -m pip install -r ml-service/requirements-dev.txt
./server/mvnw -f server/pom.xml clean verify
node --experimental-default-type=module --test server/src/test/js/*.test.mjs
python3 server/src/test/python/scoring_reference.py --check
python3 -m venv /tmp/freedom-cqa-t02-validation
/tmp/freedom-cqa-t02-validation/bin/python -m pip install -r contracts/requirements.txt
/tmp/freedom-cqa-t02-validation/bin/python -B contracts/validate.py
GROQ_API_KEY= GROQ_FREE_PLAN_CONFIRMED=false PYTHONPATH=ml-service ml-service/.venv/bin/python -B -m pytest -q ml-service/tests
ml-service/.venv/bin/python -B server/src/test/python/release_smoke.py --ml-python "$PWD/ml-service/.venv/bin/python"
python3 -B -m unittest discover -s server/src/test/python -p 'test_public_safety.py'
python3 -B scripts/check-public-safety.py
python3 -B server/src/test/python/workspace_smoke.py
python3 -B server/src/test/python/organizer_smoke.py
python3 -B server/src/test/python/review_smoke.py
python3 -B server/src/test/python/auto_smoke.py
python3 -B server/src/test/python/batch_smoke.py
```

Browser: каждый `workspace_smoke.py`, `auto_smoke.py`, `batch_smoke.py` запустить с
`--serve`, открыть напечатанный `/__tests/` и нажать Run. Для T14 — напечатанный
`/__tests/model-review.html` на отдельном свежем auto_smoke server. Один прогон на новую
временную базу; Enter завершает только процессы harness. Не запускайте эти тесты на
пользовательской SQLite. [Демо 4:50](DEMO.md) использует отдельную базу без уже
изменённой regression-сценариями истории.

CI выполняет Java/Node/ML/contracts/privacy и packaged HTTP, включая реальный Python
с injected provider; local browser runs отмечены отдельно. Результат remote CI относится
к конкретному SHA/PR и будет проверен после push, а не предсказан из локального build.
