import { useEffect, useRef, useState } from 'react';

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

// Counts a figure up once when it appears. Skipped under reduced motion and where matchMedia is missing (tests).
export function CountUp({ text }) {
  const ref = useRef(null);
  useEffect(() => {
    const target = Number(String(text).replace(/,/g, ''));
    const quiet = typeof window.matchMedia !== 'function' || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (quiet || !Number.isFinite(target) || target === 0) return undefined;
    const element = ref.current;
    const show = String(text).includes('.') ? money : value => String(Math.round(value));
    const begin = performance.now();
    let frame;
    const tick = now => {
      const progress = Math.min(1, (now - begin) / 750);
      element.textContent = progress < 1 ? show(target * (1 - (1 - progress) ** 3)) : text;
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); element.textContent = text; };
  }, [text]);
  return <span ref={ref}>{text}</span>;
}

// items: [label, value] or [label, value, 'lead']. The lead tile is the deep-green banknote.
export function Summary({ items }) {
  return <dl className="summary">{items.map(([label, value, kind]) => kind === 'lead'
    ? <div key={label} className="lead"><dt>{label}</dt><dd><CountUp text={String(value)} /></dd></div>
    : <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

const ICONS = {
  users: <><circle cx="9" cy="8" r="3.2" /><path d="M3 19c.6-3.3 3-5 6-5s5.4 1.7 6 5" /><path d="M16 5.2a3 3 0 0 1 0 5.6M18 14.3c1.8.7 2.8 2.3 3 4.7" /></>,
  star: <path d="M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.8 6.8 19.5l1-5.8-4.2-4.1 5.8-.8z" />,
  wallet: <><rect x="3" y="6" width="18" height="13" rx="2.5" /><path d="M3 10h18M16 14.5h2" /></>,
  swap: <><path d="M4 8h14M14 4l4 4-4 4" /><path d="M20 16H6M10 12l-4 4 4 4" /></>,
  person: <><circle cx="12" cy="8" r="3.6" /><path d="M5 20c.8-4 3.6-6 7-6s6.2 2 7 6" /></>,
  out: <><path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4" /><path d="M15 8l4 4-4 4M19 12H9" /></>,
};
export function Icon({ name }) {
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>;
}

export const SLOW_AFTER_MS = 2000;
// Public page listing the demo accounts; opened in a new tab.
export const DEMO_URL = 'https://github.com/RootMoataz/Paper-Maker-Banking-App/blob/5_auth-jwt-ui/DEMO.md';

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
