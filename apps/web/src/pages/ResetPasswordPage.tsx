import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import {
  AuthShell,
  authButtonClass,
  authErrorClass,
  authInputClass,
} from "../components/AuthShell";

export function ResetPasswordPage() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token");

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Ссылка некорректна: отсутствует токен.");
      return;
    }
    if (password !== confirm) {
      setError("Пароли не совпадают.");
      return;
    }
    setSubmitting(true);
    try {
      await api.resetPassword(token, password);
      // Пароль сменён — отправляем на вход с новым паролем.
      nav("/login", { replace: true, state: { resetDone: true } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError("Ссылка недействительна или истёк срок её действия.");
      } else {
        setError("Не удалось сменить пароль. Попробуйте позже.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Новый пароль"
      subtitle="Задайте новый пароль для вашего аккаунта."
      footer={
        <Link to="/login" className="text-brand-600 hover:underline">
          Вернуться ко входу
        </Link>
      }
    >
      <form className="space-y-3" onSubmit={onSubmit}>
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          placeholder="Новый пароль (минимум 8 символов)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={authInputClass}
        />
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          placeholder="Повторите пароль"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className={authInputClass}
        />
        {error && <div className={authErrorClass}>{error}</div>}
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Сменить пароль
        </button>
      </form>
    </AuthShell>
  );
}
