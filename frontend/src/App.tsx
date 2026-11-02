import { Alert, Box, Chip, CircularProgress, Typography } from '@mui/material';
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
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: '460px 1fr' },
        gridTemplateRows: { xs: 'auto 70vh', md: '1fr' },
        height: { md: '100vh' },
      }}
    >
      <Box
        component="aside"
        sx={{
          bgcolor: 'background.paper',
          borderRight: { md: 1 },
          borderBottom: { xs: 1, md: 0 },
          borderColor: 'divider',
          p: 2.5,
          overflowY: 'auto',
        }}
      >
        <Typography variant="h1" gutterBottom>
          Weather-Aware Truck Routing
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          Compare routes by forecast weather at the time you'll actually be there.
        </Typography>

        <TripForm loading={loading} onSubmit={submit} />

        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
        {plan && <RouteList plan={plan} selectedId={selectedId} onSelect={setSelectedId} />}
        {!plan && !loading && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>
            Enter a trip to see three route options, weather checkpoints and a 48-hour risk heatmap.
          </Typography>
        )}
      </Box>

      <Box component="main" sx={{ position: 'relative' }}>
        <MapView plan={plan} selectedId={selectedId} onSelect={setSelectedId} hour={hour} showHeatmap={showHeatmap} />
        {loading && (
          <Chip
            icon={<CircularProgress size={14} />}
            label="Fetching routes and forecasts…"
            sx={{
              position: 'absolute',
              top: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 1000,
              bgcolor: 'background.paper',
              boxShadow: 3,
            }}
          />
        )}
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
      </Box>
    </Box>
  );
}
