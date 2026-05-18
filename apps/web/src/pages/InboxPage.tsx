import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, Inbox, Loader2, Plug } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { cn } from "../lib/cn";
import {
  api,
  type ConversationListItem,
  type ConversationChannel,
  type Message,
  type SenderType,
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
  const integrationsQ = useQuery({
    queryKey: ["integrations"],
    queryFn: api.listIntegrations,
  });

  const conversationsQ = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.listConversations({ limit: 100 }),
    enabled: integrationsQ.isSuccess,
    refetchInterval: 15000,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const conversations = conversationsQ.data ?? [];
  const selected = useMemo(
    () =>
      conversations.find((c) => c.id === selectedId) ??
      conversations[0] ??
      null,
    [conversations, selectedId],
  );

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
        <div className="truncate font-medium text-sm">
          {conv.contact_name || conv.contact_external_id || "Без имени"}
        </div>
        <div className="text-xs text-slate-400">
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
    </button>
  );
}

function ConversationView({ conv }: { conv: ConversationListItem }) {
  const messagesQ = useQuery({
    queryKey: ["messages", conv.id],
    queryFn: () => api.listMessages(conv.id, { limit: 500 }),
    refetchInterval: 10000,
  });

  return (
    <>
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="font-medium">
          {conv.contact_name || conv.contact_external_id || "Без имени"}
        </div>
        <div className="text-xs text-slate-500">
          Канал: {channelLabel[conv.channel]}
          {conv.external_id && ` · #${conv.external_id}`}
        </div>
      </div>
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
