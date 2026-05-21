import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Inbox,
  Loader2,
  Plug,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { EntityChips } from "../components/EntityChips";
import { SentimentBadge } from "../components/SentimentBadge";
import { cn } from "../lib/cn";
import {
  api,
  type ConversationListItem,
  type ConversationChannel,
  type Message,
  type SenderType,
  type Sentiment,
} from "../lib/api";

const channelLabel: Record<ConversationChannel, string> = {
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  vk: "ВКонтакте",
  instagram: "Instagram",
  facebook: "Facebook",
  livechat: "Виджет сайта",
  email: "Email",
  other: "Другое",
};

const channelBadge: Record<ConversationChannel, string> = {
  whatsapp: "bg-emerald-100 text-emerald-700",
  telegram: "bg-sky-100 text-sky-700",
  vk: "bg-blue-100 text-blue-700",
  instagram: "bg-pink-100 text-pink-700",
  facebook: "bg-indigo-100 text-indigo-700",
  livechat: "bg-violet-100 text-violet-700",
  email: "bg-amber-100 text-amber-700",
  other: "bg-slate-100 text-slate-600",
};

function sentimentChipLabel(s: Sentiment): string {
  if (s === "positive") return "Позитив";
  if (s === "negative") return "Негатив";
  return "Нейтрально";
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

export function InboxPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(
    () => ({
      integration_id: searchParams.get("integration_id") ?? undefined,
      channel:
        (searchParams.get("channel") as ConversationChannel | null) ??
        undefined,
      status:
        (searchParams.get("status") as "open" | "closed" | null) ?? undefined,
      operator_id: searchParams.get("operator_id") ?? undefined,
      line_id: searchParams.get("line_id") ?? undefined,
      sentiment:
        (searchParams.get("sentiment") as Sentiment | null) ?? undefined,
    }),
    [searchParams],
  );
  const initialConvParam = searchParams.get("conv");

  const integrationsQ = useQuery({
    queryKey: ["integrations"],
    queryFn: api.listIntegrations,
  });
  const portalUsersQ = useQuery({
    queryKey: ["portal-users", filters.integration_id ?? null],
    queryFn: () =>
      api.getPortalUsers({ integration_id: filters.integration_id }),
    enabled: integrationsQ.isSuccess && !!filters.operator_id,
  });

  const conversationsQ = useQuery({
    queryKey: ["conversations", filters],
    queryFn: () => api.listConversations({ ...filters, limit: 100 }),
    enabled: integrationsQ.isSuccess,
    refetchInterval: 15000,
  });

  const [selectedId, setSelectedId] = useState<string | null>(
    initialConvParam,
  );
  const conversations = conversationsQ.data ?? [];

  // Если в URL пришёл ?conv=... а его нет в выдаче (например, не подходит
  // под текущие фильтры), всё равно подсветим первый из выдачи.
  useEffect(() => {
    if (!initialConvParam) return;
    if (conversations.some((c) => c.id === initialConvParam)) {
      setSelectedId(initialConvParam);
    }
  }, [initialConvParam, conversations]);

  const selected = useMemo(
    () =>
      conversations.find((c) => c.id === selectedId) ??
      conversations[0] ??
      null,
    [conversations, selectedId],
  );

  function clearFilter(key: keyof typeof filters) {
    const params = new URLSearchParams(searchParams);
    params.delete(key);
    setSearchParams(params, { replace: true });
  }
  function clearAllFilters() {
    const params = new URLSearchParams(searchParams);
    [
      "integration_id",
      "channel",
      "status",
      "operator_id",
      "line_id",
      "sentiment",
      "conv",
    ].forEach((k) => params.delete(k));
    setSearchParams(params, { replace: true });
  }
  const activeFilters = Object.entries(filters).filter(([, v]) => v);

  const operatorName = useMemo(() => {
    if (!filters.operator_id) return null;
    const u = (portalUsersQ.data ?? []).find(
      (x) => x.external_id === filters.operator_id,
    );
    return u?.full_name || `#${filters.operator_id}`;
  }, [filters.operator_id, portalUsersQ.data]);

  const integrationLabel = useMemo(() => {
    if (!filters.integration_id) return null;
    const i = (integrationsQ.data ?? []).find(
      (x) => x.id === filters.integration_id,
    );
    return i?.label || i?.domain || `#${filters.integration_id}`;
  }, [filters.integration_id, integrationsQ.data]);

  if (integrationsQ.isLoading) {
    return (
      <>
        <PageHeader title="Диалоги" />
        <Center>
          <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
        </Center>
      </>
    );
  }

  if (integrationsQ.isSuccess && (integrationsQ.data ?? []).length === 0) {
    return (
      <>
        <PageHeader title="Диалоги" />
        <EmptyState
          icon={<Plug className="h-6 w-6 text-brand-600" />}
          title="Нет подключённых источников"
          description="Подключите Bitrix24 — здесь появятся диалоги из открытых линий."
          action={
            <Link to="/integrations/bitrix24/new">
              <Button>Подключить Bitrix24</Button>
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Диалоги"
        description="Объединённая лента диалогов из всех подключённых каналов"
      />
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-amber-50/50 px-6 py-2 text-sm">
          <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
            Фильтры:
          </span>
          {filters.integration_id && (
            <FilterChip
              label="Портал"
              value={integrationLabel ?? filters.integration_id}
              onRemove={() => clearFilter("integration_id")}
            />
          )}
          {filters.channel && (
            <FilterChip
              label="Канал"
              value={channelLabel[filters.channel] ?? filters.channel}
              onRemove={() => clearFilter("channel")}
            />
          )}
          {filters.status && (
            <FilterChip
              label="Статус"
              value={filters.status === "open" ? "Открыт" : "Закрыт"}
              onRemove={() => clearFilter("status")}
            />
          )}
          {filters.operator_id && (
            <FilterChip
              label="Оператор"
              value={operatorName ?? filters.operator_id}
              onRemove={() => clearFilter("operator_id")}
            />
          )}
          {filters.line_id && (
            <FilterChip
              label="Линия"
              value={`#${filters.line_id}`}
              onRemove={() => clearFilter("line_id")}
            />
          )}
          {filters.sentiment && (
            <FilterChip
              label="Тональность"
              value={sentimentChipLabel(filters.sentiment)}
              onRemove={() => clearFilter("sentiment")}
            />
          )}
          <button
            type="button"
            onClick={clearAllFilters}
            className="ml-auto text-xs text-slate-500 hover:text-slate-800 hover:underline"
          >
            сбросить все
          </button>
        </div>
      )}
      {!filters.sentiment && (
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-6 py-2 text-xs">
          <span className="text-slate-400">Быстрый фильтр:</span>
          <button
            type="button"
            onClick={() => {
              const p = new URLSearchParams(searchParams);
              p.set("sentiment", "negative");
              setSearchParams(p, { replace: true });
            }}
            className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5 text-rose-700 transition hover:border-rose-300 hover:bg-rose-100"
          >
            <span className="inline-block h-2 w-2 rounded-full bg-rose-500" />
            Только негатив
          </button>
        </div>
      )}
      <div className="grid h-[calc(100%-77px)] grid-cols-[360px_1fr]">
        <div className="overflow-y-auto border-r border-slate-200 bg-white">
          {conversationsQ.isLoading && (
            <div className="flex items-center gap-2 p-5 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Загрузка диалогов…
            </div>
          )}
          {conversationsQ.isError && (
            <ErrorRow message={(conversationsQ.error as Error).message} />
          )}
          {conversationsQ.isSuccess && conversations.length === 0 && (
            <div className="p-8 text-center text-sm text-slate-500">
              <Inbox className="mx-auto mb-3 h-8 w-8 text-slate-300" />
              Пока нет ни одного сообщения.
              <br />
              Они появятся, как только в подключённый портал придёт первое
              событие.
            </div>
          )}
          {conversations.map((c) => (
            <ConversationRow
              key={c.id}
              conv={c}
              active={selected?.id === c.id}
              onClick={() => setSelectedId(c.id)}
            />
          ))}
        </div>

        <div className="flex flex-col overflow-hidden bg-slate-50">
          {selected ? (
            <ConversationView conv={selected} />
          ) : (
            <Center>
              <span className="text-sm text-slate-400">
                Выберите диалог слева
              </span>
            </Center>
          )}
        </div>
      </div>
    </>
  );
}

