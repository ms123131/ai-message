import { Plug, CheckCircle2 } from "lucide-react";
import { PageHeader } from "../components/PageHeader";

const integrations = [
  {
    id: "bitrix24",
    name: "Bitrix24",
    description: "CRM + Open Channels (WhatsApp, Telegram, ВК, виджет сайта)",
    status: "available" as const,
    priority: true,
  },
  {
    id: "email",
    name: "Email (IMAP)",
    description: "Подключение почтовых ящиков по IMAP/SMTP",
    status: "soon" as const,
  },
  {
    id: "telegram",
    name: "Telegram Bot",
    description: "Прямой Bot API (для бизнес-аккаунтов и каналов поддержки)",
    status: "soon" as const,
  },
  {
    id: "whatsapp",
    name: "WhatsApp Business",
    description: "WhatsApp Cloud API (Meta)",
    status: "soon" as const,
  },
];

export function IntegrationsPage() {
  return (
    <>
      <PageHeader
        title="Интеграции"
        description="Подключите источники коммуникаций для анализа"
      />
      <div className="p-8">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {integrations.map((i) => (
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
                    <div className="text-sm text-slate-500">{i.description}</div>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                {i.status === "available" ? (
                  <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
                    <CheckCircle2 className="h-4 w-4" /> готово к подключению
                  </span>
                ) : (
                  <span className="text-xs text-slate-400">скоро</span>
                )}
                <button
                  disabled={i.status !== "available"}
                  className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
                >
                  Подключить
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
