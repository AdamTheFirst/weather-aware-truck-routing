import { useCallback, useRef, useState } from 'react';
import { planTrip } from './api';
import HourSlider from './components/HourSlider';
import MapView from './components/MapView';
import RouteList from './components/RouteList';
import TripForm from './components/TripForm';
import type { Plan, PlanRequest } from './types';

export default function App() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [selectedId, setSelectedId] = useState('A');
  const [hour, setHour] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const submit = async (req: PlanRequest) => {
    // a second click cancels the first request instead of racing it
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const result = await planTrip(req, ctrl.signal);
      setPlan(result);
      setSelectedId(result.recommended_id);
      setHour(0);
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError((e as Error).message);
    } finally {
      if (abortRef.current === ctrl) setLoading(false);
    }
  };

  // stable reference so the slider's play timer isn't reset every render
  const onHour = useCallback((h: number) => setHour(h), []);

  return (
    <div className="app">
      <aside className="sidebar">
        <header>
          <h1>Weather-Aware Truck Routing</h1>
          <p className="muted">Compare routes by forecast weather at the time you'll actually be there.</p>
        </header>
        <TripForm loading={loading} onSubmit={submit} />
        {error && <div className="error">{error}</div>}
        {plan && <RouteList plan={plan} selectedId={selectedId} onSelect={setSelectedId} />}
        {!plan && !loading && (
          <div className="empty muted">
            Enter a trip to see three route options, weather checkpoints and a 48-hour risk heatmap.
          </div>
        )}
      </aside>

      <main className="map-wrap">
        <MapView plan={plan} selectedId={selectedId} onSelect={setSelectedId} hour={hour} showHeatmap={showHeatmap} />
        {loading && <div className="map-loading">Fetching routes and forecasts…</div>}
        {plan && (
          <HourSlider
            departure={plan.departure}
            hour={hour}
            max={plan.heatmap.hours}
            onChange={onHour}
            showHeatmap={showHeatmap}
            onToggleHeatmap={setShowHeatmap}
          />
        )}
      </main>
    </div>
  );
}
