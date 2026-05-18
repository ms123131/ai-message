import { Fragment } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, Clock, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type ConversationChannel, type DashboardFilters } from "../../lib/api";
import { KPICard } from "../../components/dashboard/KPICard";
import { fmtDateShort, fmtMinutesWaiting } from "../../components/dashboard/format";

const CHANNEL_LABELS: Record<ConversationChannel, string> = {
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  vk: "ВКонтакте",
  instagram: "Instagram",
  facebook: "Facebook",
  livechat: "Виджет",
  email: "Email",
  other: "Другое",
};

const CHANNEL_COLORS: Record<ConversationChannel, string> = {
  whatsapp: "#22c55e",
  telegram: "#0ea5e9",
  vk: "#3b82f6",
  instagram: "#ec4899",
  facebook: "#6366f1",
  livechat: "#8b5cf6",
  email: "#f59e0b",
  other: "#94a3b8",
};

const WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export function OverviewTab({ filters }: { filters: DashboardFilters }) {
  const overviewQ = useQuery({
    queryKey: ["dash-overview", filters],
    queryFn: () => api.getDashboardOverview(filters),
    refetchInterval: 30_000,
  });
  const timelineQ = useQuery({
    queryKey: ["dash-timeline", filters],
    queryFn: () => api.getDashboardTimeline(filters),
    refetchInterval: 30_000,
  });
  const byChannelQ = useQuery({
    queryKey: ["dash-by-channel", filters],
    queryFn: () => api.getDashboardByChannel(filters),
    refetchInterval: 30_000,
  });
  const heatmapQ = useQuery({
    queryKey: ["dash-heatmap", filters],
    queryFn: () => api.getDashboardHeatmap(filters),
    refetchInterval: 60_000,
  });
  const slaQ = useQuery({
    queryKey: ["dash-sla", filters],
    queryFn: () =>
      api.getDashboardSLABreaches({ ...filters, threshold_minutes: 15 }),
    refetchInterval: 30_000,
  });

  const o = overviewQ.data;

  return (
    <div className="space-y-6">
      {overviewQ.isError && (
        <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Не удалось загрузить метрики: {(overviewQ.error as Error).message}
        </div>
      )}

      {/* Ряд 1 — объём */}
      <Section title="Объём и активность">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <KPICard
            label="Сообщений"
            kpi={o?.messages}
            loading={overviewQ.isLoading}
          />
          <KPICard
            label="Диалогов"
            kpi={o?.conversations}
            loading={overviewQ.isLoading}
          />
          <KPICard
            label="Открыто сейчас"
            value={o?.open_now}
            loading={overviewQ.isLoading}
            hint="мгновенный снимок"
          />
          <KPICard
            label="Сообщений на диалог"
            kpi={o?.avg_messages_per_conv}
            loading={overviewQ.isLoading}
          />
        </div>
      </Section>

      {/* Ряд 2 — качество */}
      <Section title="Качество обслуживания">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <KPICard
            label="FRT медиана"
            kpi={o?.frt_median_sec}
            format="duration"
            higherIsBetter={false}
            loading={overviewQ.isLoading}
            hint="первый ответ агента"
          />
          <KPICard
            label="FRT 90-й перцентиль"
            kpi={o?.frt_p90_sec}
            format="duration"
            higherIsBetter={false}
            loading={overviewQ.isLoading}
            hint="самые медленные 10%"
          />
          <KPICard
            label="Время решения"
            kpi={o?.resolution_median_sec}
            format="duration"
            higherIsBetter={false}
            loading={overviewQ.isLoading}
            hint="медиана"
          />
          <KPICard
            label="Возвратных контактов"
            kpi={o?.returning_contacts_pct}
            format="percent"
            loading={overviewQ.isLoading}
            hint="% c >1 обращением"
          />
        </div>
      </Section>

      {/* Графики: timeline + по каналам */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Динамика сообщений" className="xl:col-span-2">
          {timelineQ.isLoading ? (
            <Center>
              <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
            </Center>
          ) : (timelineQ.data?.points ?? []).every((p) => p.messages === 0) ? (
            <EmptyChart text="Нет сообщений за выбранный период" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={timelineQ.data?.points ?? []}>
                <defs>
                  <linearGradient id="msgFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3a66f5" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#3a66f5" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="day"
                  stroke="#94a3b8"
                  fontSize={11}
                  tickFormatter={fmtDateShort}
                />
                <YAxis stroke="#94a3b8" fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                  }}
                  labelFormatter={(l) => fmtDateShort(String(l))}
                  formatter={(v: number) => [v, "сообщений"]}
                />
                <Area
                  type="monotone"
                  dataKey="messages"
                  stroke="#3a66f5"
                  strokeWidth={2}
                  fill="url(#msgFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="По каналам">
          {byChannelQ.isLoading ? (
            <Center>
              <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
            </Center>
          ) : (byChannelQ.data?.slices ?? []).length === 0 ? (
            <EmptyChart text="Каналов не было" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={byChannelQ.data!.slices.map((s) => ({
                    name: CHANNEL_LABELS[s.channel] ?? s.channel,
                    value: s.messages,
                    channel: s.channel,
                  }))}
                  dataKey="value"
                  innerRadius={60}
                  outerRadius={95}
                  paddingAngle={2}
                  stroke="none"
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={false}
                  fontSize={11}
                >
                  {byChannelQ.data!.slices.map((s) => (
                    <Cell
                      key={s.channel}
                      fill={CHANNEL_COLORS[s.channel] ?? "#94a3b8"}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Heatmap + SLA */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card title="Когда пишут клиенты" className="xl:col-span-2">
          <Heatmap cells={heatmapQ.data?.cells ?? []} loading={heatmapQ.isLoading} />
        </Card>

        <Card title="Ожидают ответа > 15 минут" subtitle="нарушения SLA">
          <SLAList
            items={slaQ.data?.items ?? []}
            loading={slaQ.isLoading}
          />
        </Card>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
        {title}
      </div>
      {children}
    </div>
  );
}

function Card({
  title,
  subtitle,
  className,
  children,
}: {
  title: string;
  subtitle?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-lg border border-slate-200 bg-white p-5 ${className ?? ""}`}
    >
      <div className="mb-3">
        <div className="text-sm font-medium text-slate-700">{title}</div>
        {subtitle && (
          <div className="text-xs text-slate-400">{subtitle}</div>
        )}
      </div>
      {children}
    </div>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-[260px] items-center justify-center">{children}</div>
  );
}

function EmptyChart({ text }: { text: string }) {
  return (
    <div className="flex h-[260px] items-center justify-center text-sm text-slate-400">
      {text}
    </div>
  );
}

function Heatmap({
  cells,
  loading,
}: {
  cells: { weekday: number; hour: number; count: number }[];
  loading?: boolean;
}) {
  if (loading) {
    return <Center>
      <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
    </Center>;
  }
  if (cells.length === 0) {
    return <EmptyChart text="Нет данных" />;
  }
  // Транспонируем в карту [weekday][hour] = count.
  const grid: Record<number, Record<number, number>> = {};
  let max = 0;
  for (const c of cells) {
    if (!grid[c.weekday]) grid[c.weekday] = {};
    grid[c.weekday][c.hour] = c.count;
    if (c.count > max) max = c.count;
  }

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid min-w-full grid-cols-[40px_repeat(24,minmax(20px,1fr))] gap-0.5">
        <div />
        {Array.from({ length: 24 }, (_, h) => (
          <div
            key={h}
            className="text-center text-[10px] text-slate-400 tabular-nums"
          >
            {h % 3 === 0 ? h : ""}
          </div>
        ))}
        {WEEKDAYS_RU.map((wd, wi) => (
          <Fragment key={wi}>
            <div className="pr-2 text-right text-[11px] font-medium text-slate-500">
              {wd}
            </div>
            {Array.from({ length: 24 }, (_, h) => {
              const v = grid[wi]?.[h] ?? 0;
              const intensity = max > 0 ? v / max : 0;
              return (
                <div
                  key={`c-${wi}-${h}`}
                  title={`${wd} ${h}:00 — ${v} сообщений`}
                  className="aspect-square rounded-sm"
                  style={{
                    backgroundColor:
                      intensity === 0
                        ? "#f1f5f9"
                        : `rgba(58, 102, 245, ${0.15 + 0.85 * intensity})`,
                  }}
                />
              );
            })}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function SLAList({
  items,
  loading,
}: {
  items: import("../../lib/api").SLABreachItem[];
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex h-[260px] items-center justify-center text-sm text-slate-400">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Загрузка…
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="flex h-[260px] flex-col items-center justify-center gap-1 text-sm text-emerald-600">
        <Clock className="h-6 w-6" />
        <div className="font-medium">Все диалоги в норме</div>
        <div className="text-xs text-slate-400">
          Нарушений SLA не обнаружено
        </div>
      </div>
    );
  }
  return (
    <ul className="max-h-[260px] divide-y divide-slate-100 overflow-y-auto">
      {items.slice(0, 10).map((b) => (
        <li key={b.conversation_id} className="flex items-start gap-2 py-2">
          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-rose-50 text-rose-600">
            <Clock className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">
              {b.contact_name || "Без имени"}
            </div>
            <div className="text-xs text-slate-500">
              {CHANNEL_LABELS[b.channel] ?? b.channel} ·{" "}
              {b.operator_name ? `→ ${b.operator_name}` : "оператор не назначен"}
            </div>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-xs font-medium text-rose-700">
              {fmtMinutesWaiting(b.minutes_waiting)}
            </div>
            <Link
              to={`/inbox?conv=${b.conversation_id}`}
              className="text-xs text-brand-600 hover:underline"
            >
              открыть
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

