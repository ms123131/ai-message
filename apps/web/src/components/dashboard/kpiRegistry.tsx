import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { KPICard } from "./KPICard";
import { buildInboxLink } from "./inboxLink";
import { fmtNumber } from "./format";
import type { DashboardFilters, DashboardOverview } from "../../lib/api";

export type KpiGroup = "volume" | "quality" | "crm";

export const KPI_GROUP_LABEL: Record<KpiGroup, string> = {
  volume: "Объём и активность",
  quality: "Качество обслуживания",
  crm: "Конверсия в CRM",
};

export type KpiRenderCtx = {
  o?: DashboardOverview;
  loading: boolean;
  filters: DashboardFilters;
};

export type KpiDescriptor = {
  id: string;
  /** Подпись в панели настройки (карточка рисует свою). */
  label: string;
  group: KpiGroup;
  render: (ctx: KpiRenderCtx) => ReactNode;
};

// Реестр KPI-карточек дашборда. Перенесено из захардкоженного JSX
// OverviewTab — теперь раскладка (порядок + скрытые) задаётся пользователем
// и хранится на бэкенде (User.ui_preferences.dashboard_overview).
export const KPI_REGISTRY: KpiDescriptor[] = [
  {
    id: "messages",
    label: "Сообщений",
    group: "volume",
    render: ({ o, loading }) => (
      <KPICard label="Сообщений" kpi={o?.messages} loading={loading} />
    ),
  },
  {
    id: "conversations",
    label: "Диалогов",
    group: "volume",
    render: ({ o, loading }) => (
      <KPICard label="Диалогов" kpi={o?.conversations} loading={loading} />
    ),
  },
  {
    id: "open_now",
    label: "Открыто сейчас",
    group: "volume",
    render: ({ o, loading, filters }) => (
      <KPICard
        label="Открыто сейчас"
        value={o?.open_now}
        loading={loading}
        hint="мгновенный снимок · перейти к списку"
        linkTo={buildInboxLink(filters, { status: "open" })}
      />
    ),
  },
  {
    id: "closed_in_period",
    label: "Закрыто за период",
    group: "volume",
    render: ({ o, loading, filters }) => (
      <KPICard
        label="Закрыто за период"
        kpi={o?.closed_in_period}
        loading={loading}
        hint="скорость разгребания"
        linkTo={buildInboxLink(filters, { status: "closed" })}
      />
    ),
  },
  {
    id: "avg_messages_per_conv",
    label: "Сообщений на диалог",
    group: "volume",
    render: ({ o, loading }) => (
      <KPICard
        label="Сообщений на диалог"
        kpi={o?.avg_messages_per_conv}
        loading={loading}
        hint="среднее"
      />
    ),
  },
  {
    id: "frt_median_sec",
    label: "Время первого ответа",
    group: "quality",
    render: ({ o, loading }) => (
      <KPICard
        label="Время первого ответа"
        kpi={o?.frt_median_sec}
        format="duration"
        higherIsBetter={false}
        loading={loading}
        hint="медиана"
      />
    ),
  },
  {
    id: "frt_p90_sec",
    label: "Самые медленные ответы",
    group: "quality",
    render: ({ o, loading }) => (
      <KPICard
        label="Самые медленные ответы"
        kpi={o?.frt_p90_sec}
        format="duration"
        higherIsBetter={false}
        loading={loading}
        hint="90-й перцентиль (10% худших)"
      />
    ),
  },
  {
    id: "resolution_median_sec",
    label: "Время решения вопроса",
    group: "quality",
    render: ({ o, loading }) => (
      <KPICard
        label="Время решения вопроса"
        kpi={o?.resolution_median_sec}
        format="duration"
        higherIsBetter={false}
        loading={loading}
        hint="медиана"
      />
    ),
  },
  {
    id: "returning_contacts_pct",
    label: "Возвратные клиенты",
    group: "quality",
    render: ({ o, loading }) => (
      <KPICard
        label="Возвратные клиенты"
        kpi={o?.returning_contacts_pct}
        format="percent"
        loading={loading}
        hint="% с более чем одним обращением"
      />
    ),
  },
  {
    id: "sentiment",
    label: "Средняя тональность",
    group: "quality",
    render: ({ o, loading }) => (
      <SentimentKPICard
        avg={o?.sentiment_avg ?? null}
        prev={o?.sentiment_avg_prev ?? null}
        pending={o?.sentiment_pending_messages ?? 0}
        loading={loading}
      />
    ),
  },
  {
    id: "conversion_to_deal_pct",
    label: "Диалог → сделка",
    group: "crm",
    render: ({ o, loading }) => (
      <KPICard
        label="Диалог → сделка"
        kpi={o?.conversion_to_deal_pct}
        format="percent"
        loading={loading}
        hint="% диалогов, породивших Deal"
      />
    ),
  },
  {
    id: "win_rate_pct",
    label: "Win-rate сделок",
    group: "crm",
    render: ({ o, loading }) => (
      <KPICard
        label="Win-rate сделок"
        kpi={o?.win_rate_pct}
        format="percent"
        loading={loading}
        hint="выиграно / (выиграно + проиграно)"
      />
    ),
  },
];

