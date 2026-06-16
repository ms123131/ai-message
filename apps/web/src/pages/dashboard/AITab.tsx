import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertCircle,
  Boxes,
  CheckCircle2,
  Hash,
  Loader2,
  Network,
  Play,
  Smile,
  Sparkles,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { SentimentBadge } from "../../components/SentimentBadge";
import { fmtDateShort } from "../../components/dashboard/format";
import {
  api,
  type DashboardFilters,
  type EntityGroup,
  type Integration,
  type SentimentBucket,
  type SentimentDayPoint,
  type SentimentOperatorRow,
  type TagBucket,
  type TopNegativeConversation,
} from "../../lib/api";
import { buildInboxLink } from "../../components/dashboard/inboxLink";

const SENTIMENT_COLORS: Record<SentimentBucket["sentiment"], string> = {
  positive: "#10b981",
  neutral: "#94a3b8",
  negative: "#f43f5e",
};
const SENTIMENT_LABEL: Record<SentimentBucket["sentiment"], string> = {
  positive: "Позитив",
  neutral: "Нейтрально",
  negative: "Негатив",
};

function fmtScore(v: number | null): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}`;
}

function fmtCount(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n);
}

export function AITab({ filters }: { filters: DashboardFilters }) {
  return (
    <div className="space-y-6">
      <Hero />
      <ControlPanel filters={filters} />
      <SentimentBlock filters={filters} />
      <SentimentTimelineBlock filters={filters} />
      <TagsBlock filters={filters} />
      <EntitiesBlock filters={filters} />
    </div>
  );
}

function Hero() {
  return (
    <div className="relative overflow-hidden rounded-xl border border-brand-200 bg-gradient-to-br from-brand-50 via-white to-violet-50 p-6">
      <div className="flex items-start gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-white shadow-sm">
          <Sparkles className="h-6 w-6 text-brand-600" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-slate-900">AI-аналитика</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Тональность клиентов, авто-теги тем, распознавание сущностей в
            сообщениях и семантический поиск похожих диалогов. NLP работает
            автоматически; ниже — статус функций, динамика тональности и топ
            упомянутых сущностей.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AI Control Panel — статус NLP-функций + ручные триггеры
// ---------------------------------------------------------------------------

type NlpFeature = "sentiment" | "tags" | "entities" | "embeddings";

const FEATURE_META: Record<
  NlpFeature,
  { label: string; hint: string; icon: typeof Smile; accent: string }
> = {
  sentiment: {
    label: "Тональность",
    hint: "Эмоциональная окраска клиентских сообщений",
    icon: Smile,
    accent: "bg-emerald-50 text-emerald-600",
  },
  tags: {
    label: "Темы (теги)",
    hint: "Классификация обращений по словарю портала",
    icon: Hash,
    accent: "bg-violet-50 text-violet-600",
  },
  entities: {
    label: "Сущности",
    hint: "Суммы, компании, города, контакты в тексте",
    icon: Boxes,
    accent: "bg-sky-50 text-sky-600",
  },
  embeddings: {
    label: "Эмбеддинги",
    hint: "Векторы для поиска похожих диалогов",
    icon: Network,
    accent: "bg-amber-50 text-amber-600",
  },
};

const TRIGGERS: Record<NlpFeature, (integrationId: string) => Promise<unknown>> =
  {
    sentiment: (id) => api.triggerSentimentAnalysis(id),
    tags: (id) => api.triggerTagsAnalysis(id),
    entities: (id) => api.triggerEntitiesAnalysis(id),
    embeddings: (id) => api.triggerEmbeddingsAnalysis(id),
  };

// Какой query-ключ инвалидируем после запуска, чтобы освежить счётчики.
const FEATURE_QUERY_KEY: Record<NlpFeature, string | null> = {
  sentiment: "dash-sentiment",
  tags: "dash-tags",
  entities: "dash-entities",
  embeddings: null,
};

function ControlPanel({ filters }: { filters: DashboardFilters }) {
  const qc = useQueryClient();
  const integrationsQ = useQuery({
    queryKey: ["integrations"],
    queryFn: api.listIntegrations,
  });
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });
  // Те же ключи, что в SentimentBlock/TagsBlock/EntitiesBlock — react-query
  // делит кэш, лишних запросов нет.
  const sentimentQ = useQuery({
    queryKey: ["dash-sentiment", filters],
    queryFn: () => api.getDashboardSentiment(filters),
    refetchInterval: 30_000,
  });
  const tagsQ = useQuery({
    queryKey: ["dash-tags", filters],
    queryFn: () => api.getDashboardTags({ ...filters, limit: 20 }),
    refetchInterval: 60_000,
  });
  const entitiesQ = useQuery({
    queryKey: ["dash-entities", filters],
    queryFn: () => api.getEntitiesTop({ ...filters, limit: 10 }),
    refetchInterval: 60_000,
  });

  const integrations = integrationsQ.data ?? [];
  const [selectedId, setSelectedId] = useState<string>("");
  const integrationId =
    selectedId || (integrations.length > 0 ? integrations[0].id : "");

  const fastReady = llmStatusQ.data?.fast_available ?? false;

  const mutation = useMutation({
    mutationFn: ({
      feature,
      id,
    }: {
      feature: NlpFeature;
      id: string;
    }) => TRIGGERS[feature](id),
    onSuccess: (_data, { feature }) => {
      toast.success(`${FEATURE_META[feature].label}: анализ запущен`);
      const key = FEATURE_QUERY_KEY[feature];
      // Воркер обрабатывает батч асинхронно — освежим счётчики чуть позже.
      if (key) {
        setTimeout(() => qc.invalidateQueries({ queryKey: [key] }), 2500);
      }
    },
    onError: (err) => {
      toast.error((err as Error).message || "Не удалось запустить анализ");
    },
  });

  const counts: Record<
    NlpFeature,
    { analyzed: number | null; pending: number | null }
  > = {
    sentiment: {
      analyzed: sentimentQ.data?.analyzed_messages ?? null,
      pending: sentimentQ.data?.pending_messages ?? null,
    },
    tags: {
      analyzed: tagsQ.data?.analyzed_messages ?? null,
      pending: tagsQ.data?.pending_messages ?? null,
    },
    entities: {
      analyzed: entitiesQ.data?.analyzed_messages ?? null,
      pending: null,
    },
    embeddings: { analyzed: null, pending: null },
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-medium text-slate-800">AI Control Panel</div>
          <div className="text-xs text-slate-500">
            Статус NLP-функций и ручной перезапуск анализа
          </div>
        </div>
        <div className="flex items-center gap-2">
          {integrations.length > 1 && (
            <select
              value={integrationId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="rounded-md border border-slate-200 px-2.5 py-1.5 text-sm text-slate-700 outline-none focus:border-brand-500"
            >
              {integrations.map((i: Integration) => (
                <option key={i.id} value={i.id}>
                  {i.label || i.domain}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {!llmStatusQ.isLoading && !fastReady && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <div className="font-medium">LLM не настроен</div>
            <div className="mt-0.5 text-amber-700">
              Задайте <code className="font-mono">LLM_FAST_PROVIDER</code> /{" "}
              <code className="font-mono">LLM_FAST_API_KEY</code> в окружении
              backend — без этого тональность и теги не считаются.
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {(Object.keys(FEATURE_META) as NlpFeature[]).map((feature) => {
          const meta = FEATURE_META[feature];
          const { analyzed, pending } = counts[feature];
          const Icon = meta.icon;
          const isRunning =
            mutation.isPending && mutation.variables?.feature === feature;
          // sentiment/tags зависят от fast LLM; entities/embeddings — нет.
          const needsFast = feature === "sentiment" || feature === "tags";
          const disabled =
            isRunning || !integrationId || (needsFast && !fastReady);
          return (
            <div
              key={feature}
              className="flex flex-col rounded-lg border border-slate-100 bg-slate-50 p-3"
            >
              <div className="flex items-start gap-2.5">
                <div
                  className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${meta.accent}`}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-800">
                    {meta.label}
                  </div>
                  <div className="text-[11px] leading-tight text-slate-500">
                    {meta.hint}
                  </div>
                </div>
              </div>
              <div className="mt-3 space-y-1 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Проанализировано</span>
                  <span className="tabular-nums font-medium text-slate-700">
                    {analyzed === null ? "—" : fmtCount(analyzed)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">В очереди</span>
                  <span
                    className={`tabular-nums font-medium ${
                      pending && pending > 0 ? "text-sky-700" : "text-slate-400"
                    }`}
                  >
                    {pending === null ? "—" : fmtCount(pending)}
                  </span>
                </div>
              </div>
              <Button
                variant="secondary"
                className="mt-3 w-full"
                disabled={disabled}
                title={
                  !integrationId
                    ? "Нет подключённых интеграций"
                    : needsFast && !fastReady
                      ? "Нужен fast LLM-провайдер"
                      : undefined
                }
                onClick={() => mutation.mutate({ feature, id: integrationId })}
              >
                {isRunning ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Запуск…
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" /> Запустить
                  </>
                )}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sentiment-блок (донат + топ негативных) — без изменений
