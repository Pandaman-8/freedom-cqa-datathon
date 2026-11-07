# ML handoff — текущий HTTP boundary

ML живёт в `ml-service/`, принадлежит Нуртасу и запускается отдельно от Java. Старый `backend/app/evaluator.py` — legacy stub, не integration target. Python использует FastAPI, Java — Spring MVC/JDBC/SQLite, браузер — Vanilla JS.

Единственный нормативный wire contract: [2.0.0](INTEGRATION_CONTRACT.md), [четыре JSON Schema и 72 fixtures](../contracts/README.md). Java отправляет `POST http://127.0.0.1:8001/v1/evaluate`: request_id, immutable conversation и полный pinned checklist. Python возвращает identity echoes, полные answers, exact evidence и diagnostics; Java проверяет их независимо, рассчитывает баллы и сохраняет snapshot. Нового формата или поля этот документ не вводит.

- Критерии динамические: передаются формулировки, weights, discrete levels и N/A rules, без hardcoded C01–C08 в provider output. Источник truth — данные checklist.
- Quotes не переводятся и не нормализуются, IDs позиционные. Bot greeting не считается операторским. При пропуске действия цитируется реальный окружающий контекст, не выдуманная «цитата отсутствия».
- Java SyntheticPolicy допускает только шесть точных опубликованных fixture-пар (v1 и существующая EN v2); Python проверяет conversation fingerprints. Новый текст/ID/рубрика требует согласованного разрешения; ни имя SYNTHETIC, ни fake provider сами по себе не снимают gate.
- Python максимум2 provider attempts/65s, Java deadline70s без POST replay. Request ledger находится в Java. `/health` не проверяет удалённый provider/биллинг и не делает inference.
- Provider secret остаётся в приватном Python окружении. Organizer URL остаётся в Java. Для безопасного старта следуйте root README без `--env-file`, с пустым ключом; ожидаются health503/evaluate501.

Текущий prompt — `cqa-dynamic/4`; нового live quality pass нет. Исторический T13 Groq E2E на v3 и ревью Нуртаса описаны в plan.json / [T15 report](../ml-service/reports/t15-quality-and-demo.md), не выдаются за новые вызовы. Текстовые fixtures не проверяют дикцию, интонацию, аудио или фактические правила компании.

[T16 release smoke](../server/src/test/python/release_smoke.py) проверяет настоящий Java↔Python HTTP с подставным provider через существующий test seam. В child запрещена внешняя сеть, production ML/fixtures не изменены. Это transport/validation/persistence regression, не LLM measurement. [Release blockers](RELEASE_READINESS.md) остаются явными.
