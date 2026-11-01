import type { LevelName } from './types';

// One colour per risk level, used by the map, the heatmap and the legend so
// they always agree. Classic traffic-light order so nobody needs the legend
// to guess that red is worse than yellow.
export const LEVEL_COLORS: Record<LevelName, string> = {
  low: '#2e9e5b',
  moderate: '#e3b505',
  high: '#ef7d1a',
  severe: '#d7301f',
  no_travel: '#6b0f5c',
};

export const LEVEL_LABELS: Record<LevelName, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
};

export const LEVEL_ORDER: LevelName[] = ['low', 'moderate', 'high', 'severe', 'no_travel'];

// Distinct colours for the three route lines (not risk colours, on purpose).
export const ROUTE_COLORS: Record<string, string> = { A: '#2563eb', B: '#7c3aed', C: '#0891b2' };

export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// <input type="datetime-local"> wants "YYYY-MM-DDTHH:mm" in *local* time.
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
