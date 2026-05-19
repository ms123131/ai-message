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
      <div className="mx-auto max-w-xl space-y-4 p-8">
        <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
          {!hasGlobalCreds && (
            <div className="flex gap-2 text-xs">
              <button
                type="button"
                onClick={() => setMode("local")}
                className={cn(
                  "rounded-md px-2.5 py-1 transition",
                  mode === "local"
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-500 hover:bg-slate-100",
                )}
              >
                <KeyRound className="mr-1 inline h-3 w-3" />
                Локальное приложение
              </button>
              <button
                type="button"
                onClick={() => setMode("marketplace")}
                className={cn(
                  "rounded-md px-2.5 py-1 transition",
                  mode === "marketplace"
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-400 hover:bg-slate-100",
                )}
              >
                <Store className="mr-1 inline h-3 w-3" />
                Marketplace · скоро
              </button>
            </div>
          )}

          <Input
            label="Домен портала"
            placeholder="mycompany.bitrix24.ru"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            error={
              domain && !domainValid ? "Некорректный домен Bitrix24" : undefined
            }
          />
          <Input
            label="Название"
            placeholder="необязательно"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />

          {mode === "local" && !hasGlobalCreds && (
            <>
              <Input
                label="client_id"
                placeholder="local.6a09ef866cbe83.16916660"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
              />
              <Input
                label="client_secret"
                type="password"
                placeholder="••••••••"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
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

          <div className="flex justify-end pt-1">
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

        <details className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 [&_summary]:cursor-pointer [&_summary]:font-medium [&_summary]:text-slate-700 [&[open]_summary]:mb-3">
          <summary>Как создать локальное приложение в Bitrix24</summary>
          <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-500">
            <li>
              На портале:{" "}
              <span className="text-slate-700">
                Разработчикам → Другое → Локальное приложение
              </span>
              . Тип — «Серверное».
            </li>
            <li>
              Путь для первоначальной установки:
              <code className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                {installUrl}
              </code>
            </li>
            <li>
              Права:{" "}
              <code className="rounded bg-slate-100 px-1 text-xs">imopenlines</code>,{" "}
              <code className="rounded bg-slate-100 px-1 text-xs">im</code>,{" "}
              <code className="rounded bg-slate-100 px-1 text-xs">user</code>,{" "}
              <code className="rounded bg-slate-100 px-1 text-xs">event</code>,{" "}
              <code className="rounded bg-slate-100 px-1 text-xs">crm</code>
            </li>
            <li>
              Сохраните приложение — токены прилетят автоматически, статус
              станет «подключено».
            </li>
          </ol>
        </details>
      </div>
    </>
  );
}

