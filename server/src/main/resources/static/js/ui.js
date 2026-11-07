import {display} from './json.js';
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key,value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = display(value);
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key in node && !key.startsWith('aria-')) node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(display(child)));
  return node;
}
export const button = (text, onclick, kind = 'secondary') => el('button', {type:'button', class:kind, text, onclick});
export const note = text => el('p', {class:'muted', text});
export const badge = text => el('span', {class:'badge', text});
export function status(node, text, state = 'ok') { node.textContent = text; node.dataset.state = state; }
export function field(label, value, change, {type = 'text', required = false, multiline = false, ...attrs} = {}) {
  const input = el(multiline ? 'textarea' : 'input', {...(!multiline ? {type} : {}), value:value ?? '', required, ...attrs});
  input.addEventListener('input', () => change(type === 'checkbox' ? input.checked : input.value));
  return el('label', {class:'field'}, el('span', {text:label}), input);
}
export function select(label, choices, value, change) {
  const input = el('select', {onchange: e => change(e.target.value)});
  for (const [key,title] of choices) input.append(el('option', {value:String(key), text:title}));
  input.value = String(value ?? '');
  return el('label', {class:'field'}, el('span', {text:label}), input);
}
export function messageNode() { return el('p', {class:'notice', role:'status', 'aria-live':'polite'}); }
export function formShell(title) {
  const fields = el('fieldset'); const feedback = messageNode();
  const form = el('form', {}, el('h3', {text:title}), fields, feedback);
  return {form, fields, feedback};
}
export async function mutation(form, feedback, drafts, action, onConflict) {
  if (drafts.pending || form.dataset.pending === 'true') return;
  const key = form.dataset.draftKey || form.id;
  function unknown() {
    drafts.unknown.add(key); form.dataset.unknown = 'true';
    status(feedback, 'Результат сохранения неизвестен. Проверьте сохранённые записи перед повторной отправкой.', 'error');
    feedback.append(button('Я проверил историю — разрешить новую отправку', () => {
      drafts.unknown.delete(key); form.dataset.unknown = 'false';
      const fields = form.querySelector('fieldset'); if (fields) fields.disabled = false;
      status(feedback, 'Черновик сохранён. Повторная отправка — только по вашему действию.');
    }));
  }
  if (drafts.unknown.has(key)) { unknown(); return; }
  form.dataset.pending = 'true'; form.setAttribute('aria-busy', 'true');
  const fields = form.querySelector('fieldset'); if (fields) fields.disabled = true;
  drafts.pending++; drafts.changed(); status(feedback, 'Сохраняем…', 'loading');
  try { await action(); }
  catch (error) {
    status(feedback, error.message, 'error');
    if (error.status === 409 && onConflict) {
      try { await onConflict(); } catch { status(feedback, 'Конфликт. Не удалось перечитать данные; повторите чтение. Черновик сохранён.', 'error'); }
    }
    if (error.unknown) unknown();
  } finally {
    form.dataset.pending = 'false'; form.setAttribute('aria-busy', 'false');
    if (fields && form.dataset.unknown !== 'true') fields.disabled = false;
    drafts.pending--; drafts.changed();
  }
}
export function exactEvidence(conversation, evidence) {
  return evidence.length > 0 && evidence.every(e => e.quote.trim() && conversation.messages.find(m => m.id === e.message_id)?.text.includes(e.quote));
}
export function safeAudio(url) {
  try { const parsed = new URL(url); return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password ? parsed.href : null; }
  catch { return null; }
}