// ---------------------------------------------------------------------------

function SentimentBlock({ filters }: { filters: DashboardFilters }) {
  const sentimentQ = useQuery({
    queryKey: ["dash-sentiment", filters],
    queryFn: () => api.getDashboardSentiment(filters),
    refetchInterval: 30_000,
  });
  const topNegativeQ = useQuery({
    queryKey: ["dash-top-negative", filters],
    queryFn: () => api.getDashboardTopNegative({ ...filters, limit: 10 }),
    refetchInterval: 60_000,
  });
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });

  const data = sentimentQ.data;
  const llmReady = llmStatusQ.data?.fast_available ?? false;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-600">
            <Smile className="h-5 w-5" />
          </div>
          <div>
            <div className="font-medium text-slate-800">
              Тональность клиентов
            </div>
            <div className="text-xs text-slate-500">
              Sentiment-разметка клиентских сообщений через LLM
            </div>
          </div>
        </div>
        <AutoStatusBadge
          llmReady={llmReady}
          pending={sentimentQ.data?.pending_messages ?? 0}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <DonutChart data={data?.buckets ?? []} loading={sentimentQ.isLoading} />
          <KpiStrip data={data} loading={sentimentQ.isLoading} />
        </div>
        <div className="lg:col-span-2">
          <TopNegativeList
            items={topNegativeQ.data?.items ?? []}
            loading={topNegativeQ.isLoading}
            filters={filters}
          />
        </div>
      </div>
    </div>
  );
}

