import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  Inbox,
  Loader2,
  Maximize2,
  RefreshCw,
  Sparkles,
  Users,
} from "lucide-react";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { SkeletonText } from "../ui/Skeleton";
import { EntityChips } from "../EntityChips";
import { cn } from "../../lib/cn";
import {
  api,
  type ConversationListItem,
  type Message,
  type SenderType,
} from "../../lib/api";
import { channelLabel } from "./channel";

export function ConversationView({
  conversationId,
  initial,
  showExpand = true,
}: {
  conversationId: string;
  /** Запись из списка диалогов — для мгновенного рендера без мигания. */
  initial?: ConversationListItem;
  /** Показывать ли кнопку «открыть на весь экран» (скрываем на самой странице). */
  showExpand?: boolean;
}) {
  const qc = useQueryClient();
  const messagesQ = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => api.listMessages(conversationId, { limit: 500 }),
    refetchInterval: 10000,
  });
  // Полная запись диалога — со свежим summary. Грузим по id, чтобы страница
  // работала по deep-link, без зависимости от списка диалогов.
  const conversationQ = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => api.getConversation(conversationId),
    refetchInterval: 15000,
    initialData: initial,
  });
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });

  const detailed = conversationQ.data ?? initial ?? null;
  // message_count нет в Conversation (только в элементе списка) — берём
  // длину загруженных сообщений, с откатом на запись из списка.
  const messageCount = messagesQ.data?.length ?? initial?.message_count ?? 0;
  const summary = detailed?.summary;
  const summaryCount = detailed?.summary_messages_count;
  const isStale =
    summary !== null &&
    summary !== undefined &&
    summaryCount !== null &&
    summaryCount !== undefined &&
    messageCount > summaryCount;

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
        const fresh = await api.getConversation(conversationId);
        qc.setQueryData(["conversation", conversationId], fresh);
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
  }, [summarizing, conversationId, qc]);

  const handleSummarize = async () => {
    setSummarizeError(null);
    summaryBaselineRef.current = detailed?.summary_at ?? null;
    setSummarizing(true);
    try {
      await api.summarizeConversation(conversationId);
    } catch (err) {
      setSummarizing(false);
      setSummarizeError(
        (err as Error).message || "Не удалось запустить генерацию сводки",
      );
    }
  };

  const smartReady = llmStatusQ.data?.smart_available ?? false;
  const summarizeDisabled = summarizing || !smartReady || messageCount === 0;
  const summarizeTitle = !smartReady
    ? "Smart LLM-провайдер не настроен (LLM_SMART_*)"
    : messageCount === 0
      ? "В диалоге нет сообщений"
      : undefined;

  if (!detailed) {
    if (conversationQ.isError) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
          <AlertCircle className="h-6 w-6 text-rose-400" />
          <div className="text-sm text-slate-600">
            {(conversationQ.error as Error)?.message ||
              "Не удалось загрузить диалог"}
          </div>
        </div>
      );
    }
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium">
              {detailed.contact_name ||
                detailed.contact_external_id ||
                "Без имени"}
            </div>
            <div className="text-xs text-slate-500">
              Канал: {channelLabel[detailed.channel]}
              {detailed.external_id && ` · #${detailed.external_id}`}
            </div>
          </div>
          <div className="flex items-start gap-2">
            {showExpand && (
              <Link
                to={`/inbox/${conversationId}`}
                title="Открыть на весь экран"
                className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-200 px-2.5 text-sm text-slate-600 transition hover:bg-slate-50"
              >
                <Maximize2 className="h-4 w-4" />
              </Link>
            )}
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
      </div>
      {summary && (
        <SummaryBlock
          summary={summary}
          model={detailed.summary_model ?? null}
          summaryAt={detailed.summary_at ?? null}
          isStale={isStale}
        />
      )}
      <SimilarBlock conversationId={conversationId} />

      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        {messagesQ.isLoading && (
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  "max-w-[70%] rounded-2xl bg-white p-3 shadow-sm",
                  i % 2 === 1 ? "ml-auto" : "",
                )}
              >
                <SkeletonText lines={2} />
              </div>
            ))}
          </div>
        )}
        {messagesQ.data?.length === 0 && (
          <EmptyState
            icon={Inbox}
            title="Сообщений ещё нет"
            description="Они появятся, когда клиент напишет в эту линию."
            size="sm"
          />
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
    </div>
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

function SimilarBlock({ conversationId }: { conversationId: string }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["similar", conversationId],
    queryFn: () => api.listSimilarConversations(conversationId, 10),
    enabled: open,
    staleTime: 60_000,
    meta: { silent: true },
  });

  return (
    <div className="border-b border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-6 py-2 text-left text-xs font-medium text-slate-600 hover:bg-slate-50"
      >
        <span className="inline-flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5 text-slate-400" />
          Похожие диалоги
        </span>
        <span className="text-slate-400">{open ? "скрыть" : "показать"}</span>
      </button>
      {open && (
        <div className="px-6 pb-3">
          {q.isLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Ищу…
            </div>
          )}
          {q.isError && (
            <div className="text-xs text-rose-600">
              {(q.error as Error).message || "Не удалось получить список"}
            </div>
          )}
          {q.data && q.data.available === false && (
            <div className="text-xs text-slate-500">
              Семантический поиск недоступен (нужен Postgres с расширением
              pgvector — см. фаза 6.5).
            </div>
          )}
          {q.data && q.data.available && q.data.items.length === 0 && (
            <div className="text-xs text-slate-500">
              {q.data.reason === "no_embeddings"
                ? "Для этого диалога ещё не посчитаны эмбеддинги. Запустите анализ на странице интеграции."
                : "Похожих диалогов не нашлось."}
            </div>
          )}
          {q.data && q.data.items.length > 0 && (
            <ul className="space-y-1">
              {q.data.items.map((item) => {
                const sim = Math.max(0, Math.min(1, item.similarity));
                const pct = Math.round(sim * 100);
                const name =
                  item.contact_name || item.contact_external_id || "Без имени";
                return (
                  <li key={item.id}>
                    <Link
                      to={`/inbox/${item.id}`}
                      className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-brand-50"
                    >
                      <span className="min-w-0 truncate text-slate-700">
                        {name}
                      </span>
                      <span className="shrink-0 text-xs text-slate-500">
                        {pct}%
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
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
      <div className="text-center text-xs text-slate-400">{message.text}</div>
    );
  }
  return (
    <div className={cn("flex", side === "me" ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[70%] rounded-lg px-3 py-2 text-sm shadow-sm",
          side === "me" ? "bg-brand-600 text-white" : "bg-white text-slate-800",
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
