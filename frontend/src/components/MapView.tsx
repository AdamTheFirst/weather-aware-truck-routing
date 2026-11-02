import { Box, Chip, Stack, Typography } from '@mui/material';
import L from 'leaflet';
import { useEffect, useMemo } from 'react';
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { LEVEL_COLORS, LEVEL_LABELS, ROUTE_COLORS, formatTime } from '../format';
import type { Checkpoint, LngLat, Plan, Route } from '../types';
import HeatmapLayer from './HeatmapLayer';

interface Props {
  plan: Plan | null;
  selectedId: string;
  onSelect: (id: string) => void;
  hour: number;
  showHeatmap: boolean;
}

const US_CENTER: [number, number] = [39.5, -98.35];
const toLatLng = ([lon, lat]: LngLat): [number, number] => [lat, lon];

// Leaflet's default marker icons don't survive bundling, and they look dated
// anyway, so start/end are small HTML pins styled in CSS.
const pin = (text: string) => L.divIcon({ className: 'pin', html: `<span>${text}</span>`, iconSize: [28, 28] });
const START = pin('A');
const END = pin('B');
const TRUCK = L.divIcon({ className: 'truck', html: '🚚', iconSize: [28, 28] });

function FitToPlan({ plan }: { plan: Plan | null }) {
  const map = useMap();
  useEffect(() => {
    if (!plan) return;
    const all = plan.routes.flatMap((r) => r.geometry.map(toLatLng));
    map.fitBounds(L.latLngBounds(all), { padding: [40, 40] });
  }, [plan, map]);
  return null;
}

/**
 * Where is the truck `hour` hours after departure on this route?
 * Linear interpolation between the two checkpoints whose ETAs surround that time.
 */
function truckPosition(route: Route, departure: string, hour: number): [number, number] | null {
  const t = new Date(departure).getTime() + hour * 3600_000;
  const cps = route.checkpoints;
  const times = cps.map((c) => new Date(c.eta).getTime());
  if (t >= times[times.length - 1]) return null; // arrived
  for (let i = 1; i < cps.length; i++) {
    if (t <= times[i]) {
      const f = (t - times[i - 1]) / (times[i] - times[i - 1] || 1);
      return [cps[i - 1].lat + f * (cps[i].lat - cps[i - 1].lat), cps[i - 1].lon + f * (cps[i].lon - cps[i - 1].lon)];
    }
  }
  return null;
}

function CheckpointPopup({ cp, routeId }: { cp: Checkpoint; routeId: string }) {
  const { weather: w, risk } = cp;
  const rows: [string, string][] = [
    ['Wind', `${w.wind_mph} mph (gusts ${w.gust_mph})`],
    ['Rain', `${w.rain_in} in/hr`],
    ['Snow', `${w.snow_in} in/hr`],
  ];
  return (
    <Box sx={{ minWidth: 190 }}>
      <Typography variant="subtitle2" fontWeight={700}>
        Route {routeId} · mile {Math.round(cp.mile)}
      </Typography>
      <Typography variant="body2">
        ETA <strong>{formatTime(cp.eta)}</strong>
      </Typography>
      <Chip
        size="small"
        label={`${LEVEL_LABELS[risk.label]}${risk.driver ? ` · ${risk.driver}` : ''}`}
        sx={{ my: 0.75, bgcolor: LEVEL_COLORS[risk.label], color: '#fff', fontWeight: 600 }}
      />
      {rows.map(([k, v]) => (
        <Stack key={k} direction="row" spacing={1}>
          <Typography variant="body2" color="text.secondary" sx={{ width: 40 }}>
            {k}
          </Typography>
          <Typography variant="body2">{v}</Typography>
        </Stack>
      ))}
      {risk.load_rule && (
        <Typography variant="caption" color="error" component="div" sx={{ mt: 0.75 }}>
          Load rule: {risk.load_rule}
        </Typography>
      )}
    </Box>
  );
}

export default function MapView({ plan, selectedId, onSelect, hour, showHeatmap }: Props) {
  // Selected route goes last so it's drawn on top of the others.
  const ordered = useMemo(() => {
    if (!plan) return [];
    return [...plan.routes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId));
  }, [plan, selectedId]);

  const selected = plan?.routes.find((r) => r.id === selectedId);
  // at +0 h the truck sits on the start pin, so only show it once the slider moves
  const truck = plan && selected && hour > 0 ? truckPosition(selected, plan.departure, hour) : null;

  return (
    // preferCanvas: hundreds of checkpoint circles are much faster on one canvas than as SVG nodes
    <MapContainer center={US_CENTER} zoom={4} preferCanvas className="map" zoomControl={false}>
      <TileLayer
        // muted grey basemap so route and risk colours stand out
        attribution='Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ | Weather &copy; <a href="https://open-meteo.com/">Open-Meteo</a> and <a href="https://api.met.no/">MET Norway</a> (CC BY 4.0)'
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        maxZoom={16}
      />
      <FitToPlan plan={plan} />
      {plan && showHeatmap && <HeatmapLayer heatmap={plan.heatmap} hour={hour} />}

      {ordered.map((r) => {
        const isSel = r.id === selectedId;
        const line = r.geometry.map(toLatLng);
        return (
          <Polyline
            key={`line-${r.id}-${isSel}`}
            positions={line}
            pathOptions={{ color: ROUTE_COLORS[r.id], weight: isSel ? 6 : 4, opacity: isSel ? 0.95 : 0.45 }}
            eventHandlers={{ click: () => onSelect(r.id) }}
          >
            <Tooltip sticky>Route {r.id}</Tooltip>
          </Polyline>
        );
      })}

      {ordered.map((r) =>
        r.checkpoints.map((cp) => {
          const isSel = r.id === selectedId;
          return (
            <CircleMarker
              key={`${r.id}-${cp.mile}-${isSel}`}
              center={[cp.lat, cp.lon]}
              radius={isSel ? 7 : 4}
              pathOptions={{
                color: '#fff',
                weight: isSel ? 2 : 1,
                fillColor: LEVEL_COLORS[cp.risk.label],
                fillOpacity: isSel ? 1 : 0.6,
              }}
            >
              <Popup>
                <CheckpointPopup cp={cp} routeId={r.id} />
              </Popup>
            </CircleMarker>
          );
        }),
      )}

      {plan && selected && (
        <>
          <Marker position={toLatLng(selected.geometry[0])} icon={START} />
          <Marker position={toLatLng(selected.geometry[selected.geometry.length - 1])} icon={END} />
        </>
      )}
      {truck && <Marker position={truck} icon={TRUCK} interactive={false} />}
    </MapContainer>
  );
}
