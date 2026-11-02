import { Autocomplete, CircularProgress, TextField } from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { searchPhoton, searchPlaces } from '../api';
import type { Place } from '../types';

interface Props {
  label: string;
  value: Place | null;
  onChange: (p: Place | null) => void;
  placeholder?: string;
}

/**
 * Place search box built on MUI Autocomplete (which handles keyboard
 * navigation and ARIA for us).
 *
 * Typing is debounced (300 ms) and each new search aborts the previous
 * request, so a fast typist doesn't fire 10 requests or get results back in
 * the wrong order. Filtering happens on the server, so the built-in
 * client-side filter is turned off.
 */
export default function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const [input, setInput] = useState('');
  const [options, setOptions] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    // nothing to search for, or the text is just the picked place's label
    if (input.trim().length < 3 || (value && input === value.label)) {
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    const timer = setTimeout(async () => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const stillCurrent = () => abortRef.current === ctrl;
      try {
        // Photon from this browser first. The server retries with Open-Meteo
        // Geocoding when Photon refuses the host's address.
        const places = await searchPhoton(input, ctrl.signal);
        if (!stillCurrent()) return;
        setOptions(places);
        setError(null);
      } catch (e) {
        if ((e as Error).name === 'AbortError') return;
        try {
          const places = await searchPlaces(input, ctrl.signal);
          if (!stillCurrent()) return;
          setOptions(places);
          setError(null);
        } catch (backup) {
          if ((backup as Error).name === 'AbortError' || !stillCurrent()) return;
          setOptions([]);
          setError((backup as Error).message);
        }
      } finally {
        if (stillCurrent()) setLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [input, value]);

  return (
    <Autocomplete
      value={value}
      onChange={(_, p) => onChange(p)}
      inputValue={input}
      onInputChange={(_, text) => setInput(text)}
      options={value && !options.includes(value) ? [value, ...options] : options}
      filterOptions={(x) => x}
      getOptionLabel={(p) => p.label}
      isOptionEqualToValue={(a, b) => a.lon === b.lon && a.lat === b.lat}
      loading={loading}
      autoHighlight
      noOptionsText={
        error ?? (input.trim().length < 3 ? 'Type at least 3 letters' : 'No places found')
      }
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={placeholder}
          error={Boolean(error)}
          helperText={error ?? undefined}
          slotProps={{
            input: {
              ...params.InputProps,
              endAdornment: (
                <>
                  {loading && <CircularProgress color="inherit" size={16} />}
                  {params.InputProps.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  );
}
