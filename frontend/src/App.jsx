import { useEffect, useState } from "react";
import { api, asJson } from "./api.js";
import ChecklistEditor from "./ChecklistEditor.jsx";
import ManualEvaluation from "./ManualEvaluation.jsx";
import ReviewWorkspace from "./ReviewWorkspace.jsx";

function Transcript({ conversation, focusedId }) {
  useEffect(() => {
    if (focusedId) document.getElementById(`msg-${focusedId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusedId, conversation?.id]);
  if (!conversation) return <p className="muted small">Загрузите и выберите диалог.</p>;
  return <div className="stack">
    <div className="flex between center wrap gap"><strong>{conversation.conversation_id}</strong><span className="tag">{conversation.language} · {conversation.channel}</span></div>
    {conversation.audio_url && <div className="stack narrow"><audio controls preload="none" src={conversation.audio_url} className="audio" />
      <a className="small" href={conversation.audio_url} target="_blank" rel="noopener noreferrer">Открыть запись отдельно</a></div>}
    <p className="muted small">Сообщения бота и события системы — только контекст. Timestamp сохранены без преобразований.</p>
    <div className="messages">
      {conversation.messages.map(m => <div className={`message message--${m.speaker} ${focusedId === m.id ? "message--focus" : ""}`} id={`msg-${m.id}`} key={m.id}>
        <div className="message-meta"><span>{m.id} · {m.speaker}</span><span>{m.timestamp}</span></div><p>{m.text || <em>[Пустая транскрипция]</em>}</p>
      </div>)}
    </div>
  </div>;
}

export default function App() {
  const [tab, setTab] = useState("conversations");
  const [connection, setConnection] = useState("checking");
  const [conversationList, setConversationList] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [conversation, setConversation] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [reviewChecklist, setReviewChecklist] = useState(null);
  const [allEvaluations, setAllEvaluations] = useState([]);
  const [focus, setFocus] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [lang, setLang] = useState("ALL");

  const fail = (message) => { setError(message); setNotice(""); };
  const ok = (message) => { setNotice(message); setError(""); };
  async function refreshList() { setConversationList(await api("/api/conversations")); }
  async function refreshEvals() { setAllEvaluations(await api("/api/evaluations")); }
  async function openConversation(id) {
    setLoading(true); setFocus("");
    try {
      const record = await api(`/api/conversations/${encodeURIComponent(id)}`);
      setSelectedId(id); setConversation(record); setEvaluation(null);
      const results = await api(`/api/evaluations?conversation_id=${encodeURIComponent(id)}`);
      if (results.length) {
        setEvaluation(results[0]);
        setReviewChecklist(await api(`/api/checklists/${encodeURIComponent(results[0].checklist_key)}?version=${results[0].checklist_version}`));
      }
    } catch (e) { fail(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    let active = true;
    Promise.all([api("/api/health"), api("/api/conversations"), api("/api/checklists/chat-quality"), api("/api/evaluations")])
      .then(([health, list, config, results]) => {
        if (!active) return;
        setConnection(health.status); setConversationList(list); setChecklist(config); setAllEvaluations(results);
      }).catch(e => { if (active) { setConnection("offline"); fail(e.message); } });
    return () => { active = false; };
  }, []);

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    try {
      const data = JSON.parse(await file.text());
      const stats = await api("/api/datasets/import", asJson(data));
      await refreshList(); ok(`Импортирован набор ${stats.dataset_group_id}: ${stats.imported_records} диалогов`);
      setTab("conversations");
    } catch (err) { fail(err.message); }
    finally { setLoading(false); e.target.value = ""; }
  }
  async function updateEvaluation(id) {
    try {
      const updated = await api(`/api/evaluations/${id}`);
      setEvaluation(updated);
      setReviewChecklist(await api(`/api/checklists/${encodeURIComponent(updated.checklist_key)}?version=${updated.checklist_version}`));
      await refreshEvals();
    }
    catch (e) { fail(e.message); }
  }
  function jumpToEvidence(id) { setFocus(""); setTimeout(() => setFocus(id), 0); }
  const filtered = conversationList.filter(c => (lang === "ALL" || c.language === lang) &&
    (c.id.toLowerCase().includes(query.toLowerCase()) || c.channel.toLowerCase().includes(query.toLowerCase())));
  return <div className="app-shell">
    <header className="masthead"><div><p className="eyebrow">FREEDOM BROKER / HACKATHON FOUNDATION</p><h1>Conversation Quality Analytics</h1>
      <p className="muted">Настраиваемая оценка · доказательства · апелляции</p></div>
      <div className={`connection ${connection}`}><span className="dot" /> Backend {connection === "ok" ? "online" : connection}</div></header>
    <nav className="tabs" aria-label="Разделы">
      {[{ key: "conversations", name: `Диалоги (${conversationList.length})` },
        { key: "checklist", name: "Чек-лист" },
        { key: "evaluate", name: "Оценивание" },
        { key: "review", name: "Результаты / пересмотр" }].map(x =>
          <button className={tab === x.key ? "tab active" : "tab"} key={x.key} onClick={() => setTab(x.key)}>{x.name}</button>)}
    </nav>
    {error && <div className="flash flash--error" role="alert"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
    {notice && <div className="flash flash--ok" role="status"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
    {tab === "conversations" && <div className="workspace">
      <section className="panel stack list-pane"><div className="flex between wrap center"><h2>Диалоги</h2><span className="tag">DEV / CONTROL</span></div>
        <label className="upload">Импортировать JSON организаторов<input type="file" accept=".json,application/json" onChange={upload} disabled={loading} /></label>
        <label>Поиск<input placeholder="ID или канал" value={query} onChange={e => setQuery(e.target.value)} /></label>
        <label>Язык<select value={lang} onChange={e => setLang(e.target.value)}><option value="ALL">Все языки</option><option value="RU">RU</option><option value="KZ">KZ</option><option value="EN">EN</option></select></label>
        <div className="conversation-list">{filtered.map(c => <button className={`conversation-row ${c.id === selectedId ? "selected" : ""}`} key={c.id} onClick={() => openConversation(c.id)}>
          <strong>{c.conversation_id}</strong><span className="muted small">{c.language} · {c.channel} · {c.message_count} реплик</span></button>)}
          {!filtered.length && <p className="muted small">Пока пусто. Загрузите DEV JSON.</p>}
        </div>
      </section>
      <section className="panel transcript-pane"><h2>Транскрипт</h2>{loading ? <p className="muted">Загрузка…</p> : <Transcript conversation={conversation} focusedId={focus} />}</section>
    </div>}
    {tab === "checklist" && <ChecklistEditor checklist={checklist} onSaved={config => { setChecklist(config); ok(`Чек-лист сохранён как версия ${config.version}`); }} onError={fail} />}
    {tab === "evaluate" && <div className="workspace"><ManualEvaluation checklist={checklist} conversation={conversation} onError={fail}
      onComplete={result => { setEvaluation(result); setReviewChecklist(checklist); refreshEvals().catch(e => fail(e.message)); ok("Ручная оценка сохранена"); setTab("review"); }}/>
      <section className="panel transcript-pane"><h2>Транскрипт</h2><Transcript conversation={conversation} focusedId={focus}/></section></div>}
    {tab === "review" && <div className="workspace">
      <div className="stack"><section className="panel stack"><div className="flex between wrap center"><h2>История оценок</h2><button className="secondary small-button" onClick={() => refreshEvals().catch(e => fail(e.message))}>Обновить</button></div>
        {allEvaluations.map(e => <button className={`conversation-row ${evaluation?.id === e.id ? "selected" : ""}`} key={e.id} onClick={async () => {
          if (selectedId !== e.conversation_id) await openConversation(e.conversation_id);
          await updateEvaluation(e.id);
        }}><strong>{e.conversation_id}</strong><span className="muted small">v{e.checklist_version} · {e.final_score.overall_score ?? "N/A"}/100 · {e.review_status}</span></button>)}
        {!allEvaluations.length && <p className="muted small">Сначала создайте ручную оценку или подключите ML.</p>}
      </section>
      <ReviewWorkspace evaluation={evaluation} checklist={reviewChecklist} conversation={conversation}
        onChanged={updateEvaluation} onError={fail} onEvidence={jumpToEvidence}/></div>
      <section className="panel transcript-pane"><h2>Транскрипт и ссылки на доказательства</h2><Transcript conversation={conversation} focusedId={focus}/></section>
    </div>}
    {tab !== "conversations" && <p className="footer-hint">Текущий диалог: <strong>{selectedId || "не выбран"}</strong>. Выберите его в разделе «Диалоги».</p>}
    <footer>Локальный прототип · Без авторизации · AI не подключён · Данные реальных клиентов не публиковать</footer>
  </div>;
}
