// Browser-side access to the backend, through the same-origin proxy (/api/...).

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** The backend's own message ("detail"), or a generic one in Portuguese. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors: [{loc: [...], msg: "..."}]
      return detail
        .map((item: { loc?: unknown[]; msg?: string }) =>
          [item.loc?.slice(1).join("."), item.msg].filter(Boolean).join(": "),
        )
        .join("; ");
    }
  } catch {
    // not JSON
  }
  return `Erro ${response.status} ao falar com o servidor.`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("Sem conexão com o servidor.", 0);
  }
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function postJson<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  return api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** SWR fetcher: the key is the API path. */
export const fetcher = <T,>(path: string) => api<T>(path);

/** Download a text export (Markdown) as a file. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(`/api${path}`);
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
