import { useEffect, useState } from "react";
import { api } from "./api.js";

const clone = (o) => JSON.parse(JSON.stringify(o));
const trim = (c) => ({ title: c.title, description: c.description, sections: c.sections, criteria: c.criteria });

export default function ChecklistEditor({ checklist, onSaved, onError }) {
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (checklist) setDraft(clone(trim(checklist))); }, [checklist?.version, checklist?.key]);
  if (!draft || !checklist) return <p className="muted">Загружаем чек-лист…</p>;
  const change = (index, patch) => setDraft(prev => ({ ...prev, criteria: prev.criteria.map((c, i) => i === index ? { ...c, ...patch } : c) }));
  const changeLevel = (index, pos, patch) => {
    const next = clone(draft.criteria[index].levels);
    next[pos] = { ...next[pos], ...patch };
    change(index, { levels: next });
  };
  const addCriterion = () => {
    const ids = new Set(draft.criteria.map(c => c.id));
    let n = 1;
    while (ids.has(`C${String(n).padStart(2, "0")}`)) n++;
    setDraft(prev => ({ ...prev, criteria: [...prev.criteria, {
      id: `C${String(n).padStart(2, "0")}`, section_id: prev.sections[0].id,
      title: "Новый критерий", instruction: "Опишите условие оценивания",
      kind: "binary", weight: 10, allow_na: false, na_rule: null, levels: [],
    }] }));
  };
  async function save() {
    setSaving(true);
    try {
      const saved = await api(`/api/checklists/${encodeURIComponent(checklist.key)}`, {
        method: "PUT", body: JSON.stringify(draft),
      });
      onSaved(saved);
    } catch (error) { onError(error.message); }
    finally { setSaving(false); }
  }
  return (
    <section className="panel stack">
      <div className="flex between center">
        <div><p className="eyebrow">Checklist Editor</p><h2>Официальные критерии</h2></div>
        <span className="tag">v{checklist.version}</span>
      </div>
      <p className="muted small">Изменения сохраняются как новая версия. Прошлые оценки не переписываются. На контрольном этапе можно заменить критерий без изменения кода.</p>
      <label>Название чек-листа<input value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
      <label>Описание<textarea rows={2} value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} /></label>
      {draft.criteria.map((c, i) => (
        <details key={c.id} className="criterion-edit" open={i === 0 ? true : undefined}>
          <summary><strong>{c.id} · {c.title}</strong><span className="muted small">{c.kind} · вес {c.weight}</span></summary>
          <div className="stack narrow">
            <div className="columns-2">
              <label>ID<input value={c.id} onChange={e => change(i, { id: e.target.value })} /></label>
              <label>Секция<select value={c.section_id} onChange={e => change(i, { section_id: e.target.value })}>
                {draft.sections.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
              </select></label>
            </div>
            <label>Название<input value={c.title} onChange={e => change(i, { title: e.target.value })} /></label>
            <label>Правило<textarea rows={3} value={c.instruction} onChange={e => change(i, { instruction: e.target.value })} /></label>
            <div className="columns-2">
              <label>Тип<select value={c.kind} onChange={e => {
                const kind = e.target.value;
                change(i, { kind, weight: kind === "flag" ? 0 : (c.weight || 10),
                  allow_na: kind === "flag" ? false : c.allow_na,
                  na_rule: kind === "flag" ? null : c.na_rule,
                  levels: kind === "scale" ? (c.levels.length ? c.levels : [{ value: 0, description: "Минимальный результат" }, { value: 10, description: "Максимальный результат" }]) : [] });
              }}><option value="binary">Да / Нет</option><option value="scale">Числовая шкала</option><option value="flag">Флаг нарушения (без баллов)</option></select></label>
              <label>Вес<input type="number" min="0" max="100" step="0.5" disabled={c.kind === "flag"} value={c.weight}
                onChange={e => change(i, { weight: Number(e.target.value) })} /></label>
            </div>
            {c.kind !== "flag" && <label className="inline-check"><input type="checkbox" checked={c.allow_na} onChange={e => change(i, { allow_na: e.target.checked, na_rule: e.target.checked ? (c.na_rule || "Укажите основание N/A") : null })} /> Разрешить N/A</label>}
            {c.allow_na && <label>Условие N/A<textarea rows={2} value={c.na_rule || ""} onChange={e => change(i, { na_rule: e.target.value })}/></label>}
            {c.kind === "scale" && <div className="stack"><strong>Шкала (значения + описание)</strong>
              {c.levels.map((lvl, pos) => <div className="level-row" key={pos}>
                <input aria-label="Баллы шкалы" type="number" min="0" step="1" value={lvl.value} onChange={e => changeLevel(i, pos, { value: Number(e.target.value) })} />
                <input aria-label="Описание уровня" value={lvl.description} onChange={e => changeLevel(i, pos, { description: e.target.value })}/>
                <button className="small-button ghost" onClick={() => change(i, { levels: c.levels.filter((_, x) => x !== pos) })}>×</button>
              </div>)}
              <button className="secondary" onClick={() => change(i, { levels: [...c.levels, { value: (Math.max(...c.levels.map(l => l.value), 0) + 1), description: "Новый уровень" }] })}>+ Уровень</button>
            </div>}
            <button className="danger-link" onClick={() => setDraft(prev => ({ ...prev, criteria: prev.criteria.filter((_, x) => x !== i) }))}>Удалить критерий</button>
          </div>
        </details>
      ))}
      <div className="flex between wrap gap"><button className="secondary" onClick={addCriterion}>+ Добавить критерий</button>
        <button disabled={saving} onClick={save}>{saving ? "Сохранение…" : "Сохранить новую версию"}</button></div>
      <p className="muted small">Суммарный вес текущего черновика: {draft.criteria.reduce((sum, c) => sum + c.weight, 0)}. Итог нормализуется до 100 для всех применимых критериев.</p>
    </section>
  );
}
