import { useEffect, useState } from 'react';
import { LEVEL_COLORS, LEVEL_LABELS, LEVEL_ORDER, formatTime } from '../format';

interface Props {
  departure: string;
  hour: number;
  max: number;
  onChange: (h: number) => void;
  showHeatmap: boolean;
  onToggleHeatmap: (v: boolean) => void;
}

/** 0–48 h forecast slider with a play button and the risk legend. */
export default function HourSlider({ departure, hour, max, onChange, showHeatmap, onToggleHeatmap }: Props) {
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => onChange(hour >= max ? 0 : hour + 1), 400);
    return () => window.clearInterval(id);
  }, [playing, hour, max, onChange]);

  const at = new Date(new Date(departure).getTime() + hour * 3600_000).toISOString();

  return (
    <div className="hour-slider">
      <div className="slider-row">
        <button
          className="play"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? 'Pause' : 'Play forecast'}
          title={playing ? 'Pause' : 'Play forecast'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <input
          type="range"
          min={0}
          max={max}
          step={1}
          value={hour}
          onChange={(e) => {
            setPlaying(false);
            onChange(Number(e.target.value));
          }}
          aria-label="Forecast hour"
        />
        <div className="slider-label">
          <strong>+{hour} h</strong>
          <span>{formatTime(at)}</span>
        </div>
      </div>
      <div className="legend-row">
        <label className="toggle">
          <input type="checkbox" checked={showHeatmap} onChange={(e) => onToggleHeatmap(e.target.checked)} />
          Heatmap
        </label>
        <div className="legend">
          {LEVEL_ORDER.map((l) => (
            <span key={l}>
              <i style={{ background: LEVEL_COLORS[l] }} />
              {LEVEL_LABELS[l]}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
