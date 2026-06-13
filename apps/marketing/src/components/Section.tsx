import type { ReactNode } from "react";
import { useReveal } from "../lib/useReveal";
import { cn } from "../lib/cn";

interface SectionProps {
  id?: string;
  children: ReactNode;
  className?: string;
  /** Подложка секции. По умолчанию прозрачная (наследует фон страницы). */
  tone?: "default" | "muted";
}

// Базовая обёртка секции: единый горизонтальный ритм, вертикальные отступы
// и reveal-анимация на скролле. Контент центрируется в колонке max-w-6xl.
export function Section({ id, children, className, tone = "default" }: SectionProps) {
  const ref = useReveal<HTMLElement>();
  return (
    <section
      id={id}
      ref={ref}
      className={cn(
        "reveal scroll-mt-20",
        tone === "muted" && "bg-slate-50",
        className,
      )}
    >
      <div className="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8 sm:py-28">
        {children}
      </div>
    </section>
  );
}

// Заголовок секции: надзаголовок-маркер + крупный заголовок + лид.
export function SectionHeading({
  eyebrow,
  title,
  lead,
  align = "left",
}: {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  align?: "left" | "center";
}) {
  return (
    <div className={cn("max-w-2xl", align === "center" && "mx-auto text-center")}>
      {eyebrow && (
        <div
          className={cn(
            "mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-brand-600",
            align === "center" && "justify-center",
          )}
        >
          <span className="h-px w-6 bg-brand-300" />
          {eyebrow}
        </div>
      )}
      <h2 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
        {title}
      </h2>
      {lead && (
        <p className="mt-4 text-lg leading-relaxed text-slate-600">{lead}</p>
      )}
    </div>
  );
}
