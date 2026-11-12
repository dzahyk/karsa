import type { User } from "./types";

let csrfToken: string | null = null;
export function setCsrf(token: string | null) { csrfToken = token; }

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {},
    public requestId?: string) {
    super(message);
  }
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
export const onUnauthorized = (l: Listener) => { unauthorizedListeners.add(l); return () => unauthorizedListeners.delete(l); };

async function request<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      credentials: "same-origin",
      headers: {
        ...(form ? {} : { "Content-Type": "application/json" }),
        ...(method !== "GET" && csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the API. Check that the backend is running on port 8000.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error;
    if (res.status === 401 && !path.startsWith("/auth/")) unauthorizedListeners.forEach((l) => l());
    throw new ApiError(res.status, e?.code ?? "HTTP_" + res.status, e?.message ?? `Request failed (${res.status}).`,
      e?.details ?? {}, e?.request_id);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  patch: <T>(p: string, b: unknown) => request<T>("PATCH", p, b),
  upload: <T>(p: string, form: FormData) => request<T>("POST", p, undefined, form),
};

export function can(user: User | undefined, permission: string) {
  return !!user?.permissions.includes(permission);
}

export function hasModule(user: User | undefined, module: string) {
  return !!user?.modules.includes(module);
}

/** Human-readable list of server-side field errors, if any. */
export function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ApiError)) return {};
  const out: Record<string, string> = {};
  const fields = (e.details.fields as { field: string; message: string }[] | undefined) ?? [];
  for (const f of fields) out[f.field] = f.message;
  if (typeof e.details.field === "string") out[e.details.field] = e.message;
  return out;
}
