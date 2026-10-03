import { useEffect, useState } from 'react';

// Amounts: no currency symbol, thousands separators, always two decimals, a plain minus for negatives.
// Unparseable values show an em dash rather than "NaN".
export const money = value => {
  const number = Number(value);
  return value === null || value === undefined || value === '' || !Number.isFinite(number) ? '—'
    : number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Dates: "2 Oct 2026"; date and time: "2 Oct 2026, 14:05". Both in the viewer's time zone, 24-hour clock.
const validDate = value => { const date = value ? new Date(value) : null; return date && !Number.isNaN(date.getTime()) ? date : null; };
export const shortDate = value => validDate(value)?.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) ?? '';
export const dateTime = value => validDate(value)?.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) ?? '';

export function initials(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

export const endingIn = id => `Ending ${String(id).slice(-4)}`;

export function Summary({ items }) {
  return <dl className="summary">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

export const SLOW_AFTER_MS = 2000;

// Shown while a request is pending. After two seconds (a cold start) the note changes to say so.
// The note sits in a polite live region and reserves two lines, so nothing below it moves.
export function Loading({ label = 'Loading…', rows = 3 }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS); return () => clearTimeout(timer); }, []);
  return <>
    <p className="loading-note pending" aria-live="polite">{slow ? 'Waking up the server, this can take a few seconds.' : label}</p>
    <Skeleton rows={rows} />
  </>;
}

export function Skeleton({ rows = 4 }) {
  return <div className="skeleton" aria-hidden="true">{Array.from({ length: rows }, (_, index) => <i key={index} />)}</div>;
}

// Fine concentric rosette, drawn once for empty states.
export function Rosette() {
  const rings = [0, 30, 60, 90, 120, 150];
  return <svg viewBox="-50 -50 100 100" fill="none" stroke="currentColor" strokeWidth=".6" aria-hidden="true">
    {rings.map(angle => <ellipse key={angle} rx="44" ry="17" transform={`rotate(${angle})`} />)}
    <circle r="46" strokeWidth="1" /><circle r="12" />
  </svg>;
}

export function Empty({ title, hint, action }) {
  return <div className="empty"><Rosette /><p className="lead">{title}</p>{hint && <p className="hint">{hint}</p>}{action && <button type="button" onClick={action.onClick} disabled={action.disabled}>{action.label}</button>}</div>;
}
