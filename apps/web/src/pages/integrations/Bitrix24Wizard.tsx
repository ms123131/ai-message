import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Plug,
} from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { api, ApiError } from "../../lib/api";

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

export function Bitrix24Wizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [domain, setDomain] = useState("");
  const [label, setLabel] = useState("");

  const normalizedDomain = useMemo(() => normalizeDomain(domain), [domain]);
  const domainValid = isValidBitrixDomain(normalizedDomain);

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
          <h2 className="text-base font-semibold tracking-tight">
            Шаг 1. Установите приложение в Bitrix24
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Откройте на своём портале{" "}
            <span className="font-medium text-slate-700">
              Маркет → Поиск приложений
            </span>
            , найдите{" "}
            <span className="font-medium text-slate-700">«ai-message»</span> и
            нажмите «Установить». При установке Bitrix24 автоматически передаст
            нам нужные токены — вписывать client_id и secret больше не нужно.
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="text-base font-semibold tracking-tight">
            Шаг 2. Введите домен портала
          </h2>
          <p className="mb-4 mt-1 text-sm text-slate-500">
            Мы найдём установленное приложение и привяжем его к вашему
            рабочему пространству.
          </p>
          <div className="space-y-4">
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
                onClick={() =>
                  connect.mutate({
                    domain: normalizedDomain,
                    label: label.trim() || undefined,
                  })
                }
                disabled={!domainValid || connect.isPending}
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
          После подключения ai-message подтянет историю переписки и будет
          обновлять новые сообщения каждые 30 секунд.
        </div>
      </div>
    </>
  );
}
