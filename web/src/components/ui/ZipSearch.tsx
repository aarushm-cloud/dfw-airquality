import { useState, type FormEvent } from 'react';
import { useGrid } from '../../state/grid';
import { ZipNotCoveredError } from '../../api/client';

type Status = 'idle' | 'searching' | 'success' | 'not_covered' | 'invalid' | 'error';

const ZIP_RE = /^\d{5}$/;

export function ZipSearch() {
  const selectCellByZip = useGrid((s) => s.selectCellByZip);
  const [value, setValue] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState('');

  function onChange(next: string) {
    setValue(next);
    if (status !== 'idle' && status !== 'searching' && status !== 'success') {
      setStatus('idle');
      setMessage('');
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();

    if (!ZIP_RE.test(trimmed)) {
      setStatus('invalid');
      setMessage('Enter a 5-digit zip');
      return;
    }

    setStatus('searching');
    setMessage('');
    try {
      await selectCellByZip(trimmed);
      setStatus('success');
      setMessage('✓ Found');
      window.setTimeout(() => {
        setStatus((s) => (s === 'success' ? 'idle' : s));
        setMessage((m) => (m === '✓ Found' ? '' : m));
      }, 800);
    } catch (err) {
      if (err instanceof ZipNotCoveredError) {
        setStatus('not_covered');
        setMessage(`Zip ${trimmed} isn't in our coverage area`);
      } else {
        setStatus('error');
        setMessage('Search failed. Try again.');
        console.warn('[zip-search] failed:', err);
      }
    }
  }

  const messageColor = status === 'success' ? 'text-teal' : 'text-stone-300';
  const isSearching = status === 'searching';

  return (
    <form
      onSubmit={onSubmit}
      className={[
        // left offset stays in sync with LeftPanel.PANEL_WIDTH_PX (280) + 16px gap.
        'fixed top-24 left-[296px] z-20 pointer-events-auto',
        'bg-ink-900/85 backdrop-blur-sm',
        'border border-hairline rounded-sm',
        'p-3',
      ].join(' ')}
    >
      <label
        htmlFor="zip-search-input"
        className="block font-mono uppercase text-[10px] tracking-wider text-stone-500 mb-1"
      >
        ZIP
      </label>
      <input
        id="zip-search-input"
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        maxLength={5}
        autoComplete="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={isSearching}
        placeholder="75201"
        className={[
          'block w-[160px]',
          'bg-transparent',
          'font-sans text-[14px] text-stone-200',
          'placeholder:text-stone-600',
          'border border-hairline rounded-sm',
          'px-2 py-1',
          'focus:outline-none focus:border-gold/60 focus:ring-1 focus:ring-gold/40',
          'disabled:opacity-60',
        ].join(' ')}
      />
      <div
        role="status"
        aria-live="polite"
        className={`mt-1 min-h-[16px] font-mono text-[10px] uppercase tracking-wider ${messageColor}`}
      >
        {message}
      </div>
    </form>
  );
}
