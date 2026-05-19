import { Loader2, TrendingDown, TrendingUp } from "lucide-react";
import type { FunnelResponse, FunnelStage } from "../../lib/api";
import { fmtNumber } from "./format";

type Props = {
  data?: FunnelResponse;
  loading?: boolean;
};

// Цвет на ступень — от тёплого к холодному, win — зелёный, lost — красный.
// Сделано через CSS-классы Tailwind, чтобы прод-сборка не теряла классы
// purge'ом (используем литеральные имена).
const STAGE_COLOR: Record<FunnelStage["key"], { bar: string; text: string }> = {
  conversations: { bar: "bg-brand-500", text: "text-brand-700" },
  with_lead: { bar: "bg-indigo-500", text: "text-indigo-700" },
  with_deal: { bar: "bg-violet-500", text: "text-violet-700" },
  with_won_deal: { bar: "bg-emerald-500", text: "text-emerald-700" },
  with_lost_deal: { bar: "bg-rose-400", text: "text-rose-700" },
};

function formatCurrency(amount: number, currency: string | null): string {
  if (!amount) return "—";
  const formatter = new Intl.NumberFormat("ru-RU", {
    style: currency ? "currency" : "decimal",
    currency: currency || undefined,
    maximumFractionDigits: 0,
  });
  return formatter.format(amount);
}

export function FunnelChart({ data, loading }: Props) {
  if (loading) {
    return (
      <div className="flex h-[240px] items-center justify-center text-sm text-slate-400">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Загрузка…
      </div>
    );
  }
  if (!data || data.stages.length === 0) {
    return (
      <div className="flex h-[240px] items-center justify-center text-sm text-slate-400">
        Нет данных за период
      </div>
    );
  }

  const total = data.stages[0]?.count || 1;

  return (
    <div className="space-y-4">
      <ul className="space-y-2">
        {data.stages.map((stage, idx) => {
          const ratio = total > 0 ? stage.count / total : 0;
          const prev = idx > 0 ? data.stages[idx - 1].count : null;
          const fromPrev =
            prev && prev > 0 ? (stage.count / prev) * 100 : null;
          const color = STAGE_COLOR[stage.key];
          return (
            <li key={stage.key} className="flex items-center gap-3">
              <div className="w-32 shrink-0 text-sm text-slate-700">
                {stage.label}
              </div>
              <div className="relative h-7 flex-1 overflow-hidden rounded bg-slate-100">
                <div
                  className={`${color.bar} h-full rounded transition-all`}
                  style={{ width: `${Math.max(ratio * 100, 2)}%` }}
                />
                <div className="absolute inset-0 flex items-center px-2 text-xs font-medium text-white mix-blend-difference">
                  {fmtNumber(stage.count)}
                </div>
              </div>
              <div className="w-20 shrink-0 text-right text-xs tabular-nums">
                {fromPrev !== null ? (
                  <span className={`inline-flex items-center gap-0.5 ${color.text}`}>
                    {fromPrev >= 50 ? (
                      <TrendingUp className="h-3 w-3" />
                    ) : (
                      <TrendingDown className="h-3 w-3" />
                    )}
                    {fromPrev.toFixed(0)}%
                  </span>
                ) : (
                  <span className="text-slate-400">100%</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="grid grid-cols-3 gap-3 border-t border-slate-100 pt-3 text-center">
        <Metric
          label="В лид"
          value={`${data.conversion_to_lead_pct.toFixed(1)}%`}
          tone="indigo"
        />
        <Metric
          label="В сделку"
          value={`${data.conversion_to_deal_pct.toFixed(1)}%`}
          tone="violet"
        />
        <Metric
          label="Выигрыш"
          value={`${data.win_rate_pct.toFixed(1)}%`}
          tone="emerald"
          hint={
            data.revenue_won
              ? formatCurrency(data.revenue_won, data.currency)
              : undefined
          }
        />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone: "indigo" | "violet" | "emerald";
  hint?: string;
}) {
  const toneMap = {
    indigo: "text-indigo-700",
    violet: "text-violet-700",
    emerald: "text-emerald-700",
  } as const;
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className={`mt-0.5 text-lg font-semibold tabular-nums ${toneMap[tone]}`}>
        {value}
      </div>
      {hint && <div className="text-xs text-slate-400">{hint}</div>}
    </div>
  );
}
