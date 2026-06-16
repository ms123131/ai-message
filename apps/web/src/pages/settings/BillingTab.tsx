import { useQuery } from "@tanstack/react-query";
import { CreditCard, Sparkles } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { api, type BillingInfo } from "../../lib/api";

const PLAN_LABELS: Record<string, string> = {
  trial: "Триал",
  start: "Старт",
  pro: "Pro",
  enterprise: "Enterprise",
};

const USAGE_LABELS: Record<string, string> = {
  conversations: "Диалоги",
  messages: "Сообщения",
  integrations: "Подключения",
};

function fmt(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n);
}

function trialDaysLeft(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.ceil(ms / 86_400_000);
}

const UPGRADE_MAILTO =
  "mailto:info@gitpro.pro?subject=" +
  encodeURIComponent("Переход на платный тариф ai-message");

export function BillingTab() {
  const billingQ = useQuery({ queryKey: ["billing"], queryFn: api.getBilling });

  if (billingQ.isLoading) {
    return (
      <div className="max-w-2xl space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!billingQ.isSuccess) return null;

  const b: BillingInfo = billingQ.data;
  const planLabel = PLAN_LABELS[b.plan] ?? b.plan;
  const daysLeft = b.plan === "trial" ? trialDaysLeft(b.trial_ends_at) : null;

  return (
    <div className="max-w-2xl space-y-4">
      {/* Карточка тарифа */}
      <div className="relative overflow-hidden rounded-lg border border-brand-200 bg-gradient-to-br from-brand-50 via-white to-violet-50 p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-white shadow-sm">
              <CreditCard className="h-5 w-5 text-brand-600" />
            </div>
            <div>
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Текущий тариф
              </div>
              <div className="text-lg font-semibold text-slate-900">
                {planLabel}
              </div>
              {daysLeft !== null && (
                <div className="mt-1 text-sm text-slate-600">
                  {daysLeft > 0
                    ? `Триал активен ещё ${daysLeft} дн.`
                    : "Срок триала истёк"}
                </div>
              )}
            </div>
          </div>
          <a href={UPGRADE_MAILTO}>
            <Button>
              <Sparkles className="h-4 w-4" /> Перейти на Pro
            </Button>
          </a>
        </div>
      </div>

      {/* Usage */}
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 text-sm font-medium text-slate-800">
          Использование
        </div>
        <div className="space-y-4">
          {(["conversations", "messages", "integrations"] as const).map((key) => (
            <UsageBar
              key={key}
              label={USAGE_LABELS[key]}
              used={b.usage[key]}
              limit={b.limits[key] ?? null}
            />
          ))}
        </div>
        <p className="mt-4 text-xs text-slate-400">
          Лимиты пока носят справочный характер — ограничения по тарифу не
          применяются. Учёт расхода AI-токенов появится позже.
        </p>
      </div>
    </div>
  );
}

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | null;
}) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const danger = pct >= 90;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="tabular-nums text-slate-700">
          {fmt(used)}
          {limit !== null ? ` / ${fmt(limit)}` : " / ∞"}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-slate-100">
        <div
          className={danger ? "h-full bg-rose-500" : "h-full bg-brand-500"}
          style={{ width: limit ? `${pct}%` : "0%" }}
        />
      </div>
    </div>
  );
}
