const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

const TOKEN_KEY = 'paper-maker-token';
export const getToken = () => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const setToken = token => { try { sessionStorage.setItem(TOKEN_KEY, token); } catch { /* storage unavailable */ } };
export const clearToken = () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ } };
let unauthorizedHandler = null;
export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
  return () => { if (unauthorizedHandler === handler) unauthorizedHandler = null; };
}

export class ApiError extends Error {
  constructor(message, status, retryAfter = null) { super(message); this.name = 'ApiError'; this.status = status; this.retryAfter = retryAfter; }
}

// Seconds to wait, from the JSON body or the Retry-After header; null when the server gave neither.
function retrySeconds(body, response) {
  for (const value of [body?.retryAfter, response.headers?.get?.('Retry-After')]) {
    const seconds = Number(value);
    if (value !== null && value !== undefined && value !== '' && Number.isFinite(seconds) && seconds > 0) return Math.ceil(seconds);
  }
  return null;
}

export function customerRequest(path = '', options = {}) {
  return apiRequest(`/customers${path}`, options);
}

export async function apiRequest(path, { method = 'GET', data, signal, idempotencyKey } = {}) {
  let response;
  const token = getToken();
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(data ? { 'Content-Type': 'application/json' } : {}),
    ...(data && idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
  };
  try {
    response = await fetch(`${baseUrl}/api${path}`, {
      method, signal, headers,
      ...(data ? { body: JSON.stringify(data) } : {}),
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Unable to reach the server. Check your connection and try again.');
  }
  if (response.status === 401 && token) {
    clearToken();
    unauthorizedHandler?.();
    throw new Error('Your session has expired. Please sign in again.');
  }
  if (response.status === 204) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map(item => `${(item.loc || []).slice(1).join('.')}: ${item.msg}`).join('; ') : '';
    throw new ApiError(message || `Request failed (${response.status}). Please try again.`, response.status, response.status === 429 ? retrySeconds(body, response) : null);
  }
  if (body === null) throw new Error('The server returned an invalid response. Please try again.');
  return body;
}
