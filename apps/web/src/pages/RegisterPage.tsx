import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Loader2, MessageSquareText } from "lucide-react";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";

export function RegisterPage() {
  const { status, register } = useAuth();
  const nav = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") return <Navigate to="/dashboard" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({
        email,
        password,
        full_name: fullName || undefined,
        workspace_name: workspace || undefined,
      });
      nav("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 409
            ? "Этот email уже зарегистрирован"
            : err.message,
        );
      } else {
        setError("Не удалось зарегистрироваться");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-6">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-brand-600 text-white">
            <MessageSquareText className="h-5 w-5" />
          </div>
          <div className="text-lg font-semibold tracking-tight">ai-message</div>
        </div>
        <h1 className="mb-1 text-base font-semibold text-slate-800">
          Создание аккаунта
        </h1>
        <p className="mb-5 text-sm text-slate-500">
          Создадим ваше рабочее пространство и привяжем к нему подключения.
        </p>
        <form className="space-y-3" onSubmit={onSubmit}>
          <input
            type="text"
            placeholder="Имя (необязательно)"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
          />
          <input
            type="text"
            placeholder="Название workspace (необязательно)"
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
          />
          <input
            type="email"
            autoComplete="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
          />
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            placeholder="Пароль (минимум 8 символов)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
          />
          {error && (
            <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Создать аккаунт
          </button>
        </form>
        <p className="mt-4 text-center text-xs text-slate-500">
          Уже есть аккаунт?{" "}
          <Link to="/login" className="text-brand-600 hover:underline">
            Войти
          </Link>
        </p>
      </div>
    </div>
  );
}
