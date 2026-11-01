import { useEffect, useRef, useState } from 'react';
import { searchPlaces } from '../api';
import type { Place } from '../types';

interface Props {
  label: string;
  value: Place | null;
  onChange: (p: Place | null) => void;
  placeholder?: string;
}

/**
 * Text box with place suggestions.
 *
 * Typing is debounced (300 ms) and each new keystroke aborts the previous
 * request, so a fast typist doesn't fire 10 requests or get results back in
 * the wrong order.
 */
export default function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const [text, setText] = useState(value?.label ?? '');
  const [options, setOptions] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  // keep the box in sync if the parent changes the value (e.g. "swap")
  useEffect(() => {
    setText(value?.label ?? '');
  }, [value]);

  useEffect(() => {
    if (value && text === value.label) return; // already picked, don't search again
    if (text.trim().length < 3) {
      setOptions([]);
      return;
    }
    const timer = setTimeout(async () => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        setOptions(await searchPlaces(text, ctrl.signal));
        setActive(0);
        setOpen(true);
      } catch (e) {
        if ((e as Error).name !== 'AbortError') setOptions([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [text, value]);

  const pick = (p: Place) => {
    onChange(p);
    setText(p.label);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || options.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, options.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      pick(options[active]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <label className="field place-input">
      <span className="field-label">{label}</span>
      <input
        type="text"
        value={text}
        placeholder={placeholder}
        autoComplete="off"
        onChange={(e) => {
          setText(e.target.value);
          if (value) onChange(null); // editing the text un-picks the place
        }}
        onFocus={() => options.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={open}
      />
      {open && options.length > 0 && (
        <ul className="suggestions" role="listbox">
          {options.map((o, i) => (
            <li
              key={`${o.lon},${o.lat},${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              onMouseDown={() => pick(o)}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </label>
  );
}
