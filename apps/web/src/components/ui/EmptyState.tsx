import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/**
 * Унифицированный empty-state. Заменяет разбросанные по страницам блоки
 * «Пока ничего нет / Подключите интеграцию / Нет данных», у которых сейчас
 * разное оформление и иногда вообще `null`.
 *
 * Использование:
 *   <EmptyState
 *     icon={Inbox}
 *     title="Пока нет диалогов"
 *     description="Подключите Bitrix24, чтобы начать получать сообщения"
 *     action={<Button onClick={...}>Подключить</Button>}
 *   />
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  size = "md",
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  /** sm — для inline-блоков, md — для секций, lg — для всей страницы. */
  size?: "sm" | "md" | "lg";
}) {
  const padding = {
    sm: "py-6",
    md: "py-10",
    lg: "py-16",
  }[size];
  const iconSize = {
    sm: "h-6 w-6",
    md: "h-8 w-8",
    lg: "h-10 w-10",
  }[size];

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        padding,
        className,
      )}
    >
      {Icon && (
        <div className="mb-3 grid place-items-center rounded-full bg-slate-100 p-3 text-slate-400">
          <Icon className={iconSize} aria-hidden="true" />
        </div>
      )}
      <div className="text-sm font-medium text-slate-700">{title}</div>
      {description && (
        <div className="mt-1 max-w-sm text-xs text-slate-500">{description}</div>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
