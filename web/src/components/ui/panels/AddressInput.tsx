import { useEffect, useRef, useState } from 'react';
import {
  getGeocodeSuggestions,
  type GeocodeSuggestion,
} from '../../../api/client';

// Address text field with debounced typeahead via /api/geocode/suggest.
// Suggestions and dropdown state are local to the input — only the canonical
// text round-trips through the route store via onChange / onPick.

const DEBOUNCE_MS = 200;
const MIN_CHARS = 2;
const SUGGEST_LIMIT = 5;

type Props = {
  inputId: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  onPick?: (suggestion: GeocodeSuggestion) => void;
  placeholder?: string;
  disabled?: boolean;
};

export function AddressInput({
  inputId,
  label,
  value,
  onChange,
  onPick,
  placeholder,
  disabled = false,
}: Props) {
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  // Monotonic request id so a slow earlier response can't overwrite a fast
  // newer one (typing fast across the debounce edge).
  const reqIdRef = useRef(0);

  useEffect(() => {
    const trimmed = value.trim();
    if (trimmed.length < MIN_CHARS) {
      setSuggestions([]);
      return;
    }

    const reqId = ++reqIdRef.current;
    const timeoutId = window.setTimeout(async () => {
      try {
        const res = await getGeocodeSuggestions(trimmed, SUGGEST_LIMIT);
        if (reqId !== reqIdRef.current) return;
        setSuggestions(res);
      } catch (err) {
        if (reqId !== reqIdRef.current) return;
        // Quiet failure — show no suggestions and let the user submit anyway.
        // /api/route is the authoritative geocoder; typeahead is convenience.
        setSuggestions([]);
        console.warn('[geocode/suggest] failed:', err);
      }
    }, DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [value]);

  const showDropdown = open && suggestions.length > 0;

  return (
    <div className="relative">
      <label
        htmlFor={inputId}
        className="block font-mono uppercase text-[10px] tracking-wider text-stone-500 mb-1"
      >
        {label}
      </label>
      <input
        id={inputId}
        type="text"
        autoComplete="off"
        spellCheck={false}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(true)}
        // Delay the close so an onClick on a dropdown item lands before
        // the dropdown unmounts. mousedown.preventDefault on each item
        // belt-and-suspenders the same race.
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={[
          'block w-full bg-transparent',
          'font-sans text-[12px] text-stone-200',
          'placeholder:text-stone-600',
          'border border-hairline rounded-sm',
          'px-2 py-1.5',
          'focus:outline-none focus:border-gold/60 focus:ring-1 focus:ring-gold/40',
          'disabled:opacity-60',
        ].join(' ')}
      />
      {showDropdown && (
        <ul
          role="listbox"
          className={[
            'absolute left-0 right-0 top-full mt-1 z-30',
            'bg-ink-900/95 backdrop-blur-sm',
            'border border-hairline rounded-sm',
            'overflow-hidden',
            'max-h-[220px] overflow-y-auto',
          ].join(' ')}
        >
          {suggestions.map((s, i) => (
            <li key={`${s.lat}-${s.lon}-${i}`} role="option" aria-selected="false">
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(s.display_name);
                  onPick?.(s);
                  setOpen(false);
                }}
                className={[
                  'block w-full text-left',
                  'px-2 py-1.5',
                  'font-sans text-[11px] text-stone-300',
                  'hover:bg-ink-800 hover:text-stone-100',
                  'focus:outline-none focus:bg-ink-800 focus:text-stone-100',
                ].join(' ')}
              >
                {s.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
