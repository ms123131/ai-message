import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  RotateCw,
  Send,
  ShieldAlert,
  Smartphone,
} from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";
import { api, ApiError, type TgQrPollResponse } from "../../lib/api";

type Stage =
  | "intro" // дисклеймер
  | "loading" // POST /qr/start в процессе
  | "qr" // показываем QR, поллим
  | "password" // включён 2FA, ждём пароль
  | "connected" // успех (короткий стейт перед редиректом)
  | "expired" // 410 — сессия истекла, нужно начать заново
  | "unavailable"; // 503 — нет TELEGRAM_API_ID/HASH

const POLL_INTERVAL_MS = 2000;

export function TelegramUserWizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [stage, setStage] = useState<Stage>("intro");
  const [integrationId, setIntegrationId] = useState<string | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);

  // Поллинг через setTimeout с защитой от race condition при unmount.
  const cancelledRef = useRef(false);
  useEffect(() => {
    cancelledRef.current = false;
    return () => {
      cancelledRef.current = true;
    };
  }, []);

  // ---------- старт QR-сессии ----------
  const startMutation = useMutation({
    mutationFn: () => api.telegramUserQrStart(),
    onMutate: () => {
      setStage("loading");
      setErrorMessage(null);
    },
    onSuccess: (data) => {
      if (cancelledRef.current) return;
      setIntegrationId(data.integration_id);
      setQrUrl(data.qr_url);
      setStage("qr");
      schedulePoll(data.integration_id, POLL_INTERVAL_MS);
    },
    onError: (err) => {
      handleApiError(err);
    },
  });

  // ---------- 2FA password ----------
  const passwordMutation = useMutation({
    mutationFn: () => {
      if (!integrationId) throw new Error("no integration_id");
      return api.telegramUserPassword(integrationId, password);
    },
    onMutate: () => {
      setPasswordError(null);
    },
    onSuccess: (data) => {
      handlePollResult(data);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 400) {
        setPasswordError("Неверный пароль 2FA");
        return;
      }
      handleApiError(err);
    },
  });

  // ---------- helpers ----------
  function schedulePoll(id: string, delayMs: number) {
    if (cancelledRef.current) return;
    window.setTimeout(() => {
      if (cancelledRef.current) return;
      void pollOnce(id);
    }, delayMs);
  }

  async function pollOnce(id: string) {
    try {
      const data = await api.telegramUserQrPoll(id);
      if (cancelledRef.current) return;
      handlePollResult(data, id);
    } catch (err) {
      if (cancelledRef.current) return;
      handleApiError(err);
    }
  }

  function handlePollResult(data: TgQrPollResponse, idForReschedule?: string) {
    if (data.state === "connected") {
      setStage("connected");
      void qc.invalidateQueries({ queryKey: ["integrations"] });
      toast.success("Telegram подключён");
      window.setTimeout(() => navigate("/integrations"), 800);
      return;
    }
    if (data.state === "requires_password") {
      setStage("password");
      return;
    }
    // waiting — Telegram мог пересоздать токен, обновляем QR
    if (data.qr_url) setQrUrl(data.qr_url);
    if (idForReschedule) {
      schedulePoll(idForReschedule, POLL_INTERVAL_MS);
    }
  }

  function handleApiError(err: unknown) {
    if (!(err instanceof ApiError)) {
      setErrorMessage("Не удалось связаться с сервером");
      setStage("expired");
      return;
    }
    // 503 — на сервере не настроен Telegram (нет API_ID/HASH)
    if (err.status === 503) {
      setStage("unavailable");
      return;
    }
    // 410 — QR-сессия истекла или удалена
    if (err.status === 410) {
      setStage("expired");
      return;
    }
    // 502 — Telegram недоступен из бэка
    if (err.status === 502) {
      setErrorMessage("Telegram временно недоступен. Повторите попытку.");
      setStage("expired");
      return;
    }
    setErrorMessage(err.message || "Произошла ошибка");
    setStage("expired");
  }

  // ---------- render ----------
  return (
    <>
      <PageHeader
        title="Telegram — личный аккаунт"
        description="Подключение через скан QR-кода"
      />
      <div className="mx-auto max-w-2xl space-y-6 p-8">
        <button
          onClick={() => navigate("/integrations")}
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" /> к интеграциям
        </button>

        {stage === "intro" && <IntroBlock onContinue={() => startMutation.mutate()} />}

        {stage === "loading" && (
          <Card>
            <div className="flex items-center justify-center gap-3 py-10 text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              Запрашиваем QR-код у Telegram…
            </div>
          </Card>
        )}

        {stage === "qr" && qrUrl && <QrBlock qrUrl={qrUrl} />}

        {stage === "password" && (
          <PasswordBlock
            password={password}
            setPassword={setPassword}
            onSubmit={() => passwordMutation.mutate()}
            loading={passwordMutation.isPending}
            error={passwordError}
          />
        )}

        {stage === "connected" && (
          <Card>
            <div className="flex flex-col items-center gap-3 py-10 text-emerald-600">
              <CheckCircle2 className="h-12 w-12" />
              <div className="text-lg font-medium">Подключено</div>
              <div className="text-sm text-slate-500">
                Возвращаемся к списку интеграций…
              </div>
            </div>
          </Card>
        )}

        {stage === "expired" && (
          <ExpiredBlock
            message={errorMessage}
            onRetry={() => startMutation.mutate()}
          />
        )}

        {stage === "unavailable" && <UnavailableBlock />}
      </div>
    </>
  );
}

