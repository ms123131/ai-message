import type { DashboardFilters } from "../../lib/api";

/** Строит ссылку в Inbox с применёнными фильтрами. */
export function buildInboxLink(
  base: DashboardFilters,
  extra: {
    status?: "open" | "closed";
    operator_id?: string;
    line_id?: string;
    conv?: string;
  } = {},
): string {
  const params = new URLSearchParams();
  const merged = {
    integration_id: base.integration_id,
    channel: base.channel,
    operator_id: extra.operator_id ?? base.operator_id,
    status: extra.status,
    line_id: extra.line_id,
    conv: extra.conv,
  };
  for (const [k, v] of Object.entries(merged)) {
    if (v) params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `/inbox?${qs}` : "/inbox";
}