export const KPI_BY_ID: Record<string, KpiDescriptor> = Object.fromEntries(
  KPI_REGISTRY.map((d) => [d.id, d]),
);

export const KPI_DEFAULT_ORDER: string[] = KPI_REGISTRY.map((d) => d.id);

/**
 * Сводит сохранённый порядок с актуальным реестром: выкидывает неизвестные id
 * (удалённые метрики), дописывает в конец новые (появившиеся после сохранения).
 */
export function resolveKpiOrder(saved?: string[]): string[] {
  const base = (saved ?? []).filter((id) => id in KPI_BY_ID);
  const missing = KPI_DEFAULT_ORDER.filter((id) => !base.includes(id));
  return [...base, ...missing];
}

// --- Спец-карточка тональности (нестандартная окраска/подпись) ---

function formatSentimentScore(v: number | null): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}`;
}

function SentimentKPICard({
  avg,
  prev,
  pending,
  loading,
}: {
  avg: number | null;
  prev: number | null;
  pending: number;
  loading?: boolean;
}) {
  const tone =
    avg === null ? "unknown" : avg > 0.2 ? "pos" : avg < -0.2 ? "neg" : "neu";
  const valueColor =
    tone === "pos"
      ? "text-emerald-600"
      : tone === "neg"
        ? "text-rose-600"
        : tone === "neu"
          ? "text-slate-700"
          : "text-slate-400";

  const delta = avg !== null && prev !== null ? avg - prev : null;
  let TrendIcon = Minus;
  let trendColor = "text-slate-400";
  let trendText = "—";
  if (delta !== null && Number.isFinite(delta)) {
    if (delta > 0.05) {
      TrendIcon = ArrowUpRight;
      trendColor = "text-emerald-600";
    } else if (delta < -0.05) {
      TrendIcon = ArrowDownRight;
      trendColor = "text-rose-600";
    }
    const sign = delta > 0 ? "+" : "";
    trendText = `${sign}${delta.toFixed(2)}`;
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        Средняя тональность
      </div>
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <div className={`text-2xl font-semibold tabular-nums ${valueColor}`}>
          {loading ? (
            <span className="text-slate-300">…</span>
          ) : (
            formatSentimentScore(avg)
          )}
        </div>
        <div
          className={`inline-flex items-center gap-0.5 text-xs font-medium ${trendColor}`}
          title="изменение к предыдущему периоду"
        >
          <TrendIcon className="h-3.5 w-3.5" />
          {trendText}
        </div>
      </div>
      <div className="mt-1 text-xs text-slate-400">
        {avg === null
          ? "нет проанализированных диалогов"
          : pending > 0
            ? `${fmtNumber(pending)} сообщений ещё анализируется`
            : "среднее по клиентским сообщениям, шкала −1…+1"}
      </div>
    </div>
  );
}
