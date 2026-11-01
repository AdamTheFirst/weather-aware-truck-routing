import L from 'leaflet';
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { LEVEL_COLORS, LEVEL_ORDER } from '../format';
import type { Heatmap } from '../types';

/**
 * Weather-risk heatmap drawn on a single <canvas>.
 *
 * Why not leaflet.heat? Those plugins show *density*: overlapping points add
 * up and get "hotter". Our grid is regular, so density means nothing; what we
 * want is a *value* map where each cell shows its own risk level. Drawing it
 * ourselves is ~60 lines and lets the hour slider repaint in about a
 * millisecond, because changing the hour only re-colours ~200 blobs. No new
 * network request, no new layers.
 */
class RiskHeatLayer extends L.Layer {
  private canvas!: HTMLCanvasElement;
  private points: L.LatLng[] = [];
  private levels: number[] = [];
  private stepDeg = 0.25;

  onAdd(map: L.Map) {
    this.canvas = L.DomUtil.create('canvas', 'risk-heat leaflet-zoom-hide');
    map.getPane('heat')!.appendChild(this.canvas);
    map.on('moveend zoomend resize', this.reset, this);
    this.reset();
    return this;
  }

  onRemove(map: L.Map) {
    map.off('moveend zoomend resize', this.reset, this);
    this.canvas.remove();
    return this;
  }

  setData(points: [number, number][], levels: number[], stepDeg: number) {
    this.points = points.map(([lon, lat]) => L.latLng(lat, lon));
    this.levels = levels;
    this.stepDeg = stepDeg;
    if (this._map) this.redraw();
  }

  // keep the canvas pinned to the visible part of the map
  private reset() {
    const map = this._map;
    const size = map.getSize();
    L.DomUtil.setPosition(this.canvas, map.containerPointToLayerPoint([0, 0]));
    this.canvas.width = size.x;
    this.canvas.height = size.y;
    this.redraw();
  }

  private redraw() {
    const map = this._map;
    const ctx = this.canvas.getContext('2d')!;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!this.points.length) return;

    // blob radius = ~1.5 grid cells, so neighbours blend into
    // a smooth surface instead of looking like dots
    const c = map.getCenter();
    const a = map.latLngToContainerPoint(c);
    const b = map.latLngToContainerPoint([c.lat, c.lng + this.stepDeg]);
    const radius = Math.max(8, Math.abs(b.x - a.x) * 1.6);

    // draw from low to high so the worst weather ends up on top. Low risk is
    // drawn very faintly: it shows the area we checked without shouting.
    for (let level = 0; level < LEVEL_ORDER.length; level++) {
      const color = LEVEL_COLORS[LEVEL_ORDER[level]];
      const alpha = level === 0 ? 0.12 : 0.55;
      for (let i = 0; i < this.points.length; i++) {
        if (this.levels[i] !== level) continue;
        const p = map.latLngToContainerPoint(this.points[i]);
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
        g.addColorStop(0, hexToRgba(color, alpha));
        g.addColorStop(1, hexToRgba(color, 0));
        ctx.fillStyle = g;
        ctx.fillRect(p.x - radius, p.y - radius, radius * 2, radius * 2);
      }
    }
  }
}

function hexToRgba(hex: string, alpha: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

interface Props {
  heatmap: Heatmap;
  hour: number;
}

export default function HeatmapLayer({ heatmap, hour }: Props) {
  const map = useMap();
  const layerRef = useRef<RiskHeatLayer | null>(null);

  // create the layer once
  useEffect(() => {
    if (!map.getPane('heat')) {
      const pane = map.createPane('heat');
      pane.style.zIndex = '350'; // above tiles (200), below route lines (400)
      pane.style.pointerEvents = 'none';
    }
    const layer = new RiskHeatLayer();
    layer.addTo(map);
    layerRef.current = layer;
    return () => {
      layer.remove();
    };
  }, [map]);

  // repaint whenever the slider moves or a new plan arrives
  useEffect(() => {
    const levelsAtHour = heatmap.levels.map((row) => row[Math.min(hour, row.length - 1)]);
    layerRef.current?.setData(heatmap.points, levelsAtHour, heatmap.step_deg);
  }, [heatmap, hour]);

  return null;
}
