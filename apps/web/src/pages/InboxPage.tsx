import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Inbox, Loader2, Plug, X } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton } from "../components/ui/Skeleton";
import { SentimentBadge } from "../components/SentimentBadge";
import { SearchBar } from "../components/inbox/SearchBar";
import { TagsFilter, tagLabel } from "../components/inbox/TagsFilter";
import { ConversationView } from "../components/inbox/ConversationView";
import { channelLabel, channelBadge } from "../components/inbox/channel";
import { focusInput, useInboxShortcuts } from "../lib/keyboard";
import { cn } from "../lib/cn";
import {
  api,
  type ConversationListItem,
  type ConversationChannel,
  type Sentiment,
} from "../lib/api";

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
      tags: searchParams.getAll("tags"),
      tag_mode:
        (searchParams.get("tag_mode") as "any" | "all" | null) ?? "any",
      q: searchParams.get("q") ?? "",
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
    queryFn: () =>
      api.listConversations({
        ...filters,
        // FastAPI требует min_length=2 на q — короче не отправляем.
        q: filters.q.length >= 2 ? filters.q : undefined,
        tags: filters.tags.length ? filters.tags : undefined,
        tag_mode: filters.tags.length ? filters.tag_mode : undefined,
        limit: 100,
      }),
    enabled: integrationsQ.isSuccess,
    refetchInterval: 15000,
  });

  const [selectedId, setSelectedId] = useState<string | null>(
    initialConvParam,
  );
  const conversations = conversationsQ.data?.items ?? [];

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
      "tags",
      "tag_mode",
      "q",
      "conv",
    ].forEach((k) => params.delete(k));
    setSearchParams(params, { replace: true });
  }
  function setQuery(q: string) {
    const params = new URLSearchParams(searchParams);
    if (q) params.set("q", q);
    else params.delete("q");
    setSearchParams(params, { replace: true });
  }
  function setTags(tags: string[]) {
    const params = new URLSearchParams(searchParams);
    params.delete("tags");
    tags.forEach((t) => params.append("tags", t));
    if (tags.length === 0) params.delete("tag_mode");
    setSearchParams(params, { replace: true });
  }
  function setTagMode(mode: "any" | "all") {
    const params = new URLSearchParams(searchParams);
    if (mode === "any") params.delete("tag_mode");
    else params.set("tag_mode", mode);
    setSearchParams(params, { replace: true });
  }
  function removeTag(tag: string) {
    setTags(filters.tags.filter((t) => t !== tag));
  }
  // activeFilters: считаем активными только то, что задано пользователем
  // (массив тегов — если не пустой, q — если не пустая строка).
  const activeFilters = useMemo(() => {
    const out: Array<[string, unknown]> = [];
    if (filters.integration_id) out.push(["integration_id", filters.integration_id]);
    if (filters.channel) out.push(["channel", filters.channel]);
    if (filters.status) out.push(["status", filters.status]);
    if (filters.operator_id) out.push(["operator_id", filters.operator_id]);
    if (filters.line_id) out.push(["line_id", filters.line_id]);
    if (filters.sentiment) out.push(["sentiment", filters.sentiment]);
    if (filters.tags.length) out.push(["tags", filters.tags]);
    if (filters.q) out.push(["q", filters.q]);
    return out;
  }, [filters]);

  // Поиск + клавиатурная навигация по списку диалогов.
  const searchInputRef = useRef<HTMLInputElement>(null);

  useInboxShortcuts(
    {
      onFocusSearch: focusInput(searchInputRef),
      onNext: () => {
        if (conversations.length === 0) return;
        const idx = conversations.findIndex((c) => c.id === selectedId);
        const next = conversations[Math.min(idx + 1, conversations.length - 1)];
        if (next) setSelectedId(next.id);
      },
      onPrev: () => {
        if (conversations.length === 0) return;
        const idx = conversations.findIndex((c) => c.id === selectedId);
        const prev = conversations[Math.max(idx - 1, 0)];
        if (prev) setSelectedId(prev.id);
      },
      onEscape: () => {
        // Если что-то в фокусе — пусть стандартный blur; иначе сбрасываем поиск.
        if (document.activeElement instanceof HTMLInputElement) return;
        if (filters.q) setQuery("");
      },
    },
    [conversations, filters.q],
  );

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
        <div className="flex h-[calc(100%-77px)] items-center justify-center">
          <EmptyState
            icon={Plug}
            title="Нет подключённых источников"
            description="Подключите Bitrix24 — здесь появятся диалоги из открытых линий."
            action={
              <Link to="/integrations/bitrix24/new">
                <Button>Подключить Bitrix24</Button>
              </Link>
            }
            size="lg"
          />
        </div>
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
          {filters.q && (
            <FilterChip
              label="Поиск"
              value={`«${filters.q}»`}
              onRemove={() => setQuery("")}
            />
          )}
          {filters.tags.map((tag) => (
            <FilterChip
              key={tag}
              label={filters.tag_mode === "all" ? "Тема (И)" : "Тема"}
              value={tagLabel(tag)}
              onRemove={() => removeTag(tag)}
            />
          ))}
          <button
            type="button"
            onClick={clearAllFilters}
            className="ml-auto text-xs text-slate-500 hover:text-slate-800 hover:underline"
          >
            сбросить все
          </button>
        </div>
      )}

      {/* Sidebar header: search + tags filter */}
      <div className="border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <SearchBar
              value={filters.q}
              onChange={setQuery}
              inputRef={searchInputRef}
            />
          </div>
          <TagsFilter
            selected={filters.tags}
            onChange={setTags}
            mode={filters.tag_mode}
            onModeChange={setTagMode}
            integrationId={filters.integration_id}
          />
        </div>
      </div>
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
            <div className="space-y-3 p-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex gap-3">
                  <Skeleton variant="circle" className="h-9 w-9 shrink-0" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-3.5 w-1/2" />
                    <Skeleton className="h-3 w-3/4" />
                  </div>
                </div>
              ))}
            </div>
          )}
          {conversationsQ.isSuccess && conversations.length === 0 && (
            <EmptyState
              icon={Inbox}
              title="Пока нет ни одного сообщения"
              description="Они появятся, как только в подключённый портал придёт первое событие."
              size="md"
            />
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
            <ConversationView
              key={selected.id}
              conversationId={selected.id}
              initial={selected}
            />
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

function Center({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-[calc(100%-77px)] items-center justify-center">
      {children}
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
