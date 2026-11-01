import type { Place, Plan, PlanRequest } from './types';

// In dev, Vite proxies /api to Django (see vite.config.ts). In production the
// same Django service serves both, so a relative URL works everywhere.
const BASE = import.meta.env.VITE_API_URL ?? '';

async function handle<T>(resp: Response): Promise<T> {
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error ?? `Request failed (${resp.status})`);
  }
  return data as T;
}

export async function searchPlaces(q: string, signal?: AbortSignal): Promise<Place[]> {
  const resp = await fetch(`${BASE}/api/geocode?q=${encodeURIComponent(q)}`, { signal });
  return (await handle<{ results: Place[] }>(resp)).results;
}

export async function planTrip(req: PlanRequest, signal?: AbortSignal): Promise<Plan> {
  const resp = await fetch(`${BASE}/api/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  });
  return handle<Plan>(resp);
}
