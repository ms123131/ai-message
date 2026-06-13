import { type ReactNode } from "react";
import { BrandMark } from "./icons/BrandMark";

// Общий каркас экранов аутентификации: центрированная карточка с логотипом.
// Используется страницами login/register/verify/forgot/reset.
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-brand-600 text-white">
            <BrandMark className="h-5 w-5" />
          </div>
          <div className="text-lg font-semibold tracking-tight">ai-message</div>
        </div>
        <h1 className="mb-1 text-base font-semibold text-slate-800">{title}</h1>
        {subtitle && <p className="mb-5 text-sm text-slate-500">{subtitle}</p>}
        {children}
        {footer && (
          <div className="mt-4 text-center text-xs text-slate-500">{footer}</div>
        )}
      </div>
    </div>
  );
}

export const authInputClass =
  "w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500";

export const authButtonClass =
  "flex w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300";

export const authErrorClass =
  "rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700";
