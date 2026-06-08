import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  Clock,
  KeyRound,
  Plug,
  QrCode,
  Send,
  Trash2,
  Webhook,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { ConfirmDialog } from "../components/ui/Dialog";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton } from "../components/ui/Skeleton";
import { toast } from "../components/ui/Toast";
import { api, type Integration } from "../lib/api";

type CatalogItem = {
  id: string;
  name: string;
  description: string;
  available: boolean;
  priority?: boolean;
  badge?: string;
  icon?: LucideIcon;
  route?: string;
};

const catalog: CatalogItem[] = [
  {
    id: "bitrix24",
    name: "Bitrix24",
    description: "CRM + Open Channels (WhatsApp, Telegram, ВК, виджет сайта)",
    available: true,
    priority: true,
    route: "/integrations/bitrix24/new",
  },
  {
    id: "telegram_user",
    name: "Telegram (личный аккаунт)",
    description: "Подключение через QR-код, как новое устройство",
    available: true,
    badge: "новое",
    icon: Send,
    route: "/integrations/telegram-user/new",
  },
  {
    id: "telegram_bot",
    name: "Telegram Bot",
    description: "Прямой Bot API по токену",
    available: false,
    icon: Send,
  },
  {
    id: "whatsapp_user",
    name: "WhatsApp (личный)",
    description: "Подключение через сканирование QR (multi-device)",
    available: false,
    icon: QrCode,
  },
  {
    id: "email",
    name: "Email (IMAP)",
    description: "Подключение почтовых ящиков по IMAP/SMTP",
    available: false,
  },
];

export function IntegrationsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["integrations"],
    queryFn: api.listIntegrations,
  });

  const del = useMutation({
    mutationFn: (id: string) => api.deleteIntegration(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
      toast.success("Подключение удалено");
      setPendingDelete(null);
    },
  });

  const [pendingDelete, setPendingDelete] = useState<Integration | null>(null);
  const connections = data ?? [];

  return (
    <>
      <PageHeader
        title="Интеграции"
        description="Источники коммуникаций для анализа"
      />
      <div className="space-y-8 p-8">
        {isLoading && (
          <section>
            <h2 className="mb-3 text-sm font-medium text-slate-500">
              Подключённые порталы
            </h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Skeleton className="h-28" />
              <Skeleton className="h-28" />
            </div>
          </section>
        )}

        {!isLoading && connections.length === 0 && (
          <EmptyState
            icon={Plug}
            title="Нет подключённых источников"
            description="Подключите Bitrix24, чтобы анализировать диалоги и CRM-активность"
            size="md"
          />
        )}

        {connections.length > 0 && (
          <section>
            <h2 className="mb-3 text-sm font-medium text-slate-500">
              Подключённые порталы
            </h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {connections.map((c) => (
                <ConnectionCard
                  key={c.id}
                  conn={c}
                  onDelete={() => setPendingDelete(c)}
                />
              ))}
            </div>
          </section>
        )}

        <ConfirmDialog
          open={pendingDelete !== null}
          onClose={() => setPendingDelete(null)}
          onConfirm={() => {
            if (pendingDelete) del.mutate(pendingDelete.id);
          }}
          title="Удалить подключение?"
          description={
            pendingDelete
              ? `Будут удалены токены и история «${pendingDelete.label ?? pendingDelete.domain ?? pendingDelete.id}». Действие нельзя отменить.`
              : undefined
          }
          confirmLabel="Удалить"
          destructive
          loading={del.isPending}
        />

        <section>
          <h2 className="mb-3 text-sm font-medium text-slate-500">
            Доступные источники
          </h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {catalog.map((i) => {
              const Icon = i.icon ?? Plug;
              return (
                <div
                  key={i.id}
                  className="rounded-lg border border-slate-200 bg-white p-5"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-600">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2 font-medium">
                          {i.name}
                          {i.priority && (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                              приоритет
                            </span>
                          )}
                          {i.badge && (
                            <span className="rounded bg-sky-100 px-1.5 py-0.5 text-xs text-sky-700">
                              {i.badge}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-slate-500">
                          {i.description}
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center justify-between">
                    {i.available ? (
                      <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
                        <CheckCircle2 className="h-4 w-4" /> готово к подключению
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">скоро</span>
                    )}
                    <Button
                      disabled={!i.available || !i.route}
                      onClick={() => i.route && navigate(i.route)}
                    >
                      Подключить
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </>
  );
}

function ConnectionCard({
  conn,
  onDelete,
}: {
  conn: Integration;
  onDelete: () => void;
}) {
  const ModeIcon = modeIcon(conn);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <ModeIcon className="h-4 w-4 text-slate-500" />
            <span className="font-medium">{conn.label}</span>
            <StatusBadge status={conn.status} />
          </div>
          <div className="mt-1 truncate text-sm text-slate-500">
            {conn.domain}
          </div>
          <div className="mt-2 text-xs text-slate-400">
            {modeLabel(conn)} · добавлен{" "}
            {new Date(conn.created_at).toLocaleString("ru-RU")}
          </div>
        </div>
        <button
          onClick={onDelete}
          aria-label="Удалить"
          className="rounded-md p-1.5 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function modeIcon(conn: Integration): LucideIcon {
  if (conn.kind === "telegram_user") return QrCode;
  if (conn.kind === "telegram_bot") return Send;
  if (conn.kind === "whatsapp_user") return QrCode;
  return conn.mode === "oauth" ? KeyRound : Webhook;
}

function modeLabel(conn: Integration): string {
  switch (conn.mode) {
    case "oauth":
      return "OAuth-приложение";
    case "webhook":
      return "Входящий webhook";
    case "bot_token":
      return "Bot API (токен)";
    case "qr_link":
      return "QR-логин";
    case "mtproto_session":
      return "MTProto-сессия";
    case "wazzup_token":
      return "Wazzup API";
    default:
      return conn.mode;
  }
}

function StatusBadge({ status }: { status: Integration["status"] }) {
  if (status === "connected")
    return (
      <span className="inline-flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
        <CheckCircle2 className="h-3 w-3" /> подключено
      </span>
    );
  if (status === "pending")
    return (
      <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
        <Clock className="h-3 w-3" /> ожидает обмена
      </span>
    );
  return (
    <span className="rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-700">
      ошибка
    </span>
  );
}
