// API client with a demo mode.
// Live: calls NEXT_PUBLIC_API_URL. If the API cannot be reached, reads bundled
// static JSON from /demo (made by `make demo-json` from the fast-profile artifacts),
// so the dashboard still works offline, e.g. at a judging table.

export type Source = "live" | "demo";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchWithTimeout(url: string, init?: RequestInit, ms = 3000): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** GET from the live API; on failure, the bundled demo file. */
export async function getData<T>(path: string, demoFile: string): Promise<{ data: T; source: Source }> {
  try {
    const r = await fetchWithTimeout(`${API_BASE}${path}`);
    if (r.ok) return { data: (await r.json()) as T, source: "live" };
  } catch {
    // fall through to demo data
  }
  const r = await fetch(`/demo/${demoFile}`);
  if (!r.ok) throw new Error(`no live API and no demo file ${demoFile}`);
  return { data: (await r.json()) as T, source: "demo" };
}

/** POST to the live API only (decisions, simulator runs). */
export async function postData<T>(path: string, body: unknown): Promise<T> {
  const r = await fetchWithTimeout(
    `${API_BASE}${path}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    8000,
  );
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(typeof detail.detail === "string" ? detail.detail : `request failed (${r.status})`);
  }
  return (await r.json()) as T;
}

export const taka = (x: number) => `Tk ${Math.round(x).toLocaleString("en-US")}`;
export const pct = (x: number) => `${Math.round(100 * x)}%`;
