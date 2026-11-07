import { useState } from "react";
import { api, asJson } from "./api.js";

function selectionOptions(criterion) {
  if (!criterion) return [];
  return criterion.kind === "scale"
    ? [...criterion.levels.map(l => ({ value: String(l.value), text: `${l.value} — ${l.description}` })),
       ...(criterion.allow_na ? [{ value: "na", text: "N/A" }] : [])]
    : [{ value: "yes", text: criterion.kind === "flag" ? "Да — обнаружено" : "Да" },
       { value: "no", text: "Нет" }, ...(criterion.allow_na ? [{ value: "na", text: "N/A" }] : [])];
}

function ScoreSummary({ score, prefix }) {
  return <div className="score-box"><span className="muted small">{prefix}</span>
    <div className="score-number">{score.overall_score === null ? "N/A" : score.overall_score}<small>{score.overall_score === null ? "" : " / 100"}</small></div>
    {score.critical_violation && <span className="alert-tag">Грубое нарушение</span>}
    <span className="muted small">Применимый вес: {score.applicable_weight}</span>
  </div>;
}

export default function ReviewWorkspace({ evaluation, checklist, conversation, onChanged, onError, onEvidence }) {
  const [appealFor, setAppealFor] = useState(null);
  const [comment, setComment] = useState("");
  const [decisions, setDecisions] = useState({});
  const [busy, setBusy] = useState(false);
  if (!evaluation || !checklist || !conversation) return <p className="muted">Выберите оценку.</p>;
  const criteria = Object.fromEntries(checklist.criteria.map(c => [c.id, c]));
  const original = Object.fromEntries(evaluation.original_answers.map(a => [a.criterion_id, a]));
  const final = Object.fromEntries(evaluation.final_answers.map(a => [a.criterion_id, a]));
  const setDecision = (id, patch) => setDecisions(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  async function createAppeal(id) {
    if (!comment.trim()) { onError("Напиши причину апелляции"); return; }
    setBusy(true);
    try {
      await api(`/api/evaluations/${evaluation.id}/appeals`, asJson({ criterion_id: id, comment }));
      setComment(""); setAppealFor(null); await onChanged(evaluation.id);
    } catch (e) { onError(e.message); }
    finally { setBusy(false); }
  }
  async function resolve(appeal, decision) {
    const form = decisions[appeal.id] || {};
    if (!form.reason?.trim()) { onError("Проверяющий должен указать причину решения"); return; }
    let replacement = null;
    if (decision === "change") {
      const c = criteria[appeal.criterion_id];
      const selected = form.selected;
      const message = conversation.messages.find(m => m.id === form.evidenceId);
      if (!selected || !message?.text || !form.explanation?.trim()) { onError("Заполни исправленную оценку, доказательство и объяснение"); return; }
      replacement = {
        criterion_id: c.id,
        answer: c.kind === "scale" && selected !== "na" ? "scale" : selected,
        value: c.kind === "scale" && selected !== "na" ? Number(selected) : null,
        explanation: form.explanation,
        evidence: [{ message_id: message.id, quote: message.text }],
      };
    }
    setBusy(true);
    try {
      await api(`/api/appeals/${appeal.id}/resolve`, asJson({ decision, reason: form.reason, replacement }));
      await onChanged(evaluation.id);
    } catch (e) { onError(e.message); }
    finally { setBusy(false); }
  }
  return <section className="panel stack">
    <div className="flex between wrap center gap"><div><p className="eyebrow">Evaluation / Human Review</p><h2>Оценка и пересмотр</h2></div><span className="tag">{evaluation.origin === "manual" ? "Ручная оценка" : "AI"} · v{evaluation.checklist_version}</span></div>
    <p className="muted small">Исходная оценка сохраняется без изменений. Решения проверяющего влияют только на финальную оценку.</p>
    <div className="columns-2"><ScoreSummary score={evaluation.original_score} prefix="Исходный результат"/><ScoreSummary score={evaluation.final_score} prefix="После пересмотра" /></div>
    <h3>Критерии и доказательства</h3>
    {evaluation.final_answers.map(answer => {
      const c = criteria[answer.criterion_id];
      if (!c) return null;
      const previous = original[c.id];
      const changed = JSON.stringify(previous) !== JSON.stringify(answer);
      return <div className="result-card" key={c.id}>
        <div className="flex between wrap gap"><strong>{c.id} · {c.title}</strong><span className={c.kind === "flag" && answer.answer === "yes" ? "alert-tag" : "tag"}>
          {answer.answer === "scale" ? answer.value : answer.answer.toUpperCase()} · вес {c.weight}</span></div>
        {changed && <p className="small changed">Изменено проверяющим (было: {previous.answer === "scale" ? previous.value : previous.answer})</p>}
        <p className="small">{answer.explanation}</p>
        <div className="evidence-list">{answer.evidence.map((e, i) => <button key={i} className="evidence" onClick={() => onEvidence(e.message_id)}>
          ↗ {e.message_id} · «{e.quote.slice(0, 100)}{e.quote.length > 100 ? "…" : ""}»
        </button>)}</div>
        {appealFor === c.id ? <div className="stack narrow">
          <label>Почему оспариваете?<textarea rows={2} value={comment} onChange={e => setComment(e.target.value)} /></label>
          <div className="flex gap"><button disabled={busy} onClick={() => createAppeal(c.id)}>Сохранить апелляцию</button>
            <button className="secondary" onClick={() => { setAppealFor(null); setComment(""); }}>Отмена</button></div>
        </div> : <button className="small-button secondary" onClick={() => setAppealFor(c.id)}>Оспорить критерий</button>}
      </div>;
    })}
    {evaluation.appeals.length > 0 && <><h3>История апелляций</h3>{evaluation.appeals.map(a => {
      const c = criteria[a.criterion_id];
      const d = decisions[a.id] || {};
      return <div key={a.id} className="appeal-card stack narrow">
        <div className="flex between wrap"><strong>{a.criterion_id} · {c?.title}</strong><span className="tag">{a.status === "open" ? "Ожидает решения" : "Пересмотрено"}</span></div>
        <p className="small"><b>Апелляция:</b> {a.comment}</p>
        {a.status === "resolved" ? <p className="small"><b>Решение:</b> {a.decision === "confirm" ? "Подтверждено" : "Изменено"}. {a.reason}</p> : <>
          <label>Причина решения проверяющего<textarea rows={2} value={d.reason || ""} onChange={e => setDecision(a.id, { reason: e.target.value })} /></label>
          <div className="review-change">
            <strong className="small">Для изменения оценки:</strong>
            <label>Новый результат<select value={d.selected || ""} onChange={e => setDecision(a.id, { selected: e.target.value })}>
              <option value="">Выберите…</option>{selectionOptions(c).map(opt => <option key={opt.value} value={opt.value}>{opt.text}</option>)}
            </select></label>
            <label>Доказательство<select value={d.evidenceId || ""} onChange={e => setDecision(a.id, { evidenceId: e.target.value })}>
              <option value="">Выберите реплику…</option>
              {conversation.messages.filter(m => m.text).map(m => <option key={m.id} value={m.id}>{m.id} {m.speaker}: {m.text.slice(0, 65)}</option>)}
            </select></label>
            <label>Новое обоснование<textarea rows={2} value={d.explanation || ""} onChange={e => setDecision(a.id, { explanation: e.target.value })}/></label>
          </div>
          <div className="flex gap wrap"><button disabled={busy} onClick={() => resolve(a, "confirm")}>Подтвердить AI/ручную оценку</button>
            <button disabled={busy} className="secondary" onClick={() => resolve(a, "change")}>Изменить и пересчитать</button></div>
        </>}
      </div>;
    })}</>}
  </section>;
}
