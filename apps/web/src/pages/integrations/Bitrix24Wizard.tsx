import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Loader2,
  Plug,
  Webhook,
} from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { cn } from "../../lib/cn";
import { api, ApiError } from "../../lib/api";

type Mode = "oauth" | "webhook";
type Step = 0 | 1 | 2;

const PENDING_KEY = "ai-message:b24-pending-oauth";

function normalizeDomain(input: string): string {
  return input
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/\/.*$/, "")
    .toLowerCase();
}

function isValidBitrixDomain(domain: string): boolean {
  return /^[a-z0-9-]+\.bitrix24\.[a-z.]+$/i.test(domain);
}

export function Bitrix24Wizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>(0);
  const [mode, setMode] = useState<Mode>("oauth");

  const [label, setLabel] = useState("");
  const [domain, setDomain] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");

  const normalizedDomain = useMemo(() => normalizeDomain(domain), [domain]);
  const domainValid = isValidBitrixDomain(normalizedDomain);
  const webhookValid =
    /^https:\/\/[^/]+\.bitrix24\.[a-z.]+\/rest\/\d+\/[a-z0-9]+\/?$/i.test(
      webhookUrl.trim(),
    );

  const step1Valid =
    label.trim().length > 1 &&
    (mode === "oauth"
      ? domainValid && clientId.trim().length > 5 && clientSecret.trim().length > 5
      : webhookValid);

  const createWebhook = useMutation({
    mutationFn: api.createBitrix24Webhook,
    onSuccess: () => setStep(2),
  });

  const createOAuth = useMutation({
    mutationFn: api.createBitrix24OAuth,
    onSuccess: (data) => {
      sessionStorage.setItem(
        PENDING_KEY,
        JSON.stringify({ id: data.integration.id }),
      );
      window.location.href = data.authorize_url;
    },
  });

  const submitting = createOAuth.isPending || createWebhook.isPending;
  const submitError =
    (createOAuth.error as ApiError | undefined)?.message ??
    (createWebhook.error as ApiError | undefined)?.message;

  function handleSubmit() {
    if (mode === "webhook") {
      createWebhook.mutate({
        label: label.trim(),
        webhook_url: webhookUrl.trim().replace(/\/?$/, "/"),
      });
    } else {
      createOAuth.mutate({
        label: label.trim(),
        domain: normalizedDomain,
        client_id: clientId.trim(),
        client_secret: clientSecret.trim(),
      });
    }
  }

  return (
    <>
      <PageHeader
        title="Подключение Bitrix24"
        description="Импорт чатов Open Channels, CRM-активностей и email-событий"
        actions={
          <Button
            variant="secondary"
            onClick={() => navigate("/integrations")}
          >
            <ArrowLeft className="h-4 w-4" /> К интеграциям
          </Button>
        }
      />
      <div className="mx-auto max-w-3xl space-y-6 p-8">
        <Stepper step={step} />

        {step === 0 && (
          <StepCard
            title="Способ подключения"
            description="Выберите, как ai-message будет получать данные из вашего Bitrix24"
          >
            <ModeCard
              active={mode === "oauth"}
              onClick={() => setMode("oauth")}
              icon={<KeyRound className="h-5 w-5" />}
              title="OAuth-приложение"
              description="Полные права (CRM, Open Channels, события). Требует регистрации локального приложения на портале."
              recommended
            />
            <ModeCard
              active={mode === "webhook"}
              onClick={() => setMode("webhook")}
              icon={<Webhook className="h-5 w-5" />}
              title="Входящий webhook"
              description="Быстрый старт без публикации приложения. Без подписки на события — только опрос API."
            />
            <div className="flex justify-end pt-2">
              <Button onClick={() => setStep(1)}>
                Далее <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </StepCard>
        )}

        {step === 1 && (
          <StepCard
            title={
              mode === "oauth"
                ? "Параметры OAuth-приложения"
                : "Параметры входящего webhook'а"
            }
            description={
              mode === "oauth" ? (
                <>
                  Создайте локальное приложение в разделе{" "}
                  <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
                    Разработчикам → Другое → Локальное приложение
                  </code>
                  . Укажите callback URL:{" "}
                  <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
                    {window.location.origin}/integrations/bitrix24/callback
                  </code>
                </>
              ) : (
                <>
                  Создайте входящий webhook в разделе{" "}
                  <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
                    Разработчикам → Другое → Входящий вебхук
                  </code>
                  . Выдайте права <code>crm</code>, <code>imopenlines</code>,{" "}
                  <code>im</code>, <code>user</code>.
                </>
              )
            }
          >
            <Input
              label="Название подключения"
              placeholder="Например: Главный портал"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />

            {mode === "oauth" ? (
              <>
                <Input
                  label="Домен портала"
                  placeholder="mycompany.bitrix24.ru"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  hint="Формат: <название>.bitrix24.<ru/com/de/...>"
                  error={
                    domain && !domainValid
                      ? "Некорректный домен Bitrix24"
                      : undefined
                  }
                />
                <Input
                  label="client_id"
                  placeholder="app.65f3b9e7a2c4d8.12345678"
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                />
                <Input
                  label="client_secret"
                  type="password"
                  placeholder="••••••••"
                  value={clientSecret}
                  onChange={(e) => setClientSecret(e.target.value)}
                  hint="Хранится на сервере. Используется для обмена code на access_token."
                />
              </>
            ) : (
              <Input
                label="URL webhook'а"
                placeholder="https://mycompany.bitrix24.ru/rest/1/xxxxxxxxxxxxxxxx/"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                error={
                  webhookUrl && !webhookValid
                    ? "Ожидается URL вида https://portal.bitrix24.ru/rest/<user>/<token>/"
                    : undefined
                }
              />
            )}

            {submitError && (
              <div className="flex items-start gap-2 rounded-md bg-rose-50 p-3 text-sm text-rose-700">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <div>{submitError}</div>
              </div>
            )}

            <div className="flex justify-between pt-2">
              <Button
                variant="secondary"
                onClick={() => setStep(0)}
                disabled={submitting}
              >
                <ArrowLeft className="h-4 w-4" /> Назад
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={!step1Valid || submitting}
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Сохранение…
                  </>
                ) : mode === "oauth" ? (
                  <>
                    Перейти на портал <ExternalLink className="h-4 w-4" />
                  </>
                ) : (
                  <>
                    Сохранить <CheckCircle2 className="h-4 w-4" />
                  </>
                )}
              </Button>
            </div>
          </StepCard>
        )}

        {step === 2 && (
          <StepCard
            title="Подключение создано"
            description="Bitrix24 успешно сохранён в списке интеграций"
          >
            <div className="flex items-start gap-3 rounded-md bg-emerald-50 p-4 text-sm text-emerald-700">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
              <div>
                Соединение «{label}» добавлено. Backend будет периодически
                опрашивать API и принимать webhook-события.
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <Button onClick={() => navigate("/integrations")}>
                <Plug className="h-4 w-4" /> К списку интеграций
              </Button>
            </div>
          </StepCard>
        )}
      </div>
    </>
  );
}

function StepCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="mb-5">
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-slate-500">{description}</p>
        )}
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function Stepper({ step }: { step: Step }) {
  const items = ["Способ", "Параметры", "Готово"];
  return (
    <ol className="flex items-center gap-3 text-sm">
      {items.map((label, i) => (
        <li key={label} className="flex items-center gap-3">
          <div
            className={cn(
              "grid h-6 w-6 place-items-center rounded-full text-xs font-medium",
              i < step
                ? "bg-emerald-100 text-emerald-700"
                : i === step
                ? "bg-brand-600 text-white"
                : "bg-slate-100 text-slate-400",
            )}
          >
            {i < step ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
          </div>
          <span
            className={cn(
              "font-medium",
              i === step ? "text-slate-900" : "text-slate-400",
            )}
          >
            {label}
          </span>
          {i < items.length - 1 && (
            <span className="h-px w-8 bg-slate-200" />
          )}
        </li>
      ))}
    </ol>
  );
}

function ModeCard({
  active,
  onClick,
  icon,
  title,
  description,
  recommended,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  description: string;
  recommended?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-3 rounded-md border p-4 text-left transition",
        active
          ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100"
          : "border-slate-200 bg-white hover:border-slate-300",
      )}
    >
      <div
        className={cn(
          "grid h-9 w-9 shrink-0 place-items-center rounded-md",
          active ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600",
        )}
      >
        {icon}
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{title}</span>
          {recommended && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
              рекомендуется
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
      </div>
    </button>
  );
}
