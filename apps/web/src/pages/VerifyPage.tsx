import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { AuthShell } from "../components/AuthShell";

export function VerifyPage() {
  const { status, verify } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token");

  const [error, setError] = useState<string | null>(null);
  // StrictMode в dev монтирует эффект дважды — гасим повторный вызов verify
  // (токен одноразовый, второй запрос вернёт 400).
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!token) {
      setError("Ссылка некорректна: отсутствует токен.");
      return;
    }
    (async () => {
      try {
        await verify(token);
        nav("/dashboard", { replace: true });
      } catch (err) {
        if (err instanceof ApiError && err.status === 400) {
          setError("Ссылка недействительна или истёк срок её действия.");
        } else {
          setError("Не удалось подтвердить почту. Попробуйте позже.");
        }
      }
    })();
  }, [token, verify, nav]);

  if (status === "authenticated") return <Navigate to="/dashboard" replace />;

  if (error) {
    return (
      <AuthShell
        title="Не удалось подтвердить почту"
        subtitle={error}
        footer={
          <Link to="/login" className="text-brand-600 hover:underline">
            Вернуться ко входу
          </Link>
        }
      >
        <p className="text-center text-xs text-slate-500">
          Запросите новое письмо на странице входа — кнопка «Отправить письмо
          подтверждения повторно».
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Подтверждаем почту" subtitle="Секунду, проверяем ссылку…">
      <div className="flex justify-center py-4">
        <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
      </div>
    </AuthShell>
  );
}
