import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { KPI } from "../../lib/api";
import { cn } from "../../lib/cn";

type Format = "number" | "duration" | "percent";

export type KPICardProps = {
  label: string;
  kpi?: KPI | null;
  value?: number;
  format?: Format;
  /** true = рост ХОРОШО (зелёный). false = рост ПЛОХО (например, FRT — меньше лучше). */
  higherIsBetter?: boolean;
  loading?: boolean;
  /** Дополнительная подсказка под значением (например, «сейчас открыто»). */
  hint?: string;
};

function fmtNumber(v: number): string {
  return new Intl.NumberFormat("ru-RU").format(Math.round(v));
}

function fmtDuration(sec: number): string {
  if (!sec || sec < 1) return "—";
  if (sec < 60) return `${Math.round(sec)}с`;
  const m = sec / 60;
  if (m < 60) return `${m.toFixed(1).replace(".0", "")} мин`;
  const h = m / 60;
  if (h < 24) return `${h.toFixed(1).replace(".0", "")} ч`;
  return `${(h / 24).toFixed(1)} д`;
}

function fmtPercent(v: number): string {
  if (v === undefined || v === null) return "—";
  return `${Math.round(v)}%`;
}

function fmtValue(v: number, format: Format): string {
  if (format === "duration") return fmtDuration(v);
  if (format === "percent") return fmtPercent(v);
  return fmtNumber(v);
}

export function KPICard({
  label,
  kpi,
  value,
  format = "number",
  higherIsBetter = true,
  loading,
  hint,
}: KPICardProps) {
  const v = kpi?.value ?? value;
  const delta = kpi?.delta_pct ?? null;

  let trendColor = "text-slate-400";
  let TrendIcon = Minus;
  let trendText = "—";

  if (delta !== null && delta !== undefined && Number.isFinite(delta)) {
    const isPositiveDelta = delta > 0.5;
    const isNegativeDelta = delta < -0.5;
    if (isPositiveDelta) {
      TrendIcon = ArrowUpRight;
      trendColor = higherIsBetter ? "text-emerald-600" : "text-rose-600";
    } else if (isNegativeDelta) {
      TrendIcon = ArrowDownRight;
      trendColor = higherIsBetter ? "text-rose-600" : "text-emerald-600";
    } else {
      TrendIcon = Minus;
      trendColor = "text-slate-400";
    }
    const sign = delta > 0 ? "+" : "";
    trendText = `${sign}${delta.toFixed(1)}%`;
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <div className="text-2xl font-semibold tabular-nums text-slate-900">
          {loading ? (
            <span className="text-slate-300">…</span>
          ) : v === undefined || v === null ? (
            "—"
          ) : (
            fmtValue(v, format)
          )}
        </div>
        <div
          className={cn(
            "inline-flex items-center gap-0.5 text-xs font-medium",
            trendColor,
          )}
          title="изменение к предыдущему периоду"
        >
          <TrendIcon className="h-3.5 w-3.5" />
          {trendText}
        </div>
      </div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}
