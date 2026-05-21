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
    // Тело можно прочитать ровно один раз. Сначала забираем как текст, потом
    // пробуем распарсить как JSON — иначе .json()→.text() как fallback падает
    // с "body stream already read".
    const raw = await resp.text();
    let body: unknown = raw;
    try {
      body = raw ? JSON.parse(raw) : raw;
    } catch {
      // оставляем raw текст
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

export type Sentiment = "positive" | "neutral" | "negative";

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
  sentiment_score: number | null;
  summary: string | null;
  summary_at: string | null;
  summary_model: string | null;
  summary_messages_count: number | null;
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

// Phase 4Б — расширенный дашборд.

export type KPI = {
  value: number;
  delta_pct: number | null;
  delta_abs: number | null;
};

export type DashboardOverview = {
  range_days: number;
  range_from: string;
  range_to: string;
  conversations: KPI;
  messages: KPI;
  open_now: number;
  closed_in_period: KPI;
  frt_median_sec: KPI;
  frt_p90_sec: KPI;
  resolution_median_sec: KPI;
  unique_contacts: KPI;
  returning_contacts_pct: KPI;
  avg_messages_per_conv: KPI;
  conversion_to_deal_pct: KPI;
  win_rate_pct: KPI;
  sentiment_avg: number | null;
  sentiment_avg_prev: number | null;
  sentiment_pending_messages: number;
};

export type SentimentBucket = {
  sentiment: Sentiment;
  count: number;
  share: number;
};

export type SentimentResponse = {
  period_days: number;
  total_messages: number;
  analyzed_messages: number;
  pending_messages: number;
  buckets: SentimentBucket[];
  avg_score: number | null;
};

export type TopNegativeConversation = {
  conversation_id: string;
  contact_name: string | null;
  channel: ConversationChannel;
  sentiment_score: number;
  message_count: number;
  last_message_at: string | null;
};
export type TopNegativeResponse = { items: TopNegativeConversation[] };

export type LLMStatus = {
  fast_available: boolean;
  smart_available: boolean;
};

export type TagBucket = {
  tag: string;
  count: number;
  share: number;
};

export type TagsResponse = {
  period_days: number;
  total_messages: number;
  analyzed_messages: number;
  pending_messages: number;
  buckets: TagBucket[];
};

export type FunnelStage = {
  key:
    | "conversations"
    | "with_lead"
    | "with_deal"
    | "with_won_deal"
    | "with_lost_deal";
  label: string;
  count: number;
};

export type FunnelResponse = {
  range_days: number;
  range_from: string;
  range_to: string;
  stages: FunnelStage[];
  conversion_to_lead_pct: number;
  conversion_to_deal_pct: number;
  win_rate_pct: number;
  revenue_won: number;
  currency: string | null;
};

export type TimelinePoint = {
  day: string;
  conversations: number;
  messages: number;
  closed: number;
};

export type DashboardTimeline = {
  range_days: number;
  points: TimelinePoint[];
};

export type ByChannelSlice = {
  channel: ConversationChannel;
  conversations: number;
  messages: number;
};

export type ByChannelResponse = { slices: ByChannelSlice[] };

export type ManagerRow = {
  operator_id: string;
  full_name: string | null;
  avatar_url: string | null;
  work_position: string | null;
  email: string | null;
  conversations: number;
  open_conversations: number;
  frt_median_sec: number | null;
  frt_p90_sec: number | null;
  messages_sent: number;
};

export type ByManagerResponse = { rows: ManagerRow[] };

export type LineRow = {
  line_id: string;
  name: string | null;
  integration_id: string;
  conversations: number;
  open_conversations: number;
  messages: number;
  frt_median_sec: number | null;
};

export type ByLineResponse = { rows: LineRow[] };

export type HeatmapCell = { weekday: number; hour: number; count: number };
export type HeatmapResponse = { cells: HeatmapCell[] };

export type SLABreachItem = {
  conversation_id: string;
  contact_name: string | null;
  channel: ConversationChannel;
  minutes_waiting: number;
  last_client_message_at: string;
  operator_id: string | null;
  operator_name: string | null;
};
export type SLABreachesResponse = {
  threshold_minutes: number;
  items: SLABreachItem[];
};

export type TopContactItem = {
  contact_external_id: string | null;
  contact_name: string | null;
  conversations: number;
  messages: number;
  last_message_at: string | null;
};
export type TopContactsResponse = { items: TopContactItem[] };

export type PortalUser = {
  external_id: string;
  full_name: string | null;
  email: string | null;
  work_position: string | null;
  avatar_url: string | null;
  is_active: boolean;
};

export type DashboardFilters = {
  days?: number;
  integration_id?: string;
  channel?: ConversationChannel;
  operator_id?: string;
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

/** Скачивает CSV по абсолютному пути API. Корректно работает с cookies (JWT
 * через credentials: 'include'), затем превращает blob в файл и кликает
 * по ссылке скачивания. Браузерное окно не открывается. */
export async function downloadCSV(path: string, filename: string): Promise<void> {
  const url = path.startsWith("http") ? path : `${API_URL}${path}`;
  const token = tokenStore.get();
  const resp = await fetch(url, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) {
    throw new Error(`Не удалось скачать CSV (${resp.status})`);
  }
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
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

  connectBitrix24: (body: {
    domain: string;
    label?: string;
    client_id?: string;
    client_secret?: string;
  }) =>
    request<Integration>("/api/v1/integrations/bitrix24/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getBitrix24Config: () =>
    request<{ has_global_credentials: boolean; install_url: string }>(
      "/api/v1/integrations/bitrix24/config",
    ),

  // --- Conversations / Dashboard ---
  listConversations: (params: {
    integration_id?: string;
    channel?: ConversationChannel;
    status?: "open" | "closed";
    operator_id?: string;
    line_id?: string;
    sentiment?: Sentiment;
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

  // --- Dashboard (phase 4Б) ---
  getDashboardOverview: (f: DashboardFilters = {}) =>
    request<DashboardOverview>(`/api/v1/dashboard/overview${qs(f)}`),

  getDashboardTimeline: (f: DashboardFilters = {}) =>
    request<DashboardTimeline>(`/api/v1/dashboard/timeline${qs(f)}`),

  getDashboardByChannel: (f: DashboardFilters = {}) =>
    request<ByChannelResponse>(`/api/v1/dashboard/by-channel${qs(f)}`),

  getDashboardByManager: (f: DashboardFilters & { limit?: number } = {}) =>
    request<ByManagerResponse>(`/api/v1/dashboard/by-manager${qs(f)}`),

  getDashboardByLine: (f: DashboardFilters & { limit?: number } = {}) =>
    request<ByLineResponse>(`/api/v1/dashboard/by-line${qs(f)}`),

  getDashboardHeatmap: (f: DashboardFilters = {}) =>
    request<HeatmapResponse>(`/api/v1/dashboard/heatmap${qs(f)}`),

  getDashboardSLABreaches: (
    f: DashboardFilters & { threshold_minutes?: number; limit?: number } = {},
  ) => request<SLABreachesResponse>(`/api/v1/dashboard/sla-breaches${qs(f)}`),

  getDashboardTopContacts: (f: DashboardFilters & { limit?: number } = {}) =>
    request<TopContactsResponse>(`/api/v1/dashboard/top-contacts${qs(f)}`),

  getDashboardFunnel: (f: DashboardFilters = {}) =>
    request<FunnelResponse>(`/api/v1/dashboard/funnel${qs(f)}`),

  getDashboardSentiment: (f: DashboardFilters & { days?: number } = {}) =>
    request<SentimentResponse>(`/api/v1/dashboard/sentiment${qs(f)}`),

  getDashboardTopNegative: (f: DashboardFilters & { limit?: number } = {}) =>
    request<TopNegativeResponse>(
      `/api/v1/dashboard/top-negative-conversations${qs(f)}`,
    ),

  getDashboardTags: (f: DashboardFilters & { limit?: number } = {}) =>
    request<TagsResponse>(`/api/v1/dashboard/tags${qs(f)}`),

  triggerTagsAnalysis: (integrationId: string, batchSize = 200) =>
    request<{ status: string; job_id: string; integration_id: string }>(
      `/api/v1/integrations/${integrationId}/analyze-tags${qs({ batch_size: batchSize })}`,
      { method: "POST" },
    ),

  triggerSentimentAnalysis: (integrationId: string, batchSize = 200) =>
    request<{ status: string; job_id: string; integration_id: string }>(
      `/api/v1/integrations/${integrationId}/analyze-sentiment${qs({ batch_size: batchSize })}`,
      { method: "POST" },
    ),

  getLLMStatus: () => request<LLMStatus>("/api/v1/system/llm-status"),

  summarizeConversation: (conversationId: string) =>
    request<{ status: string; job_id: string; conversation_id: string }>(
      `/api/v1/conversations/${conversationId}/summarize`,
      { method: "POST" },
    ),

  getPortalUsers: (params: { integration_id?: string; only_active?: boolean } = {}) =>
    request<PortalUser[]>(
      `/api/v1/dashboard/portal-users${qs({
        ...params,
        only_active: params.only_active === false ? "false" : undefined,
      } as Record<string, string | number | undefined | null>)}`,
    ),
};
