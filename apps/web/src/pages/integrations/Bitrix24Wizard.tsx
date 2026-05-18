import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Loader2,
  Plug,
  Store,
} from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { cn } from "../../lib/cn";
import { api, ApiError } from "../../lib/api";

type Mode = "marketplace" | "local";

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

type NotInstalledDetail = {
  status: "not_installed";
  domain: string;
  install_instructions_url: string;
  message: string;
};

const INSTALL_PATH = "/install/bitrix24";

export function Bitrix24Wizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [mode, setMode] = useState<Mode>("local");
  const [domain, setDomain] = useState("");
  const [label, setLabel] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  const configQuery = useQuery({
    queryKey: ["bitrix24-config"],
    queryFn: api.getBitrix24Config,
    staleTime: 5 * 60 * 1000,
  });
  const hasGlobalCreds = configQuery.data?.has_global_credentials ?? false;

  const normalizedDomain = useMemo(() => normalizeDomain(domain), [domain]);
  const domainValid = isValidBitrixDomain(normalizedDomain);
  const credsValid =
    mode === "marketplace" ||
    hasGlobalCreds ||
    (clientId.trim().length > 5 && clientSecret.trim().length > 5);
  const installUrl =
    configQuery.data?.install_url ?? `${window.location.origin}${INSTALL_PATH}`;

  const connect = useMutation({
    mutationFn: api.connectBitrix24,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
      navigate("/integrations");
    },
  });

  const apiError = connect.error as ApiError | undefined;
  const notInstalled: NotInstalledDetail | null =
    apiError?.status === 404 &&
    typeof apiError.body === "object" &&
    apiError.body !== null &&
    "detail" in apiError.body &&
    typeof (apiError.body as { detail: unknown }).detail === "object" &&
    (apiError.body as { detail: { status?: string } }).detail.status ===
      "not_installed"
      ? ((apiError.body as { detail: NotInstalledDetail }).detail)
      : null;

  function handleSubmit() {
    const useManualCreds = mode === "local" && !hasGlobalCreds;
    connect.mutate({
      domain: normalizedDomain,
      label: label.trim() || undefined,
      client_id: useManualCreds ? clientId.trim() : undefined,
      client_secret: useManualCreds ? clientSecret.trim() : undefined,
    });
  }

  return (
    <>
      <PageHeader
        title="Подключение Bitrix24"
        description="Введите доменное имя вашего портала Bitrix24"
        actions={
          <Button variant="secondary" onClick={() => navigate("/integrations")}>
            <ArrowLeft className="h-4 w-4" /> К интеграциям
          </Button>
        }
      />
      <div className="mx-auto max-w-2xl space-y-6 p-8">
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-base font-semibold tracking-tight">
            Способ подключения
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ModeCard
              active={mode === "local"}
              onClick={() => setMode("local")}
              icon={<KeyRound className="h-5 w-5" />}
              title="Локальное приложение"
              description="У вас своё локальное приложение в Bitrix24. Введите его client_id и client_secret."
            />
            <ModeCard
              active={mode === "marketplace"}
              onClick={() => setMode("marketplace")}
              icon={<Store className="h-5 w-5" />}
              title="Marketplace"
              description="Установите наше приложение из Bitrix24 Marketplace — токены придут автоматически."
              soon
            />
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="text-base font-semibold tracking-tight">
            {mode === "local"
              ? "Шаг 1. Создайте локальное приложение в Bitrix24"
              : "Шаг 1. Установите приложение из Marketplace"}
          </h2>
          {mode === "local" ? (
            <div className="mt-1 space-y-2 text-sm text-slate-500">
              <p>
                В Bitrix24:{" "}
                <span className="font-medium text-slate-700">
                  Разработчикам → Другое → Локальное приложение
                </span>
                . Тип:{" "}
                <span className="font-medium text-slate-700">
                  «Серверное (использует только API)»
                </span>
                .
              </p>
              <p>
                Поле{" "}
                <span className="font-medium text-slate-700">
                  «Путь для первоначальной установки»
                </span>
                :
              </p>
              <code className="block rounded bg-slate-100 px-2 py-1.5 text-xs">
                {installUrl}
              </code>
              <p>
                Права доступа (scope):{" "}
                <code className="rounded bg-slate-100 px-1">imopenlines</code>,{" "}
                <code className="rounded bg-slate-100 px-1">im</code>,{" "}
                <code className="rounded bg-slate-100 px-1">user</code>,{" "}
                <code className="rounded bg-slate-100 px-1">event</code>,{" "}
                <code className="rounded bg-slate-100 px-1">crm</code>.
              </p>
              <p>
                После сохранения приложения скопируйте{" "}
                <code className="rounded bg-slate-100 px-1">client_id</code> и{" "}
                <code className="rounded bg-slate-100 px-1">client_secret</code>.
              </p>
            </div>
          ) : (
            <p className="mt-1 text-sm text-slate-500">
              Откройте на своём портале{" "}
              <span className="font-medium text-slate-700">
                Маркет → Поиск приложений
              </span>
              , найдите{" "}
              <span className="font-medium text-slate-700">«ai-message»</span> и
              нажмите «Установить».
            </p>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="text-base font-semibold tracking-tight">
            Шаг 2. Параметры подключения
          </h2>
          <div className="mt-4 space-y-4">
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
              label="Название (необязательно)"
              placeholder="Например: Главный портал"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />

            {mode === "local" && hasGlobalCreds && (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                  <div>
                    Глобальные client_id/secret уже сконфигурированы на сервере
                    (BITRIX24_APP_CLIENT_ID). Вводить ничего не нужно — мы
                    используем их автоматически.
                  </div>
                </div>
              </div>
            )}

            {mode === "local" && !hasGlobalCreds && (
              <>
                <Input
                  label="client_id"
                  placeholder="local.6a09ef866cbe83.16916660"
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  hint="Скопируйте из карточки локального приложения в Bitrix24."
                />
                <Input
                  label="client_secret"
                  type="password"
                  placeholder="••••••••"
                  value={clientSecret}
                  onChange={(e) => setClientSecret(e.target.value)}
                  hint="Хранится у нас на сервере, используется для обновления токенов."
                />
              </>
            )}

            {notInstalled && (
              <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <div>{notInstalled.message}</div>
                </div>
                <a
                  href={notInstalled.install_instructions_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm font-medium text-amber-900 underline"
                >
                  Открыть инструкцию <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}

            {apiError && !notInstalled && (
              <div className="flex items-start gap-2 rounded-md bg-rose-50 p-3 text-sm text-rose-700">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <div>{apiError.message}</div>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button
                onClick={handleSubmit}
                disabled={!domainValid || !credsValid || connect.isPending}
              >
                {connect.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Подключение…
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-4 w-4" /> Подключить
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
          <Plug className="h-4 w-4" />
          {mode === "local"
            ? "После подключения установите/переустановите ваше локальное приложение в Битриксе — токены автоматически прилетят к нам и привяжутся к интеграции."
            : "После подключения ai-message подтянет историю переписки и будет обновлять новые сообщения каждые 30 секунд."}
        </div>
      </div>
    </>
  );
}

function ModeCard({
  active,
  onClick,
  icon,
  title,
  description,
  soon,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  description: string;
  soon?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-start gap-3 rounded-md border p-4 text-left transition",
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
          {soon && (
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
              скоро
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
      </div>
    </button>
  );
}
