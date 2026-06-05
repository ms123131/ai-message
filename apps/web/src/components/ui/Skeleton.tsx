import { cn } from "../../lib/cn";

/**
 * Скелетон-плашка для loading-стейта. Заменяет "…" и Loader2 в местах,
 * где известна форма будущего контента.
 *
 * Использование:
 *   <Skeleton className="h-4 w-32" />
 *   <Skeleton variant="circle" className="h-8 w-8" />
 *   <SkeletonText lines={3} />
 */
export function Skeleton({
  className,
  variant = "rect",
}: {
  className?: string;
  variant?: "rect" | "circle";
}) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "animate-pulse bg-slate-200/70",
        variant === "circle" ? "rounded-full" : "rounded-md",
        className,
      )}
    />
  );
}

export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn("h-3", i === lines - 1 ? "w-2/3" : "w-full")}
        />
      ))}
    </div>
  );
}
