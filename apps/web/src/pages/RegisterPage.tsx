import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { Loader2, MailCheck } from "lucide-react";
import { useAuth } from "../lib/auth";
import { api, ApiError } from "../lib/api";
import {
  AuthShell,
  authButtonClass,
  authErrorClass,
  authInputClass,
} from "../components/AuthShell";

const RESEND_COOLDOWN_SEC = 60;

export function RegisterPage() {
  const { status, register } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // После успешной регистрации показываем экран «проверьте почту».
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [resendLeft, setResendLeft] = useState(0);

  if (status === "authenticated") return <Navigate to="/dashboard" replace />;

  function startCooldown() {
    setResendLeft(RESEND_COOLDOWN_SEC);
    const timer = setInterval(() => {
      setResendLeft((s) => {
        if (s <= 1) {
          clearInterval(timer);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const resp = await register({
        email,
        password,
        full_name: fullName || undefined,
        workspace_name: workspace || undefined,
      });
      setSentTo(resp.email);
      startCooldown();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 409 ? "Этот email уже зарегистрирован" : err.message,
        );
      } else {
        setError("Не удалось зарегистрироваться");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function onResend() {
    if (!sentTo || resendLeft > 0) return;
    try {
      await api.resendVerification(sentTo);
    } catch {
      // ответ обезличен — даже при ошибке не раскрываем деталей
    }
    startCooldown();
  }

  if (sentTo) {
    return (
      <AuthShell
        title="Проверьте почту"
        subtitle={
          <>
            Мы отправили письмо со ссылкой подтверждения на{" "}
            <span className="font-medium text-slate-700">{sentTo}</span>.
            Перейдите по ссылке из письма, чтобы завершить регистрацию и войти.
          </>
        }
        footer={
          <Link to="/login" className="text-brand-600 hover:underline">
            Вернуться ко входу
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-4 py-2">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-brand-50 text-brand-600">
            <MailCheck className="h-6 w-6" />
          </div>
          <p className="text-center text-xs text-slate-500">
            Не пришло письмо? Проверьте папку «Спам».
          </p>
          <button
            type="button"
            onClick={onResend}
            disabled={resendLeft > 0}
            className={authButtonClass}
          >
            {resendLeft > 0
              ? `Отправить повторно (${resendLeft})`
              : "Отправить письмо повторно"}
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Создание аккаунта"
      subtitle="Создадим ваше рабочее пространство и привяжем к нему подключения."
      footer={
        <>
          Уже есть аккаунт?{" "}
          <Link to="/login" className="text-brand-600 hover:underline">
            Войти
          </Link>
        </>
      }
    >
      <form className="space-y-3" onSubmit={onSubmit}>
        <input
          type="text"
          placeholder="Имя (необязательно)"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className={authInputClass}
        />
        <input
          type="text"
          placeholder="Название workspace (необязательно)"
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
          className={authInputClass}
        />
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
          autoComplete="new-password"
          required
          minLength={8}
          placeholder="Пароль (минимум 8 символов)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={authInputClass}
        />
        {error && <div className={authErrorClass}>{error}</div>}
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Создать аккаунт
        </button>
      </form>
    </AuthShell>
  );
}