function ConversationRow({
  conv,
  active,
  onClick,
}: {
  conv: ConversationListItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full border-b border-slate-100 px-5 py-4 text-left transition hover:bg-slate-50",
        active && "bg-brand-50 hover:bg-brand-50",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <SentimentBadge
            score={conv.sentiment_score}
            messageCount={conv.message_count}
          />
          <div className="truncate font-medium text-sm">
            {conv.contact_name || conv.contact_external_id || "Без имени"}
          </div>
        </div>
        <div className="shrink-0 text-xs text-slate-400">
          {formatTime(conv.last_message_at ?? conv.created_at)}
        </div>
      </div>
      <div className="mt-1 truncate text-sm text-slate-500">
        {conv.last_message_preview || (
          <span className="italic text-slate-400">нет сообщений</span>
        )}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-xs",
            channelBadge[conv.channel],
          )}
        >
          {channelLabel[conv.channel]}
        </span>
        {conv.status === "closed" && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
            закрыт
          </span>
        )}
        {conv.message_count > 0 && (
          <span className="ml-auto text-xs text-slate-400">
            {conv.message_count}
          </span>
        )}
      </div>
      {conv.tags && conv.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {conv.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="rounded bg-brand-50 px-1.5 py-0.5 text-[11px] text-brand-700"
              title={`Тема: ${tag.replace(/_/g, " ")}`}
            >
              #{tag.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

function ConversationView({ conv }: { conv: ConversationListItem }) {
  const qc = useQueryClient();
  const messagesQ = useQuery({
    queryKey: ["messages", conv.id],
    queryFn: () => api.listMessages(conv.id, { limit: 500 }),
    refetchInterval: 10000,
  });
  // Полная запись диалога — со свежим summary. Список диалогов не обновляется
  // моментально после генерации, поэтому за summary ходим отдельно.
  const conversationQ = useQuery({
    queryKey: ["conversation", conv.id],
    queryFn: () => api.getConversation(conv.id),
    refetchInterval: 15000,
  });
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });

  const detailed = conversationQ.data ?? conv;
  const summary = detailed.summary;
  const summaryCount = detailed.summary_messages_count;
  const isStale =
    summary !== null &&
    summary !== undefined &&
    summaryCount !== null &&
    summaryCount !== undefined &&
    conv.message_count > summaryCount;

  // Поллим conversation после клика «Сводка», пока summary_at не изменится.
  // Без этого кнопка отпускалась после 202, и пользователь не понимал, готово
  // ли. Таймаут 90с — на случай зависшей smart-LLM/воркера.
  const [summarizing, setSummarizing] = useState(false);
  const [summarizeError, setSummarizeError] = useState<string | null>(null);
  const summaryBaselineRef = useRef<string | null>(null);

  useEffect(() => {
    if (!summarizing) return;
    let cancelled = false;
    const startedAt = Date.now();
    const tick = async () => {
      try {
        const fresh = await api.getConversation(conv.id);
        qc.setQueryData(["conversation", conv.id], fresh);
        if (fresh.summary_at && fresh.summary_at !== summaryBaselineRef.current) {
          if (!cancelled) setSummarizing(false);
          qc.invalidateQueries({ queryKey: ["conversations"] });
          return;
        }
      } catch {
        // Сеть могла моргнуть — продолжаем
      }
      if (Date.now() - startedAt > 90_000) {
        if (!cancelled) setSummarizing(false);
        return;
      }
      if (cancelled) return;
      setTimeout(tick, 3000);
    };
    setTimeout(tick, 3000);
    return () => {
      cancelled = true;
    };
  }, [summarizing, conv.id, qc]);

  const handleSummarize = async () => {
    setSummarizeError(null);
    summaryBaselineRef.current = detailed.summary_at ?? null;
    setSummarizing(true);
    try {
      await api.summarizeConversation(conv.id);
    } catch (err) {
      setSummarizing(false);
      setSummarizeError(
        (err as Error).message || "Не удалось запустить генерацию сводки",
      );
    }
  };

  const smartReady = llmStatusQ.data?.smart_available ?? false;
  const summarizeDisabled =
    summarizing || !smartReady || conv.message_count === 0;
  const summarizeTitle = !smartReady
    ? "Smart LLM-провайдер не настроен (LLM_SMART_*)"
    : conv.message_count === 0
      ? "В диалоге нет сообщений"
      : undefined;

  return (
    <>
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium">
              {conv.contact_name || conv.contact_external_id || "Без имени"}
            </div>
            <div className="text-xs text-slate-500">
              Канал: {channelLabel[conv.channel]}
              {conv.external_id && ` · #${conv.external_id}`}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Button
              onClick={handleSummarize}
              disabled={summarizeDisabled}
              title={summarizeTitle}
              variant="secondary"
            >
              {summarizing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Генерирую…
                </>
              ) : summary ? (
                <>
                  <RefreshCw className="h-4 w-4" /> Обновить сводку
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" /> Сводка
                </>
              )}
            </Button>
            {summarizeError && (
              <div
                role="alert"
                className="max-w-xs rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-700"
              >
                {summarizeError}
              </div>
            )}
          </div>
        </div>
      </div>
      {summary && (
        <SummaryBlock
          summary={summary}
          model={detailed.summary_model ?? null}
          summaryAt={detailed.summary_at ?? null}
          isStale={isStale}
        />
      )}
      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        {messagesQ.isLoading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Загрузка сообщений…
          </div>
        )}
        {messagesQ.isError && (
          <ErrorRow message={(messagesQ.error as Error).message} />
        )}
        {messagesQ.data?.length === 0 && (
          <div className="text-center text-sm text-slate-400">
            Сообщений ещё нет
          </div>
        )}
        {messagesQ.data?.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>
      <div className="border-t border-slate-200 bg-white p-4">
        <input
          className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
          placeholder="Отправка сообщений появится в следующей фазе"
          disabled
        />
      </div>
    </>
  );
}

