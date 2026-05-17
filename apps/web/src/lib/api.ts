// REST-клиент для apps/api. URL берётся из VITE_API_URL.

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!resp.ok) {
    let body: unknown;
    try {
      body = await resp.json();
    } catch {
      body = await resp.text();
    }
    const message =
      typeof body === "object" && body && "detail" in body
        ? JSON.stringify((body as { detail: unknown }).detail)
        : resp.statusText;
    throw new ApiError(resp.status, body, message);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export type IntegrationKind = "bitrix24";
export type IntegrationMode = "oauth" | "webhook";
export type IntegrationStatus = "pending" | "connected" | "error";

export type Integration = {
  id: string;
  kind: IntegrationKind;
  mode: IntegrationMode;
  label: string;
  domain: string;
  status: IntegrationStatus;
  member_id?: string | null;
  scope?: string | null;
  created_at: string;
  updated_at: string;
};

export const api = {
  health: () => request<{ status: string; version: string }>("/api/v1/health"),

  listIntegrations: () => request<Integration[]>("/api/v1/integrations"),

  deleteIntegration: (id: string) =>
    request<void>(`/api/v1/integrations/${id}`, { method: "DELETE" }),

  createBitrix24OAuth: (body: {
    label: string;
    domain: string;
    client_id: string;
    client_secret: string;
  }) =>
    request<{ integration: Integration; authorize_url: string }>(
      "/api/v1/integrations/bitrix24/oauth",
      { method: "POST", body: JSON.stringify(body) },
    ),

  createBitrix24Webhook: (body: { label: string; webhook_url: string }) =>
    request<Integration>("/api/v1/integrations/bitrix24/webhook", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  exchangeBitrix24Code: (body: {
    integration_id: string;
    code: string;
    domain: string;
    member_id?: string | null;
    scope?: string | null;
  }) =>
    request<Integration>("/api/v1/integrations/bitrix24/oauth/exchange", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
