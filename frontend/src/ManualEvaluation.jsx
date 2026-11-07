import { useEffect, useState } from "react";
import { api, asJson } from "./api.js";

function choices(criterion) {
  if (criterion.kind === "scale") return [
    ...criterion.levels.map(l => ({ value: String(l.value), label: `${l.value} — ${l.description}` })),
    ...(criterion.allow_na ? [{ value: "na", label: "N/A — неприменимо" }] : [])
  ];
  return [
    { value: "yes", label: criterion.kind === "flag" ? "Да — нарушение есть" : "Да" },
    { value: "no", label: criterion.kind === "flag" ? "Нет — нарушения нет" : "Нет" },
    ...(criterion.allow_na ? [{ value: "na", label: "N/A — неприменимо" }] : []),
  ];
}

export default function ManualEvaluation({ checklist, conversation, onComplete, onError }) {
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setForm({}); }, [conversation?.id, checklist?.version]);
  if (!conversation || !checklist) return <p className="muted">Выберите диалог.</p>;
  const update = (id, patch) => setForm(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  async function submit() {
    const answers = [];
    for (const c of checklist.criteria) {
      const item = form[c.id] || {};
      if (!item.selected || !item.explanation?.trim() || !item.evidenceId) {
        onError(`Заполни решение, обоснование и реплику для ${c.id}`); return;
      }
      const message = conversation.messages.find(m => m.id === item.evidenceId);
      if (!message || !message.text) { onError(`Нужна непустая реплика-доказательство для ${c.id}`); return; }
      const isScale = c.kind === "scale" && item.selected !== "na";
      answers.push({
        criterion_id: c.id, answer: isScale ? "scale" : item.selected,
        value: isScale ? Number(item.selected) : null,
        explanation: item.explanation.trim(),
        evidence: [{ message_id: message.id, quote: message.text }],
      });
    }
    setBusy(true);
    try {
      const result = await api("/api/evaluations/manual", asJson({
        conversation_id: conversation.id, checklist_key: checklist.key, answers,
      }));
      onComplete(result);
    } catch (error) { onError(error.message); }
    finally { setBusy(false); }
  }
  async function auto() {
    setBusy(true);
    try {
      const result = await api("/api/evaluations/auto", asJson({ conversation_id: conversation.id, checklist_key: checklist.key }));
      onComplete(result);
    } catch (error) { onError(error.message); }
    finally { setBusy(false); }
  }
  return <section className="panel stack">
    <div className="flex between wrap center gap"><div><p className="eyebrow">Оценка · {conversation.id}</p><h2>Ручная оценка для проверки системы</h2></div><span className="tag">Чек-лист v{checklist.version}</span></div>
    <p className="muted small">Это рабочий режим для проверки расчёта и апелляций, НЕ AI-оценка. ML-модуль подключим отдельно. Каждый вывод должен содержать ссылку на реальную реплику.</p>
    {checklist.criteria.map(c => {
      const f = form[c.id] || {};
      return <div className="criterion-form" key={c.id}>
        <div className="flex between wrap"><strong>{c.id}. {c.title}</strong><span className="muted small">Вес {c.weight}</span></div>
        <p className="muted small">{c.instruction}</p>
        <div className="columns-2">
          <label>Результат<select value={f.selected || ""} onChange={e => update(c.id, { selected: e.target.value })}>
            <option value="">Выбрать…</option>
            {choices(c).map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select></label>
          <label>Реплика-доказательство<select value={f.evidenceId || ""} onChange={e => update(c.id, { evidenceId: e.target.value })}>
            <option value="">Выбрать…</option>
            {conversation.messages.filter(m => m.text).map(m => <option value={m.id} key={m.id}>{m.id} · {m.speaker}: {m.text.slice(0, 70)}</option>)}
          </select></label>
        </div>
        <label>Обоснование<textarea rows={2} placeholder={f.selected === "na" ? "Почему критерий неприменим?" : "Что подтверждает реплика или какой шаг был пропущен?"}
          value={f.explanation || ""} onChange={e => update(c.id, { explanation: e.target.value })}/></label>
      </div>;
    })}
    <div className="flex gap wrap"><button disabled={busy} onClick={submit}>Сохранить ручную оценку</button>
      <button disabled={busy} className="secondary" onClick={auto}>Запустить AI (после интеграции)</button></div>
  </section>;
}
