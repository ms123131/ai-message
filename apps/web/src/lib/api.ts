// REST-клиент для apps/api. URL берётся из VITE_API_URL.

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ??
  "";

const TOKEN_KEY = "ai_access_token";

// In-memory + localStorage хранилище access-токена.
// localStorage — чтобы переживать F5; refresh лежит в HttpOnly cookie.
export const tokenStore = {
  get(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  set(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear(): void {
    localStorage.removeItem(TOKEN_KEY);
  },
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
    message: string,
  ) {
    super(message);
  }
}

async function tryRefresh(): Promise<string | null> {
  try {
    const resp = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { access_token: string };
    if (data.access_token) {
      tokenStore.set(data.access_token);
      return data.access_token;
    }
    return null;
  } catch {
    return null;
  }
}

async function rawRequest(
  path: string,
  init: RequestInit,
  token: string | null,
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string> | undefined) ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isAuthPath = path.startsWith("/api/v1/auth/");
  let token = tokenStore.get();
  let resp = await rawRequest(path, init, token);

  // На 401 пробуем тихо обновить access через refresh-cookie и повторить.
  if (resp.status === 401 && !isAuthPath) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      token = refreshed;
      resp = await rawRequest(path, init, token);
    }
    if (resp.status === 401) {
      tokenStore.clear();
      if (onUnauthorized) onUnauthorized();
    }
  }

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

// --- Domain types ---

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

export type ConversationChannel =
  | "whatsapp"
  | "telegram"
  | "vk"
  | "instagram"
  | "facebook"
  | "livechat"
  | "email"
  | "other";

export type ConversationStatus = "open" | "closed";
export type SenderType = "client" | "agent" | "bot" | "system";

export type Conversation = {
  id: string;
  integration_id: string;
  external_id: string;
  channel: ConversationChannel;
  contact_name: string | null;
  contact_external_id: string | null;
  status: ConversationStatus;
  created_at: string;
  updated_at: string;
};

export type ConversationListItem = Conversation & {
  message_count: number;
  last_message_at: string | null;
  last_message_preview: string | null;
};

export type Message = {
  id: string;
  conversation_id: string;
  external_id: string | null;
  sender_type: SenderType;
  sender_external_id: string | null;
  text: string | null;
  attachments: Array<Record<string, unknown>> | null;
  sent_at: string;
};

export type DashboardStats = {
  range_days: number;
  range_from: string;
  range_to: string;
  total_conversations: number;
  total_messages: number;
  open_conversations: number;
  volume_by_day: Array<{ day: string; count: number }>;
  by_channel: Array<{
    channel: ConversationChannel;
    conversations: number;
    messages: number;
  }>;
};

export type UserRole = "admin" | "member";

export type CurrentUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  tenant_id: string;
  created_at: string;
};

export type TenantInfo = {
  id: string;
  name: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: CurrentUser;
  tenant: TenantInfo;
};

function qs(params: Record<string, string | number | undefined | null>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/v1/health"),

  // --- Auth ---
  register: (body: {
    email: string;
    password: string;
    full_name?: string;
    workspace_name?: string;
  }) =>
    request<AuthResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  login: (body: { email: string; password: string }) =>
    request<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  refresh: () =>
    request<AuthResponse>("/api/v1/auth/refresh", { method: "POST" }),

  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),

  me: () => request<AuthResponse>("/api/v1/auth/me"),

  // --- Integrations ---
  listIntegrations: () => request<Integration[]>("/api/v1/integrations"),

  deleteIntegration: (id: string) =>
    request<void>(`/api/v1/integrations/${id}`, { method: "DELETE" }),

  connectBitrix24: (body: { domain: string; label?: string }) =>
    request<Integration>("/api/v1/integrations/bitrix24/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // --- Conversations / Dashboard ---
  listConversations: (params: {
    integration_id?: string;
    channel?: ConversationChannel;
    limit?: number;
    offset?: number;
  } = {}) =>
    request<ConversationListItem[]>(`/api/v1/conversations${qs(params)}`),

  getConversation: (id: string) =>
    request<Conversation>(`/api/v1/conversations/${id}`),

  listMessages: (conversationId: string, params: { limit?: number; offset?: number } = {}) =>
    request<Message[]>(`/api/v1/conversations/${conversationId}/messages${qs(params)}`),

  getDashboardStats: (params: { days?: number; integration_id?: string } = {}) =>
    request<DashboardStats>(`/api/v1/dashboard/stats${qs(params)}`),
};
