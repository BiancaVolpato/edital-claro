// Server-side access to the backend API. API_URL is read at request time,
// so the same build works locally, in docker-compose and in production.

const API_URL = process.env.API_URL ?? "http://localhost:8000";
// Must exceed the backend's own database check, which can take a few seconds when
// PostgreSQL is down; otherwise a healthy API would be reported as unreachable.
const HEALTH_TIMEOUT_MS = 10_000;

export type BackendHealth =
  | { reachable: true; version: string; database: "ok" | "unavailable" }
  | { reachable: false };

export async function getBackendHealth(): Promise<BackendHealth> {
  try {
    const response = await fetch(`${API_URL}/health`, {
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { reachable: false };
    }
    const body: unknown = await response.json();
    if (!isHealthBody(body)) {
      return { reachable: false };
    }
    return { reachable: true, version: body.version, database: body.database };
  } catch {
    // Network error, timeout or invalid JSON: the API is treated as unreachable.
    return { reachable: false };
  }
}

function isHealthBody(
  body: unknown,
): body is { version: string; database: "ok" | "unavailable" } {
  if (typeof body !== "object" || body === null) {
    return false;
  }
  const { version, database } = body as Record<string, unknown>;
  return (
    typeof version === "string" &&
    (database === "ok" || database === "unavailable")
  );
}
