import type { LucideIcon } from "lucide-react";
import { cn } from "../../lib/cn";

export type TabItem<Id extends string = string> = {
  id: Id;
  label: string;
  icon?: LucideIcon;
  /** Текстовый бейдж справа от названия (например, «скоро»). */
  badge?: string;
};

type TabsProps<Id extends string> = {
  tabs: ReadonlyArray<TabItem<Id>>;
  value: Id;
  onChange: (id: Id) => void;
  className?: string;
};

/**
 * Подчёркнутый таб-бар. Вынесен из DashboardPage, чтобы переиспользовать в
 * Settings и других экранах. Активный таб и URL-синхронизацию хранит
 * вызывающая страница (обычно через useSearchParams).
 */
export function Tabs<Id extends string>({
  tabs,
  value,
  onChange,
  className,
}: TabsProps<Id>) {
  return (
    <div className={cn("flex items-center gap-1 border-b border-slate-200", className)}>
      {tabs.map(({ id, label, icon: Icon, badge }) => (
        <button
          key={id}
          type="button"
          onClick={() => onChange(id)}
          className={cn(
            "relative -mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition",
            value === id
              ? "border-brand-600 text-brand-700"
              : "border-transparent text-slate-500 hover:text-slate-800",
          )}
        >
          {Icon && <Icon className="h-4 w-4" />}
          {label}
          {badge && (
            <span className="ml-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-slate-500">
              {badge}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
