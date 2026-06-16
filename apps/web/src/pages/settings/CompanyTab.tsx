import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Skeleton } from "../../components/ui/Skeleton";
import { toast } from "../../components/ui/Toast";
import { api, type CompanySettings } from "../../lib/api";
import { useAuth } from "../../lib/auth";

// Распространённые часовые пояса РФ/СНГ. Полный список tz избыточен для UI.
const TIMEZONES = [
  "Europe/Kaliningrad",
  "Europe/Moscow",
  "Europe/Samara",
  "Asia/Yekaterinburg",
  "Asia/Omsk",
  "Asia/Novosibirsk",
  "Asia/Krasnoyarsk",
  "Asia/Irkutsk",
  "Asia/Yakutsk",
  "Asia/Vladivostok",
  "Asia/Kamchatka",
  "Europe/Kyiv",
  "Asia/Almaty",
  "Asia/Tashkent",
];

export function CompanyTab() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const qc = useQueryClient();

  const companyQ = useQuery({
    queryKey: ["company-settings"],
    queryFn: api.getCompanySettings,
  });
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });

  const [form, setForm] = useState<CompanySettings | null>(null);
  useEffect(() => {
    if (companyQ.data) setForm(companyQ.data);
  }, [companyQ.data]);

  const saveMut = useMutation({
    mutationFn: (body: Partial<CompanySettings>) =>
      api.updateCompanySettings(body),
    onSuccess: (data) => {
      qc.setQueryData(["company-settings"], data);
      toast.success("Настройки компании сохранены");
    },
    onError: () => toast.error("Не удалось сохранить настройки"),
  });

  const dirty =
    form &&
    companyQ.data &&
    (form.name !== companyQ.data.name ||
      form.timezone !== companyQ.data.timezone ||
      form.locale !== companyQ.data.locale);

  return (
    <div className="max-w-2xl space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 text-sm font-medium text-slate-800">
          Организация
        </div>
        {companyQ.isLoading || !form ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (form) saveMut.mutate(form);
            }}
          >
            <Input
              label="Название организации"
              value={form.name}
              disabled={!isAdmin}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-slate-700">
                Часовой пояс
              </label>
              <select
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-500 disabled:opacity-60"
                value={form.timezone}
                disabled={!isAdmin}
                onChange={(e) => setForm({ ...form, timezone: e.target.value })}
              >
                {TIMEZONES.includes(form.timezone) ? null : (
                  <option value={form.timezone}>{form.timezone}</option>
                )}
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-slate-700">
                Язык интерфейса
              </label>
              <select
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-500 disabled:opacity-60"
                value={form.locale}
                disabled={!isAdmin}
                onChange={(e) => setForm({ ...form, locale: e.target.value })}
              >
                <option value="ru">Русский</option>
                <option value="en">English</option>
              </select>
            </div>
            {isAdmin ? (
              <div className="flex items-center gap-3">
                <Button type="submit" disabled={!dirty || saveMut.isPending}>
                  {saveMut.isPending ? "Сохранение…" : "Сохранить"}
                </Button>
                {dirty && (
                  <span className="text-xs text-slate-400">
                    есть несохранённые изменения
                  </span>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-400">
                Изменять настройки организации может только администратор.
              </p>
            )}
          </form>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-3 text-sm font-medium text-slate-800">
          AI-провайдеры
        </div>
        {llmStatusQ.isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-5 w-2/3" />
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
                  Sentiment-анализ и теги работают через Fast LLM. Задайте в
                  окружении backend <code className="font-mono">LLM_FAST_PROVIDER</code> и{" "}
                  <code className="font-mono">LLM_FAST_API_KEY</code>.
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ProviderRow({ name, available }: { name: string; available: boolean }) {
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
