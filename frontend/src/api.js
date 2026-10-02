const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

export async function customerRequest(path = '', { method = 'GET', data, signal } = {}) {
  let response;
  try {
    response = await fetch(`${baseUrl}/api/customers${path}`, {
      method, signal,
      ...(data ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : {}),
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Unable to reach the server. Check your connection and try again.');
  }
  if (response.status === 204) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map(item => `${(item.loc || []).slice(1).join('.')}: ${item.msg}`).join('; ') : '';
    throw new Error(message || `Request failed (${response.status}). Please try again.`);
  }
  if (body === null) throw new Error('The server returned an invalid response. Please try again.');
  return body;
}
