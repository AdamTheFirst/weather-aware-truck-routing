import SwapVertIcon from '@mui/icons-material/SwapVert';
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { toLocalInputValue } from '../format';
import type { Place, PlanRequest } from '../types';
import PlaceInput from './PlaceInput';

interface Props {
  loading: boolean;
  onSubmit: (req: PlanRequest) => void;
}

export default function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  // default: leave in an hour, rounded to the hour
  const [departure, setDeparture] = useState(() => {
    const d = new Date(Date.now() + 3600_000);
    d.setMinutes(0, 0, 0);
    return toLocalInputValue(d);
  });
  const [load, setLoad] = useState('35000');
  const [interval, setIntervalMi] = useState<10 | 25 | 50>(25);

  const canSubmit = origin && destination && departure && load !== '' && !loading;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!origin || !destination) return;
    onSubmit({
      origin,
      destination,
      // datetime-local has no timezone; new Date() reads it as local time and
      // toISOString() sends UTC, so the backend never has to guess
      departure: new Date(departure).toISOString(),
      load_lb: Number(load),
      interval_mi: interval,
    });
  };

  const swap = () => {
    setOrigin(destination);
    setDestination(origin);
  };

  return (
    <Stack component="form" spacing={2} onSubmit={submit}>
      <Box sx={{ position: 'relative' }}>
        <Stack spacing={1.5}>
          <PlaceInput label="From" value={origin} onChange={setOrigin} placeholder="e.g. Denver, CO" />
          <PlaceInput label="To" value={destination} onChange={setDestination} placeholder="e.g. Salt Lake City, UT" />
        </Stack>
        <Tooltip title="Swap origin and destination">
          <IconButton
            onClick={swap}
            size="small"
            aria-label="Swap origin and destination"
            sx={{
              position: 'absolute',
              right: -14,
              top: '50%',
              transform: 'translateY(-50%)',
              bgcolor: 'background.paper',
              border: 1,
              borderColor: 'divider',
              zIndex: 1,
              '&:hover': { bgcolor: 'grey.100' },
            }}
          >
            <SwapVertIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      <Stack direction="row" spacing={1.5} alignItems="flex-start">
        <TextField
          label="Departure (your local time)"
          type="datetime-local"
          value={departure}
          onChange={(e) => setDeparture(e.target.value)}
          required
          sx={{
            flex: 1,
            minWidth: 0,
            // The shrunk outline label ellipsizes once it is longer than the notch.
            // This string is the field's name, so keep the whole thing visible.
            '& .MuiInputLabel-shrink': { maxWidth: 'none', overflow: 'visible', textOverflow: 'unset' },
          }}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label="Load"
          type="number"
          value={load}
          onChange={(e) => setLoad(e.target.value)}
          required
          sx={{ width: 132, flexShrink: 0 }}
          slotProps={{
            htmlInput: { min: 0, max: 120000, step: 500 },
            input: { endAdornment: <InputAdornment position="end">lb</InputAdornment> },
          }}
        />
      </Stack>

      <Box>
        <Typography variant="overline" color="text.secondary" component="div">
          Check weather every
        </Typography>
        <ToggleButtonGroup
          value={interval}
          exclusive
          fullWidth
          size="small"
          color="primary"
          onChange={(_, v) => v && setIntervalMi(v)}
          aria-label="Checkpoint interval"
        >
          {([10, 25, 50] as const).map((n) => (
            <ToggleButton key={n} value={n}>
              {n} mi
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      <Button
        type="submit"
        variant="contained"
        size="large"
        disabled={!canSubmit}
        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : undefined}
      >
        {loading ? 'Checking routes & weather…' : 'Find safest route'}
      </Button>
    </Stack>
  );
}