function SummaryBlock({
  summary,
  model,
  summaryAt,
  isStale,
}: {
  summary: string;
  model: string | null;
  summaryAt: string | null;
  isStale: boolean;
}) {
  const formattedAt = summaryAt
    ? new Date(summaryAt).toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;
  return (
    <div className="border-b border-slate-200 bg-gradient-to-br from-brand-50/60 via-white to-violet-50/40 px-6 py-3">
      <div className="flex items-start gap-3">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-slate-700">AI-сводка</span>
            {isStale && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-800">
                устарела — есть новые сообщения
              </span>
            )}
            {formattedAt && (
              <span className="text-slate-400">
                {formattedAt}
                {model && ` · ${model}`}
              </span>
            )}
          </div>
          <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
            {summary}
          </div>
        </div>
      </div>
    </div>
  );
}

const senderSide: Record<SenderType, "me" | "them" | "system"> = {
  agent: "me",
  bot: "me",
  client: "them",
  system: "system",
};

function MessageBubble({ message }: { message: Message }) {
  const side = senderSide[message.sender_type];
  if (side === "system") {
    return (
      <div className="text-center text-xs text-slate-400">
        {message.text}
      </div>
    );
  }
  return (
    <div className={cn("flex", side === "me" ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[70%] rounded-lg px-3 py-2 text-sm shadow-sm",
          side === "me"
            ? "bg-brand-600 text-white"
            : "bg-white text-slate-800",
        )}
      >
        <div className="whitespace-pre-wrap break-words">{message.text}</div>
        <EntityChips entities={message.entities} />

        <div
          className={cn(
            "mt-1 text-[10px]",
            side === "me" ? "text-brand-100" : "text-slate-400",
          )}
        >
          {new Date(message.sent_at).toLocaleString("ru-RU", {
            hour: "2-digit",
            minute: "2-digit",
            day: "2-digit",
            month: "2-digit",
          })}
        </div>
      </div>
    </div>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-[calc(100%-77px)] items-center justify-center">
      {children}
    </div>
  );
}

function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex h-[calc(100%-77px)] items-center justify-center p-8">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-brand-50">
          {icon}
        </div>
        <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
        <p className="mt-2 text-sm text-slate-500">{description}</p>
        {action && <div className="mt-5">{action}</div>}
      </div>
    </div>
  );
}

function ErrorRow({ message }: { message: string }) {
  return (
    <div className="m-4 flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span>Ошибка загрузки: {message}</span>
    </div>
  );
}

function FilterChip({
  label,
  value,
  onRemove,
}: {
  label: string;
  value: string;
  onRemove: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs text-slate-700">
      <span className="text-slate-400">{label}:</span>
      <span className="font-medium">{value}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Снять фильтр ${label}`}
        className="text-slate-400 transition hover:text-rose-600"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}
