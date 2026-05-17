// Локальное хранилище подключений CRM. Временное решение до появления backend.
// Позже заменится на REST-вызовы apps/api.

export type Bitrix24Connection = {
  id: string;
  kind: "bitrix24";
  mode: "oauth" | "webhook";
  /** portal.bitrix24.ru (без протокола) */
  domain: string;
  /** Название для отображения */
  label: string;
  /** OAuth client_id (только для mode=oauth) */
  clientId?: string;
  /** Полный URL входящего webhook'а (только для mode=webhook) */
  webhookUrl?: string;
  /** Полученный OAuth code (демо, до обмена на backend) */
  code?: string;
  memberId?: string;
  scope?: string;
  status: "pending" | "connected" | "error";
  createdAt: string;
};

const KEY = "ai-message:connections";

function read(): Bitrix24Connection[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Bitrix24Connection[]) : [];
  } catch {
    return [];
  }
}

function write(items: Bitrix24Connection[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
}

export function listConnections(): Bitrix24Connection[] {
  return read();
}

export function getConnection(id: string): Bitrix24Connection | undefined {
  return read().find((c) => c.id === id);
}

export function saveConnection(conn: Bitrix24Connection) {
  const items = read();
  const idx = items.findIndex((c) => c.id === conn.id);
  if (idx >= 0) items[idx] = conn;
  else items.push(conn);
  write(items);
}

export function deleteConnection(id: string) {
  write(read().filter((c) => c.id !== id));
}

export function newId(): string {
  return `b24_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Нормализует ввод пользователя: "https://portal.bitrix24.ru/" → "portal.bitrix24.ru"
 */
export function normalizeDomain(input: string): string {
  return input
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/\/.*$/, "")
    .toLowerCase();
}

export function isValidBitrixDomain(domain: string): boolean {
  return /^[a-z0-9-]+\.bitrix24\.(ru|com|by|kz|ua|de|fr|es|it|pl|tr|com\.br|com\.tr)$/i.test(
    domain,
  );
}

/**
 * Формирует URL авторизации Bitrix24.
 * Документация: https://apidocs.bitrix24.ru/api-reference/oauth/index.html
 */
export function buildAuthorizeUrl(params: {
  domain: string;
  clientId: string;
  state: string;
}): string {
  const url = new URL(`https://${params.domain}/oauth/authorize/`);
  url.searchParams.set("client_id", params.clientId);
  url.searchParams.set("state", params.state);
  return url.toString();
}
