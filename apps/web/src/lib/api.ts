type ApiRequestOptions = {
  method?: string;
  token?: string;
  body?: BodyInit | Record<string, unknown> | URLSearchParams | null;
  headers?: Record<string, string>;
};

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');

function resolveUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = 'GET', token, body, headers = {} } = options;
  const requestHeaders = new Headers(headers);

  if (token) {
    requestHeaders.set('Authorization', `Bearer ${token}`);
  }

  const isBinaryBody = body instanceof Blob || body instanceof ArrayBuffer || ArrayBuffer.isView(body);
  if (body != null && !isBinaryBody && !(body instanceof FormData) && !(body instanceof URLSearchParams) && typeof body !== 'string') {
    if (!requestHeaders.has('Content-Type')) {
      requestHeaders.set('Content-Type', 'application/json');
    }
  }

  const response = await fetch(resolveUrl(path), {
    method,
    headers: requestHeaders,
    body: body == null
      ? undefined
      : typeof body === 'string' || body instanceof URLSearchParams || body instanceof FormData || body instanceof Blob || body instanceof ArrayBuffer
        ? body
        : JSON.stringify(body),
  });

  const contentType = response.headers.get('content-type') ?? '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload
      ? String((payload as { detail?: unknown }).detail ?? 'Request failed')
      : typeof payload === 'string' && payload.length > 0
        ? payload
        : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  if (response.status === 204 || payload === '') {
    return undefined as T;
  }

  return payload as T;
}
