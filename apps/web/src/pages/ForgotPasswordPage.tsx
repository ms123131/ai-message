import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Loader2, MailCheck } from "lucide-react";
import { api } from "../lib/api";
import {
  AuthShell,
  authButtonClass,
  authInputClass,
} from "../components/AuthShell";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.forgotPassword(email);
    } catch {
      // ответ обезличен — не раскрываем, зарегистрирован ли адрес
    } finally {
      setSubmitting(false);
      setSent(true);
    }
  }

  if (sent) {
    return (
      <AuthShell
        title="Проверьте почту"
        subtitle="Если этот адрес зарегистрирован, мы отправили на него письмо со ссылкой для сброса пароля."
        footer={
          <Link to="/login" className="text-brand-600 hover:underline">
            Вернуться ко входу
          </Link>
        }
      >
        <div className="flex justify-center py-2">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-brand-50 text-brand-600">
            <MailCheck className="h-6 w-6" />
          </div>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Сброс пароля"
      subtitle="Укажите email — пришлём ссылку для установки нового пароля."
      footer={
        <Link to="/login" className="text-brand-600 hover:underline">
          Вернуться ко входу
        </Link>
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
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Отправить ссылку
        </button>
      </form>
    </AuthShell>
  );
}