function DonutChart({
  data,
  loading,
}: {
  data: SentimentBucket[];
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex h-[180px] items-center justify-center">
        <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
      </div>
    );
  }
  const total = data.reduce((s, b) => s + b.count, 0);
  if (total === 0) {
    return (
      <div className="flex h-[180px] flex-col items-center justify-center gap-1 text-center text-xs text-slate-400">
        <Smile className="h-6 w-6 text-slate-300" />
        Пока нет проанализированных сообщений
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <PieChart>
        <Pie
          data={data.map((b) => ({
            name: SENTIMENT_LABEL[b.sentiment],
            value: b.count,
            sentiment: b.sentiment,
          }))}
          dataKey="value"
          innerRadius={50}
          outerRadius={75}
          paddingAngle={2}
          stroke="none"
        >
          {data.map((b) => (
            <Cell key={b.sentiment} fill={SENTIMENT_COLORS[b.sentiment]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            fontSize: 12,
            borderRadius: 8,
            border: "1px solid #e2e8f0",
          }}
          formatter={(v: number) => [`${v} сообщений`, "Кол-во"]}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

function KpiStrip({
  data,
  loading,
}: {
  data:
    | {
        total_messages: number;
        analyzed_messages: number;
        pending_messages: number;
        avg_score: number | null;
      }
    | undefined;
  loading?: boolean;
}) {
  return (
    <div className="mt-4 space-y-1.5 text-xs">
      <Row
        label="Клиентских сообщений"
        value={loading ? "…" : fmtCount(data?.total_messages ?? 0)}
      />
      <Row
        label="Проанализировано"
        value={loading ? "…" : fmtCount(data?.analyzed_messages ?? 0)}
      />
      <Row
        label="Ждут анализа"
        value={loading ? "…" : fmtCount(data?.pending_messages ?? 0)}
        muted={(data?.pending_messages ?? 0) === 0}
      />
      <Row
        label="Среднее по диалогам"
        value={loading ? "…" : fmtScore(data?.avg_score ?? null)}
        bold
      />
    </div>
  );
}

function Row({
  label,
  value,
  muted,
  bold,
}: {
  label: string;
  value: string;
  muted?: boolean;
  bold?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className={muted ? "text-slate-400" : "text-slate-500"}>
        {label}
      </span>
      <span
        className={`tabular-nums ${bold ? "font-semibold text-slate-900" : "text-slate-700"}`}
      >
        {value}
      </span>
    </div>
  );
}

function TopNegativeList({
  items,
  loading,
  filters,
}: {
  items: TopNegativeConversation[];
  loading?: boolean;
  filters: DashboardFilters;
}) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-slate-700">
          Топ-10 негативных диалогов
        </div>
        <Link
          to={
            buildInboxLink(filters) +
            (buildInboxLink(filters).includes("?") ? "&" : "?") +
            "sentiment=negative"
          }
          className="text-xs text-brand-600 hover:underline"
        >
          смотреть все →
        </Link>
      </div>
      {loading && (
        <div className="flex h-[200px] items-center justify-center">
          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
        </div>
      )}
      {!loading && items.length === 0 && (
        <div className="flex h-[200px] flex-col items-center justify-center gap-2 text-xs text-slate-400">
          <CheckCircle2 className="h-6 w-6 text-emerald-400" />
          Негативных диалогов нет — клиенты довольны
        </div>
      )}
      {!loading && items.length > 0 && (
        <ul className="divide-y divide-slate-200">
          {items.map((it) => (
            <li key={it.conversation_id} className="py-2">
              <Link
                to={`/inbox/${it.conversation_id}`}
                className="flex items-center gap-3 hover:bg-white/70 -mx-2 px-2 py-1 rounded"
              >
                <SentimentBadge
                  score={it.sentiment_score}
                  messageCount={it.message_count}
                  size="lg"
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-slate-800">
                    {it.contact_name ?? "Без имени"}
                  </div>
                  <div className="text-xs text-slate-500">
                    {it.message_count} сообщений
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div
                    className={`font-mono text-sm font-semibold tabular-nums ${
                      it.sentiment_score < -0.2
                        ? "text-rose-700"
                        : it.sentiment_score > 0.2
                          ? "text-emerald-700"
                          : "text-slate-600"
                    }`}
                  >
                    {fmtScore(it.sentiment_score)}
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Бэйдж «авто-режим включён». NLP крутится автоматически — cron каждые
 * 5 минут плюс realtime-триггер на каждое новое клиентское сообщение
 * (см. webhooks.py). Ручной перезапуск — в AI Control Panel выше.
 */
function AutoStatusBadge({
  llmReady,
  pending,
}: {
  llmReady: boolean;
  pending: number;
}) {
  if (!llmReady) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-700">
        LLM не настроен
      </div>
    );
  }
  if (pending > 0) {
    return (
      <div className="flex items-center gap-1.5 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-xs text-sky-700">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Авто-анализ: в очереди {pending}
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs text-emerald-700">
      <span className="h-2 w-2 rounded-full bg-emerald-500" />
      Авто-анализ включён
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sentiment-таймлайн: динамика по дням / срез по операторам
// ---------------------------------------------------------------------------

function SentimentTimelineBlock({ filters }: { filters: DashboardFilters }) {
  const [mode, setMode] = useState<"day" | "operator">("day");
  const timelineQ = useQuery({
    queryKey: ["dash-sentiment-timeline", filters],
    queryFn: () => api.getSentimentTimeline(filters),
    refetchInterval: 60_000,
  });

  const points = timelineQ.data?.points ?? [];
  const operators = timelineQ.data?.by_operator ?? [];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-rose-50 text-rose-600">
            <Smile className="h-5 w-5" />
          </div>
          <div>
            <div className="font-medium text-slate-800">
              Динамика тональности
            </div>
            <div className="text-xs text-slate-500">
              {mode === "day"
                ? "Распределение тональности клиентских сообщений по дням"
                : "Средний sentiment диалогов в разрезе операторов"}
            </div>
          </div>
        </div>
        <div className="inline-flex rounded-md border border-slate-200 p-0.5 text-xs">
          <button
            type="button"
            onClick={() => setMode("day")}
            className={`rounded px-2.5 py-1 font-medium transition ${
              mode === "day"
                ? "bg-brand-600 text-white"
                : "text-slate-600 hover:bg-slate-50"
            }`}
          >
            По дням
          </button>
          <button
            type="button"
            onClick={() => setMode("operator")}
            className={`rounded px-2.5 py-1 font-medium transition ${
              mode === "operator"
                ? "bg-brand-600 text-white"
                : "text-slate-600 hover:bg-slate-50"
            }`}
          >
            По операторам
          </button>
        </div>
      </div>

      {timelineQ.isLoading ? (
        <div className="flex h-[260px] items-center justify-center">
          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
        </div>
      ) : mode === "day" ? (
        <SentimentDayChart points={points} />
      ) : (
        <OperatorList operators={operators} />
      )}
    </div>
  );
}

function SentimentDayChart({ points }: { points: SentimentDayPoint[] }) {
  const hasData = points.some(
    (p) => p.positive + p.neutral + p.negative > 0,
  );
  if (!hasData) {
    return (
      <div className="flex h-[260px] flex-col items-center justify-center gap-1 text-center text-xs text-slate-400">
        <Smile className="h-6 w-6 text-slate-300" />
        За выбранный период нет размеченных сообщений
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart
        data={points}
        margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis
          dataKey="day"
          tickFormatter={(v) => fmtDateShort(String(v))}
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{
            fontSize: 12,
            borderRadius: 8,
            border: "1px solid #e2e8f0",
          }}
          labelFormatter={(l) => fmtDateShort(String(l))}
        />
        <Legend
          iconType="circle"
          wrapperStyle={{ fontSize: 12 }}
          formatter={(value) =>
            SENTIMENT_LABEL[value as SentimentBucket["sentiment"]] ?? value
          }
        />
        <Area
          type="monotone"
          dataKey="positive"
          stackId="1"
          stroke={SENTIMENT_COLORS.positive}
          fill={SENTIMENT_COLORS.positive}
          fillOpacity={0.7}
        />
        <Area
          type="monotone"
          dataKey="neutral"
          stackId="1"
          stroke={SENTIMENT_COLORS.neutral}
          fill={SENTIMENT_COLORS.neutral}
          fillOpacity={0.6}
        />
        <Area
          type="monotone"
          dataKey="negative"
          stackId="1"
          stroke={SENTIMENT_COLORS.negative}
          fill={SENTIMENT_COLORS.negative}
          fillOpacity={0.7}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function OperatorList({ operators }: { operators: SentimentOperatorRow[] }) {
  if (operators.length === 0) {
    return (
      <div className="flex h-[260px] flex-col items-center justify-center gap-1 text-center text-xs text-slate-400">
        <Smile className="h-6 w-6 text-slate-300" />
        Нет данных по операторам за период
      </div>
    );
  }
  // avg_score в диапазоне [-1, 1]; ширину бара считаем от центра.
  return (
    <ul className="space-y-2">
      {operators.map((op) => {
        const score = op.avg_score ?? 0;
        const pct = Math.min(100, Math.abs(score) * 100);
        const positive = score >= 0;
        return (
          <li
            key={op.operator_id}
            className="flex items-center gap-3 text-xs"
          >
            <span className="w-40 shrink-0 truncate text-slate-700">
              {op.full_name || `#${op.operator_id}`}
            </span>
            <div className="flex flex-1 items-center">
              <div className="flex h-2 flex-1 justify-end">
                {!positive && (
                  <div
                    className="h-full rounded-l bg-rose-400"
                    style={{ width: `${pct}%` }}
                  />
                )}
              </div>
              <div className="h-3 w-px bg-slate-300" />
              <div className="flex h-2 flex-1 justify-start">
                {positive && (
                  <div
                    className="h-full rounded-r bg-emerald-400"
                    style={{ width: `${pct}%` }}
                  />
                )}
              </div>
            </div>
            <span
              className={`w-12 text-right font-mono tabular-nums ${
                score < -0.2
                  ? "text-rose-700"
                  : score > 0.2
                    ? "text-emerald-700"
                    : "text-slate-500"
              }`}
            >
              {fmtScore(op.avg_score)}
            </span>
            <span className="w-16 text-right tabular-nums text-slate-400">
              {op.analyzed_conversations} диал.
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Tags-блок: о чём пишут клиенты (донат + список) — без изменений
// ---------------------------------------------------------------------------

const TAG_LABEL_OVERRIDE: Record<string, string> = {
  оплата: "Оплата",
  доставка: "Доставка",
  возврат: "Возврат",
  жалоба: "Жалоба",
  гарантия: "Гарантия",
  вопрос_о_товаре: "Вопрос о товаре",
  техподдержка: "Техподдержка",
  статус_заказа: "Статус заказа",
  другое: "Другое",
};

function tagLabel(slug: string): string {
  return (
    TAG_LABEL_OVERRIDE[slug] ??
    slug.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
  );
}

const TAG_PALETTE = [
  "#8b5cf6",
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ec4899",
  "#06b6d4",
  "#ef4444",
  "#84cc16",
  "#a855f7",
  "#14b8a6",
];

function TagsBlock({ filters }: { filters: DashboardFilters }) {
  const tagsQ = useQuery({
    queryKey: ["dash-tags", filters],
    queryFn: () => api.getDashboardTags({ ...filters, limit: 20 }),
    refetchInterval: 60_000,
  });
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });

  const data = tagsQ.data;
  const llmReady = llmStatusQ.data?.fast_available ?? false;
  const buckets = data?.buckets ?? [];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-violet-50 text-violet-600">
            <Hash className="h-5 w-5" />
          </div>
          <div>
            <div className="font-medium text-slate-800">Темы обращений</div>
            <div className="text-xs text-slate-500">
              О чём пишут клиенты — LLM-классификация по словарю портала
            </div>
          </div>
        </div>
        <AutoStatusBadge
          llmReady={llmReady}
          pending={data?.pending_messages ?? 0}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <TagsDonut buckets={buckets} loading={tagsQ.isLoading} />
          <div className="mt-4 space-y-1.5 text-xs">
            <Row
              label="Клиентских сообщений"
              value={tagsQ.isLoading ? "…" : fmtCount(data?.total_messages ?? 0)}
            />
            <Row
              label="Протегировано"
              value={
                tagsQ.isLoading ? "…" : fmtCount(data?.analyzed_messages ?? 0)
              }
            />
            <Row
              label="Ждут тегирования"
              value={
                tagsQ.isLoading ? "…" : fmtCount(data?.pending_messages ?? 0)
              }
              muted={(data?.pending_messages ?? 0) === 0}
            />
          </div>
        </div>
        <div className="lg:col-span-2">
          <TagsList buckets={buckets} loading={tagsQ.isLoading} />
        </div>
      </div>
    </div>
  );
}

function TagsDonut({
  buckets,
  loading,
}: {
  buckets: TagBucket[];
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex h-[180px] items-center justify-center">
        <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
      </div>
    );
  }
  const total = buckets.reduce((s, b) => s + b.count, 0);
  if (total === 0) {
    return (
      <div className="flex h-[180px] flex-col items-center justify-center gap-1 text-center text-xs text-slate-400">
        <Hash className="h-6 w-6 text-slate-300" />
        Пока нет протегированных сообщений
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <PieChart>
        <Pie
          data={buckets.map((b) => ({
            name: tagLabel(b.tag),
            value: b.count,
          }))}
          dataKey="value"
          innerRadius={50}
          outerRadius={75}
          paddingAngle={2}
          stroke="none"
        >
          {buckets.map((b, i) => (
            <Cell key={b.tag} fill={TAG_PALETTE[i % TAG_PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            fontSize: 12,
            borderRadius: 8,
            border: "1px solid #e2e8f0",
          }}
          formatter={(v: number) => [`${v} сообщений`, "Кол-во"]}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

function TagsList({
  buckets,
  loading,
}: {
  buckets: TagBucket[];
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-lg border border-slate-100 bg-slate-50">
        <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
      </div>
    );
  }
  if (buckets.length === 0) {
    return (
      <div className="flex h-[200px] flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50 text-xs text-slate-400">
        Запустите тегирование, чтобы увидеть темы
      </div>
    );
  }
  const max = Math.max(...buckets.map((b) => b.count), 1);
  return (
    <ul className="space-y-2 rounded-lg border border-slate-100 bg-slate-50 p-4">
      {buckets.map((b, i) => (
        <li key={b.tag} className="flex items-center gap-3 text-xs">
          <span
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: TAG_PALETTE[i % TAG_PALETTE.length] }}
          />
          <span className="truncate text-slate-700">{tagLabel(b.tag)}</span>
          <div className="flex flex-1 items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded bg-slate-200">
              <div
                className="h-full"
                style={{
                  width: `${(b.count / max) * 100}%`,
                  backgroundColor: TAG_PALETTE[i % TAG_PALETTE.length],
                }}
              />
            </div>
            <span className="w-12 text-right tabular-nums text-slate-500">
              {b.count}
            </span>
            <span className="w-10 text-right tabular-nums text-slate-400">
              {(b.share * 100).toFixed(0)}%
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Топ упомянутых сущностей (суммы / компании / города / контакты)
// ---------------------------------------------------------------------------

const ENTITY_KIND_LABEL: Record<string, string> = {
  money: "Суммы",
  organization: "Компании",
  location: "Города и адреса",
  person: "Имена",
  email: "Email",
  phone: "Телефоны",
};

function EntitiesBlock({ filters }: { filters: DashboardFilters }) {
  const entitiesQ = useQuery({
    queryKey: ["dash-entities", filters],
    queryFn: () => api.getEntitiesTop({ ...filters, limit: 10 }),
    refetchInterval: 60_000,
  });

  const groups = entitiesQ.data?.groups ?? [];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-sky-50 text-sky-600">
            <Boxes className="h-5 w-5" />
          </div>
          <div>
            <div className="font-medium text-slate-800">
              Топ упомянутых сущностей
            </div>
            <div className="text-xs text-slate-500">
              Суммы, компании, города и контакты из текста сообщений
            </div>
          </div>
        </div>
        {entitiesQ.data && (
          <div className="text-xs text-slate-400">
            размечено {fmtCount(entitiesQ.data.analyzed_messages)} сообщений
          </div>
        )}
      </div>

      {entitiesQ.isLoading ? (
        <div className="flex h-[160px] items-center justify-center">
          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
        </div>
      ) : groups.length === 0 ? (
        <div className="flex h-[160px] flex-col items-center justify-center gap-1 text-center text-xs text-slate-400">
          <Boxes className="h-6 w-6 text-slate-300" />
          Сущности ещё не извлечены. Запустите анализ в AI Control Panel выше.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {groups.map((g) => (
            <EntityGroupCard key={g.kind} group={g} />
          ))}
        </div>
      )}
    </div>
  );
}

function EntityGroupCard({ group }: { group: EntityGroup }) {
  const max = Math.max(...group.items.map((i) => i.count), 1);
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 p-4">
      <div className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">
        {ENTITY_KIND_LABEL[group.kind] ?? group.kind}
      </div>
      <ul className="space-y-1.5">
        {group.items.map((it) => (
          <li key={it.value} className="flex items-center gap-2 text-xs">
            <span className="min-w-0 flex-1 truncate text-slate-700" title={it.value}>
              {it.value}
            </span>
            <div className="h-1.5 w-16 overflow-hidden rounded bg-slate-200">
              <div
                className="h-full bg-sky-400"
                style={{ width: `${(it.count / max) * 100}%` }}
              />
            </div>
            <span className="w-8 text-right tabular-nums text-slate-500">
              {it.count}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
