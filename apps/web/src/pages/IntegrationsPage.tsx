import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  Clock,
  KeyRound,
  Plug,
  Trash2,
  Webhook,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import {
  deleteConnection,
  listConnections,
  type Bitrix24Connection,
} from "../lib/connections";

type CatalogItem = {
  id: string;
  name: string;
  description: string;
  available: boolean;
  priority?: boolean;
};

const catalog: CatalogItem[] = [
  {
    id: "bitrix24",
    name: "Bitrix24",
    description:
      "CRM + Open Channels (WhatsApp, Telegram, ВК, виджет сайта)",
    available: true,
    priority: true,
  },
  {
    id: "email",
    name: "Email (IMAP)",
    description: "Подключение почтовых ящиков по IMAP/SMTP",
    available: false,
  },
  {
    id: "telegram",
    name: "Telegram Bot",
    description: "Прямой Bot API",
    available: false,
  },
  {
    id: "whatsapp",
    name: "WhatsApp Business",
    description: "WhatsApp Cloud API (Meta)",
    available: false,
  },
];

export function IntegrationsPage() {
  const navigate = useNavigate();
  const [tick, setTick] = useState(0); // принудительный re-read из localStorage
  const connections = useMemo(() => listConnections(), [tick]);

  function handleDelete(id: string) {
    if (!confirm("Удалить это подключение?")) return;
    deleteConnection(id);
    setTick((t) => t + 1);
  }

  return (
    <>
      <PageHeader
        title="Интеграции"
        description="Источники коммуникаций для анализа"
      />
      <div className="space-y-8 p-8">
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
                  onDelete={() => handleDelete(c.id)}
                />
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="mb-3 text-sm font-medium text-slate-500">
            Доступные источники
          </h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {catalog.map((i) => (
              <div
                key={i.id}
                className="rounded-lg border border-slate-200 bg-white p-5"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="grid h-10 w-10 place-items-center rounded-md bg-brand-50 text-brand-600">
                      <Plug className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 font-medium">
                        {i.name}
                        {i.priority && (
                          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                            приоритет
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
                    disabled={!i.available}
                    onClick={() =>
                      i.id === "bitrix24" &&
                      navigate("/integrations/bitrix24/new")
                    }
                  >
                    Подключить
                  </Button>
                </div>
              </div>
            ))}
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
  conn: Bitrix24Connection;
  onDelete: () => void;
}) {
  const ModeIcon = conn.mode === "oauth" ? KeyRound : Webhook;
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
            {conn.mode === "oauth" ? "OAuth-приложение" : "Входящий webhook"} ·
            добавлен {new Date(conn.createdAt).toLocaleString("ru-RU")}
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

function StatusBadge({ status }: { status: Bitrix24Connection["status"] }) {
  if (status === "connected")
    return (
      <span className="inline-flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
        <CheckCircle2 className="h-3 w-3" /> подключено
      </span>
    );
  if (status === "pending")
    return (
      <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
        <Clock className="h-3 w-3" /> ожидает backend
      </span>
    );
  return (
    <span className="rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-700">
      ошибка
    </span>
  );
}
