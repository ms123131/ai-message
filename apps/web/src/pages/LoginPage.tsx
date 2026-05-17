import { useNavigate } from "react-router-dom";
import { MessageSquareText } from "lucide-react";

export function LoginPage() {
  const nav = useNavigate();
  return (
    <div className="grid min-h-full place-items-center bg-slate-50 p-6">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-brand-600 text-white">
            <MessageSquareText className="h-5 w-5" />
          </div>
          <div className="text-lg font-semibold tracking-tight">ai-message</div>
        </div>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            nav("/dashboard");
          }}
        >
          <input
            type="email"
            placeholder="Email"
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
            defaultValue="demo@ai-message.local"
          />
          <input
            type="password"
            placeholder="Пароль"
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
            defaultValue="demo"
          />
          <button
            type="submit"
            className="w-full rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
          >
            Войти
          </button>
        </form>
        <p className="mt-4 text-center text-xs text-slate-400">
          Демо-режим — авторизация будет добавлена в фазе 2
        </p>
      </div>
    </div>
  );
}
