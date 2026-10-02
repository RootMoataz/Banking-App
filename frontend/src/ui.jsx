export const money = value => Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const shortDate = value => value ? new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';

export function initials(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

export const endingIn = id => `Ending ${String(id).slice(-4)}`;

export function Summary({ items }) {
  return <dl className="summary">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
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

export function Empty({ title, hint }) {
  return <div className="empty"><Rosette /><p className="lead">{title}</p>{hint && <p className="hint">{hint}</p>}</div>;
}
