import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";
import { api, ApiError } from "../lib/api";
import {
  AuthShell,
  authButtonClass,
  authErrorClass,
  authInputClass,
} from "../components/AuthShell";

export function LoginPage() {
  const { status, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from ?? "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // 403 email_not_verified → предлагаем переслать письмо подтверждения.
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resent, setResent] = useState(false);

  if (status === "authenticated") return <Navigate to={from} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNeedsVerification(false);
    setResent(false);
    setSubmitting(true);
    try {
      await login(email, password);
      nav(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setNeedsVerification(true);
          setError("Адрес почты не подтверждён. Завершите регистрацию по ссылке из письма.");
        } else {
          setError(err.status === 401 ? "Неверный email или пароль" : err.message);
        }
      } else {
        setError("Не удалось войти");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function onResend() {
    try {
      await api.resendVerification(email);
    } catch {
      // ответ обезличен
    }
    setResent(true);
  }

  return (
    <AuthShell
      title="Вход в аккаунт"
      subtitle="Анализ коммуникаций из всех каналов в одном месте."
      footer={
        <>
          Нет аккаунта?{" "}
          <Link to="/register" className="text-brand-600 hover:underline">
            Создать
          </Link>
        </>
      }
    >
      <form className="space-y-3" onSubmit={onSubmit}>
        <input
          type="email"
          autoComplete="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={authInputClass}
        />
        <input
          type="password"
          autoComplete="current-password"
          required
          placeholder="Пароль"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={authInputClass}
        />
        {error && <div className={authErrorClass}>{error}</div>}
        {needsVerification &&
          (resent ? (
            <p className="text-xs text-slate-500">
              Письмо отправлено повторно — проверьте почту.
            </p>
          ) : (
            <button
              type="button"
              onClick={onResend}
              className="text-xs text-brand-600 hover:underline"
            >
              Отправить письмо подтверждения повторно
            </button>
          ))}
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Войти
        </button>
      </form>
      <p className="mt-3 text-center text-xs text-slate-500">
        <Link to="/forgot-password" className="text-brand-600 hover:underline">
          Забыли пароль?
        </Link>
      </p>
    </AuthShell>
  );
}
