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
