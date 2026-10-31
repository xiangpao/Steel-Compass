export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (
    response.status === 401 &&
    typeof window !== "undefined" &&
    !path.startsWith("/api/v1/auth/") &&
    window.location.pathname !== "/login"
  ) {
    // Session expired mid-work: return to login instead of showing raw JSON.
    window.location.assign("/login");
  }
  if (!response.ok) {
    const message =
      typeof payload === "object" && payload !== null
        ? JSON.stringify(payload)
        : String(payload);
    throw new ApiError(response.status, message, payload);
  }
  return payload as T;
}

/** True when a request was cancelled through its AbortSignal. */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const payload = error.payload as {
      detail?: string | { message?: string };
      error?: { message?: string };
    };
    if (payload?.error?.message) return payload.error.message;
    if (typeof payload?.detail === "string") return payload.detail;
    if (payload?.detail && typeof payload.detail === "object") {
      return payload.detail.message ?? error.message;
    }
  }
  return error instanceof Error ? error.message : "发生未知错误";
}
