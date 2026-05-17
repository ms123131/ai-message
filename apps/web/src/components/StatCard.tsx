import type { LucideIcon } from "lucide-react";

export function StatCard({
  label,
  value,
  delta,
  icon: Icon,
}: {
  label: string;
  value: string;
  delta?: string;
  icon: LucideIcon;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">{label}</div>
        <div className="grid h-8 w-8 place-items-center rounded-md bg-brand-50 text-brand-600">
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {delta && (
        <div className="mt-1 text-xs text-emerald-600 font-medium">{delta}</div>
      )}
    </div>
  );
}