// ---------------- блоки ----------------

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      {children}
    </div>
  );
}

function IntroBlock({ onContinue }: { onContinue: () => void }) {
  const [agreed, setAgreed] = useState(false);
  return (
    <Card>
      <div className="flex items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-sky-50 text-sky-600">
          <Send className="h-5 w-5" />
        </div>
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Перед подключением</h2>
          <p className="text-sm text-slate-600">
            Вы подключаете <b>личный аккаунт</b> Telegram как новое устройство.
            ai-message получит доступ к чтению ваших диалогов для анализа —
            ровно так же, как Telegram Desktop или мобильное приложение.
          </p>
          <ul className="space-y-1.5 text-sm text-slate-600">
            <li className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
              Привязка происходит через скан QR-кода — пароль от Telegram мы
              не видим.
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
              Вы можете отозвать доступ в любой момент: «Настройки →
              Устройства» в Telegram или кнопкой «Удалить» в нашем интерфейсе.
            </li>
            <li className="flex items-start gap-2">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              Сессия хранится зашифрованной. Подключайте только корпоративный
              аккаунт, не личный.
            </li>
          </ul>

          <label className="flex cursor-pointer items-start gap-2 pt-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            <span>
              Я подтверждаю, что являюсь владельцем аккаунта и согласен с
              чтением диалогов сервисом ai-message.
            </span>
          </label>

          <div className="pt-1">
            <Button onClick={onContinue} disabled={!agreed}>
              Продолжить
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function QrBlock({ qrUrl }: { qrUrl: string }) {
  return (
    <Card>
      <div className="grid gap-6 md:grid-cols-[auto,1fr] md:items-start">
        <div className="mx-auto md:mx-0">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <QRCodeSVG
              value={qrUrl}
              size={224}
              level="M"
              includeMargin={false}
            />
          </div>
          <div className="mt-3 flex items-center justify-center gap-1.5 text-xs text-slate-400">
            <RotateCw className="h-3 w-3" />
            QR обновляется автоматически каждые ~30 секунд
          </div>
        </div>
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Отсканируйте QR-код</h2>
          <ol className="space-y-2 text-sm text-slate-600">
            <Step n={1}>
              Откройте Telegram на телефоне, где вы уже залогинены.
            </Step>
            <Step n={2}>
              Перейдите в <b>Настройки → Устройства</b> (или{" "}
              <b>Privacy and Security → Devices</b>).
            </Step>
            <Step n={3}>
              Нажмите <b>«Подключить устройство»</b> (Link Desktop Device) и
              отсканируйте этот код.
            </Step>
          </ol>
          <div className="flex items-center gap-2 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
            <Smartphone className="h-4 w-4" />
            После скана может появиться шаг ввода пароля двухфакторной
            аутентификации — это нормально.
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Ожидаем подтверждения от Telegram…
          </div>
        </div>
      </div>
    </Card>
  );
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-medium text-brand-700">
        {n}
      </span>
      <span className="leading-relaxed">{children}</span>
    </li>
  );
}

function PasswordBlock({
  password,
  setPassword,
  onSubmit,
  loading,
  error,
}: {
  password: string;
  setPassword: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  error: string | null;
}) {
  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-md bg-amber-50 text-amber-600">
            <ShieldAlert className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Двухфакторная аутентификация</h2>
            <p className="text-sm text-slate-500">
              QR отсканирован. У вашего аккаунта включён облачный пароль —
              введите его, чтобы завершить вход.
            </p>
          </div>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!loading && password.length > 0) onSubmit();
          }}
          className="space-y-3"
        >
          <Input
            label="Пароль 2FA"
            type="password"
            autoFocus
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={error ?? undefined}
            placeholder="Облачный пароль Telegram"
          />
          <div className="flex justify-end">
            <Button type="submit" disabled={loading || password.length === 0}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              Войти
            </Button>
          </div>
        </form>
      </div>
    </Card>
  );
}

function ExpiredBlock({
  message,
  onRetry,
}: {
  message: string | null;
  onRetry: () => void;
}) {
  return (
    <Card>
      <div className="space-y-3 text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-amber-50 text-amber-600">
          <AlertTriangle className="h-6 w-6" />
        </div>
        <h2 className="text-lg font-semibold">Сессия истекла</h2>
        <p className="text-sm text-slate-500">
          {message ??
            "QR-код больше не действителен. Сгенерируйте новый и отсканируйте заново."}
        </p>
        <div className="pt-2">
          <Button onClick={onRetry}>
            <RotateCw className="h-4 w-4" />
            Начать заново
          </Button>
        </div>
      </div>
    </Card>
  );
}

function UnavailableBlock() {
  return (
    <Card>
      <div className="space-y-3 text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-rose-50 text-rose-600">
          <ShieldAlert className="h-6 w-6" />
        </div>
        <h2 className="text-lg font-semibold">Интеграция не настроена</h2>
        <p className="text-sm text-slate-500">
          На сервере не заданы переменные <code>TELEGRAM_API_ID</code> и{" "}
          <code>TELEGRAM_API_HASH</code>. Обратитесь к администратору ai-message —
          их нужно получить на{" "}
          <a
            href="https://my.telegram.org"
            target="_blank"
            rel="noreferrer"
            className="text-brand-600 hover:underline"
          >
            my.telegram.org
          </a>{" "}
          и добавить в <code>.env</code>.
        </p>
      </div>
    </Card>
  );
}

