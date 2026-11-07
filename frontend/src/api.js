const BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function api(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let data;
  try { data = await response.json(); }
  catch { data = { detail: await response.text().catch(() => "Server unavailable") }; }
  if (!response.ok) {
    const message = Array.isArray(data?.detail)
      ? data.detail.map(d => `${d.loc?.join(".") || "field"}: ${d.msg}`).join("; ")
      : (data?.detail || `HTTP ${response.status}`);
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

export const asJson = (body) => ({ method: "POST", body: JSON.stringify(body) });
