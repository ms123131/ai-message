import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const styles: Record<Variant, string> = {
  primary:
    "bg-brand-600 text-white shadow-sm hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400",
  secondary:
    "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 disabled:opacity-50",
  ghost:
    "bg-transparent text-slate-700 hover:bg-slate-100 disabled:opacity-50",
  danger:
    "bg-rose-600 text-white shadow-sm hover:bg-rose-700 disabled:bg-slate-200",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", className, ...rest }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed",
        styles[variant],
        className,
      )}
      {...rest}
    />
  ),
);
Button.displayName = "Button";
