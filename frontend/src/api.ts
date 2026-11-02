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

interface PhotonFeature {
  properties: { name?: string; city?: string; state?: string; country?: string };
  geometry: { coordinates: [number, number] };
}

function photonLabel(props: PhotonFeature['properties']): string {
  const parts = [props.name, props.city, props.state, props.country].filter((part): part is string => Boolean(part));
  return [...new Set(parts)].join(', ');
}

/**
 * Ask Photon from the browser. Render's shared address is refused by Photon,
 * and the browser's own address is not. CORS is open (`Access-Control-Allow-Origin: *`).
 */
export async function searchPhoton(q: string, signal?: AbortSignal): Promise<Place[]> {
  const resp = await fetch(
    `https://photon.komoot.io/api/?q=${encodeURIComponent(q)}&limit=5&lang=en`,
    { signal },
  );
  if (!resp.ok) throw new Error(`Place search failed (${resp.status})`);
  const data = (await resp.json()) as { features?: PhotonFeature[] };
  return (data.features ?? []).map((feature) => {
    const [lon, lat] = feature.geometry.coordinates;
    return { label: photonLabel(feature.properties), lon, lat };
  });
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
