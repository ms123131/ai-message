import type { ReactNode } from "react";
import { cn } from "../lib/cn";

interface CTAButtonProps {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  size?: "md" | "lg";
  className?: string;
  /** Внешняя ссылка (mailto/telegram) — открываем в новой вкладке. */
  external?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2";

const variants = {
  primary:
    "bg-brand-600 text-white shadow-sm shadow-brand-600/20 hover:bg-brand-700 hover:shadow-md hover:shadow-brand-600/25 active:translate-y-px",
  secondary:
    "bg-white text-slate-900 ring-1 ring-inset ring-slate-200 hover:ring-slate-300 hover:bg-slate-50 active:translate-y-px",
  ghost: "text-slate-600 hover:text-slate-900",
} as const;

const sizes = {
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
} as const;

export function CTAButton({
  href,
  children,
  variant = "primary",
  size = "md",
  className,
  external = false,
}: CTAButtonProps) {
  return (
    <a
      href={href}
      className={cn(base, variants[variant], sizes[size], className)}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
    >
      {children}
    </a>
  );
}
