import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { api } from "../lib/api";

export function SettingsPage() {
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });

  return (
    <>
      <PageHeader title="Настройки" description="Профиль организации и параметры" />
      <div className="space-y-4 p-8">
        <div className="max-w-2xl rounded-lg border border-slate-200 bg-white p-6">
          <div className="space-y-4">
            <Field label="Название организации" value="Моя компания" />
            <Field label="Часовой пояс" value="Europe/Moscow" />
            <Field label="Язык интерфейса" value="Русский" />
          </div>
        </div>

        <div className="max-w-2xl rounded-lg border border-slate-200 bg-white p-6">
          <div className="mb-3 text-sm font-medium text-slate-800">
            AI-провайдеры
          </div>
          {llmStatusQ.isLoading && (
            <div className="text-xs text-slate-400">Проверяю доступность…</div>
          )}
          {llmStatusQ.isError && (
            <div className="text-xs text-rose-600">
              Не удалось получить статус: {(llmStatusQ.error as Error).message}
            </div>
          )}
          {llmStatusQ.isSuccess && (
            <div className="space-y-2">
              <ProviderRow
                name="Fast LLM (sentiment, теги)"
                available={llmStatusQ.data.fast_available}
              />
              <ProviderRow
                name="Smart LLM (резюме, инсайты)"
                available={llmStatusQ.data.smart_available}
              />
              {!llmStatusQ.data.fast_available && (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    Sentiment-анализ и теги работают через Fast LLM. Задайте
                    в окружении backend{" "}
                    <code className="font-mono">LLM_FAST_PROVIDER</code> и{" "}
                    <code className="font-mono">LLM_FAST_API_KEY</code> —
                    подробности в <code className="font-mono">apps/api/.env.example</code>.
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function ProviderRow({
  name,
  available,
}: {
  name: string;
  available: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-700">{name}</span>
      {available ? (
        <span className="inline-flex items-center gap-1 text-emerald-700">
          <CheckCircle2 className="h-4 w-4" /> подключён
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-slate-400">
          <AlertCircle className="h-4 w-4" /> не настроен
        </span>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-sm text-slate-800">{value}</div>
    </div>
  );
}
