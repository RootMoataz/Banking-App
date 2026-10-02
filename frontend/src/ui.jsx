export const money = value => Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const shortDate = value => value ? new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';

export function initials(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

export function Summary({ items }) {
  return <dl className="summary">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

export function Skeleton({ rows = 4 }) {
  return <div className="skeleton" aria-hidden="true">{Array.from({ length: rows }, (_, index) => <i key={index} />)}</div>;
}

export function Empty({ title, hint }) {
  return <div className="empty"><p className="lead">{title}</p>{hint && <p className="hint">{hint}</p>}</div>;
}
