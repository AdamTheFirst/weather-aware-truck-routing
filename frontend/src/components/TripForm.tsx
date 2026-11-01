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
    <form className="trip-form" onSubmit={submit}>
      <PlaceInput label="From" value={origin} onChange={setOrigin} placeholder="e.g. Denver, CO" />
      <button type="button" className="swap" onClick={swap} title="Swap origin and destination" aria-label="Swap">
        ⇅
      </button>
      <PlaceInput label="To" value={destination} onChange={setDestination} placeholder="e.g. Salt Lake City, UT" />

      <div className="row">
        <label className="field">
          <span className="field-label">Departure</span>
          <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
        </label>
        <label className="field">
          <span className="field-label">Load (lb)</span>
          <input
            type="number"
            min={0}
            max={120000}
            step={500}
            value={load}
            onChange={(e) => setLoad(e.target.value)}
            required
          />
        </label>
      </div>

      <div className="field">
        <span className="field-label">Check weather every</span>
        <div className="segmented" role="radiogroup">
          {([10, 25, 50] as const).map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={interval === n}
              className={interval === n ? 'on' : ''}
              onClick={() => setIntervalMi(n)}
            >
              {n} mi
            </button>
          ))}
        </div>
      </div>

      <button type="submit" className="primary" disabled={!canSubmit}>
        {loading ? 'Checking routes & weather…' : 'Find safest route'}
      </button>
    </form>
  );
}
