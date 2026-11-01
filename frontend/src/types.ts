// Shapes of what the Django API returns. Kept in one place so a change on the
// backend shows up as a type error here instead of a blank map.

export type LngLat = [number, number];

export type LevelName = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel';

export interface Place {
  label: string;
  lon: number;
  lat: number;
}

export interface Risk {
  level: number; // 0..4
  label: LevelName;
  driver: 'wind' | 'rain' | 'snow' | null;
  by_condition: Record<'wind' | 'rain' | 'snow', LevelName>;
  load_rule: string | null;
}

export interface Checkpoint {
  mile: number;
  eta: string;
  lon: number;
  lat: number;
  weather: { wind_mph: number; gust_mph: number; rain_in: number; snow_in: number };
  risk: Risk;
}

export interface RouteSummary {
  miles_by_level: Record<LevelName, number>;
  avg_risk: number;
  worst_level: LevelName;
}

export interface Route {
  id: string;
  via: string;
  distance_mi: number;
  duration_s: number;
  geometry: LngLat[];
  checkpoints: Checkpoint[];
  summary: RouteSummary;
}

export interface Heatmap {
  hours: number;
  step_deg: number;
  points: LngLat[];
  levels: number[][]; // levels[pointIndex][hour]
}

export interface Plan {
  departure: string;
  load_lb: number;
  interval_mi: number;
  routes: Route[];
  recommended_id: string;
  recommendation_reason: string;
  heatmap: Heatmap;
}

export interface PlanRequest {
  origin: Place;
  destination: Place;
  departure: string;
  load_lb: number;
  interval_mi: 10 | 25 | 50;
}
