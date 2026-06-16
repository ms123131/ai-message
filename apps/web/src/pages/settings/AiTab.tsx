import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { toast } from "../../components/ui/Toast";
import { api } from "../../lib/api";

const PLACEHOLDER = `Например:
— Чем занимается компания, что продаёте/обслуживаете.
— Кто ваши клиенты.
— Tone of voice: как принято общаться (на «вы», дружелюбно и т.п.).
— Политики: сроки ответа, что можно и нельзя обещать, как вести себя в конфликте.`;

export function AiTab() {
  const qc = useQueryClient();

  const profileQ = useQuery({
    queryKey: ["ai-business-profile"],
    queryFn: api.getBusinessProfile,
  });
  const llmStatusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: api.getLLMStatus,
    staleTime: 60_000,
  });

  const [value, setValue] = useState("");
  useEffect(() => {
    if (profileQ.data) setValue(profileQ.data.business_profile ?? "");
  }, [profileQ.data]);

  const saveMut = useMutation({
    mutationFn: () => api.saveBusinessProfile(value.trim() || null),
    onSuccess: (data) => {
      qc.setQueryData(["ai-business-profile"], data);
      toast.success("Профиль бизнеса сохранён");
    },
    onError: () => toast.error("Не удалось сохранить профиль"),
  });

  const dirty =
    profileQ.data && value.trim() !== (profileQ.data.business_profile ?? "").trim();

  return (
    <div className="max-w-2xl space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-1 text-sm font-medium text-slate-800">
          Профиль бизнеса для AI-ассистента
        </div>
        <p className="mb-4 text-xs text-slate-400">
          Ассистент использует это описание как контекст: чтобы понимать
          специфику вашего бизнеса и подсказывать, как корректно вести себя с
          клиентами. Чем точнее — тем полезнее ответы.
        </p>
        {profileQ.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              saveMut.mutate();
            }}
          >
            <textarea
              className="h-48 w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-500"
              placeholder={PLACEHOLDER}
              value={value}
              maxLength={8000}
              onChange={(e) => setValue(e.target.value)}
            />
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
          </form>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-3 text-sm font-medium text-slate-800">
          Smart LLM (движок ассистента)
        </div>
        {llmStatusQ.isLoading && <Skeleton className="h-5 w-2/3" />}
        {llmStatusQ.isSuccess && (
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-700">Smart LLM</span>
              {llmStatusQ.data.smart_available ? (
                <span className="inline-flex items-center gap-1 text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" /> подключён
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-slate-400">
                  <AlertCircle className="h-4 w-4" /> не настроен
                </span>
              )}
            </div>
            {!llmStatusQ.data.smart_available && (
              <div className="mt-2 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  AI-ассистент работает на Smart LLM. Задайте в окружении
                  backend <code className="font-mono">LLM_SMART_PROVIDER</code>,{" "}
                  <code className="font-mono">LLM_SMART_MODEL</code> и{" "}
                  <code className="font-mono">LLM_SMART_API_KEY</code>.
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
