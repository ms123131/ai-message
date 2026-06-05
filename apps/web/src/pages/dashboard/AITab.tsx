import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  AlertCircle,
  CheckCircle2,
  Hash,
  Lightbulb,
  Loader2,
  Lock,
  Smile,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wand2,
} from "lucide-react";
import { SentimentBadge } from "../../components/SentimentBadge";
import {
  api,
  type DashboardFilters,
  type SentimentBucket,
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
      <SentimentBlock filters={filters} />
      <TagsBlock filters={filters} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {LOCKED_FEATURES.map((f) => (
          <FeatureCard key={f.title} {...f} />
        ))}
      </div>
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
          <h2 className="text-lg font-semibold text-slate-900">
            AI-аналитика
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Готово: тональность клиента, авто-теги тем, сводка диалога одной
            кнопкой, распознавание контактов и сущностей в сообщениях.
            Дальше — обнаружение аномалий, оценка качества ответов и
            еженедельные инсайты.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sentiment-блок
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

      {!llmStatusQ.isLoading && !llmReady && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <div className="font-medium">AI-функции отключены</div>
            <div className="mt-0.5 text-amber-700">
              Задайте <code className="font-mono">LLM_FAST_PROVIDER</code> и
              <code className="font-mono"> LLM_FAST_API_KEY</code> в окружении
              backend (см. <code className="font-mono">apps/api/.env.example</code>).
              Без этого тональность не считается.
            </div>
          </div>
        </div>
      )}

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
            <Cell
              key={b.sentiment}
              fill={SENTIMENT_COLORS[b.sentiment]}
            />
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
  data: { total_messages: number; analyzed_messages: number; pending_messages: number; avg_score: number | null } | undefined;
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
                to={buildInboxLink(filters, { conv: it.conversation_id })}
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
 * Бэйдж «авто-режим включён». Заменил собой кнопки «Запустить анализ» /
 * «Запустить тегирование»: NLP теперь крутится автоматически — cron каждые
 * 5 минут плюс realtime-триггер на каждое новое клиентское сообщение
 * (см. webhooks.py). Кнопка превратилась в пассивный индикатор статуса.
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
// Tags-блок: о чём пишут клиенты (донат + список)
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
              value={tagsQ.isLoading ? "…" : fmtCount(data?.analyzed_messages ?? 0)}
            />
            <Row
              label="Ждут тегирования"
              value={tagsQ.isLoading ? "…" : fmtCount(data?.pending_messages ?? 0)}
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
// Прочие lock-карточки — без изменений по содержанию
// ---------------------------------------------------------------------------

type Feature = {
  icon: typeof Sparkles;
  title: string;
  description: string;
  preview: React.ReactNode;
  accent: string;
};

const LOCKED_FEATURES: Feature[] = [
  {
    icon: AlertCircle,
    accent: "bg-rose-50 text-rose-600",
    title: "Обнаружение аномалий",
    description:
      "Мониторинг резких всплесков по темам и тональности. Уведомление, когда что-то идёт не так — до того, как заметит руководитель.",
    preview: (
      <AnomalyPreview text="Жалоб на «не приходит код» сегодня в 4× выше нормы" />
    ),
  },
  {
    icon: Wand2,
    accent: "bg-amber-50 text-amber-600",
    title: "Оценка качества ответов",
    description:
      "LLM проверяет диалог по чек-листу: эмпатия, полнота ответа, корректность, грамматика. Не только скорость, но и качество.",
    preview: <QualityScorePreview score={87} />,
  },
  {
    icon: TrendingDown,
    accent: "bg-pink-50 text-pink-600",
    title: "Прогноз оттока клиентов",
    description:
      "Модель оценивает риск ухода клиента на основе истории обращений и тональности. Список «обратите внимание» — в дашборде.",
    preview: <ChurnPreview at_risk={3} watch={12} healthy={84} />,
  },
  {
    icon: Lightbulb,
    accent: "bg-orange-50 text-orange-600",
    title: "Еженедельные инсайты",
    description:
      "Раз в неделю система сама собирает наблюдения: что выросло, что упало, на что обратить внимание руководителю.",
    preview: (
      <ul className="space-y-1 text-xs text-slate-600">
        <li className="flex items-start gap-1">
          <TrendingUp className="mt-0.5 h-3 w-3 text-emerald-600" />
          <span>Скорость ответа улучшилась на 18%</span>
        </li>
        <li className="flex items-start gap-1">
          <TrendingDown className="mt-0.5 h-3 w-3 text-rose-600" />
          <span>Негатив по теме «возврат» вырос на 32%</span>
        </li>
        <li className="flex items-start gap-1">
          <AlertCircle className="mt-0.5 h-3 w-3 text-amber-600" />
          <span>Иванов перегружен: +40% нагрузки vs среднего</span>
        </li>
      </ul>
    ),
  },
];

function FeatureCard({ icon: Icon, title, description, preview, accent }: Feature) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-white p-5">
      <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-500">
        <Lock className="h-3 w-3" /> скоро
      </span>
      <div className="flex items-start gap-3">
        <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${accent}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="font-medium text-slate-800">{title}</div>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            {description}
          </p>
        </div>
      </div>
      <div className="mt-4 rounded-md border border-slate-100 bg-slate-50 p-3">
        {preview}
      </div>
    </div>
  );
}

function AnomalyPreview({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
      <div>
        <div className="font-medium text-slate-700">Обнаружена аномалия</div>
        <div className="text-slate-500">{text}</div>
      </div>
    </div>
  );
}

function QualityScorePreview({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid h-14 w-14 place-items-center rounded-full border-4 border-emerald-200">
        <span className="text-sm font-semibold text-emerald-700">{score}</span>
      </div>
      <ul className="space-y-0.5 text-xs text-slate-600">
        <li>✓ Эмпатия</li>
        <li>✓ Полнота ответа</li>
        <li>· Время ответа</li>
      </ul>
    </div>
  );
}

function ChurnPreview({
  at_risk,
  watch,
  healthy,
}: {
  at_risk: number;
  watch: number;
  healthy: number;
}) {
  return (
    <div className="flex items-stretch gap-2 text-xs">
      <Stat color="bg-rose-50 text-rose-700" label="в зоне риска" value={at_risk} />
      <Stat color="bg-amber-50 text-amber-700" label="наблюдать" value={watch} />
      <Stat color="bg-emerald-50 text-emerald-700" label="лояльные" value={healthy} />
    </div>
  );
}

function Stat({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <div className={`flex-1 rounded-md px-2 py-1.5 ${color}`}>
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wider opacity-70">
        {label}
      </div>
    </div>
  );
}
