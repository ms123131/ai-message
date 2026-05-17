import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, className, id, ...rest }, ref) => {
    const inputId =
      id ?? `i_${Math.random().toString(36).slice(2, 8)}`;
    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-slate-700"
          >
            {label}
          </label>
        )}
        <input
          id={inputId}
          ref={ref}
          className={cn(
            "w-full rounded-md border bg-white px-3 py-2 text-sm outline-none transition",
            error
              ? "border-rose-300 focus:border-rose-500"
              : "border-slate-200 focus:border-brand-500",
            className,
          )}
          {...rest}
        />
        {hint && !error && (
          <p className="text-xs text-slate-500">{hint}</p>
        )}
        {error && <p className="text-xs text-rose-600">{error}</p>}
      </div>
    );
  },
);
Input.displayName = "Input";
