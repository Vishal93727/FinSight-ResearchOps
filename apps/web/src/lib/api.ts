const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export type ApiOptions = Omit<RequestInit, 'headers'> & { token?: string | null; headers?: Record<string, string> };

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { token, headers, ...rest } = options;
  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      ...(rest.body instanceof URLSearchParams ? { 'Content-Type': 'application/x-www-form-urlencoded' } : {}),
      ...(rest.body && !(rest.body instanceof URLSearchParams) && !(rest.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof payload.detail === 'string' ? payload.detail : `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}
