import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { api, ApiError, type Integration } from "../../lib/api";

const PENDING_KEY = "ai-message:b24-pending-oauth";

type Status = "loading" | "success" | "error";

export function Bitrix24Callback() {
  const [params] = useSearchParams();
  const code = params.get("code");
  const state = params.get("state");
  const domain = params.get("domain");
  const memberId = params.get("member_id");
  const scope = params.get("scope");
  const oauthError = params.get("error");

  const [status, setStatus] = useState<Status>("loading");
  const [message, setMessage] = useState<string>("");
  const [conn, setConn] = useState<Integration | null>(null);

  const pending = useMemo(() => {
    try {
      const raw = sessionStorage.getItem(PENDING_KEY);
      return raw ? (JSON.parse(raw) as { id: string }) : null;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (oauthError) {
        setStatus("error");
        setMessage(`Bitrix24 вернул ошибку: ${oauthError}`);
        return;
      }
      if (!code || !state) {
        setStatus("error");
        setMessage("Не получены параметры code и state");
        return;
      }
      const integrationId = state.split(".")[0];
      if (!integrationId || (pending && pending.id !== integrationId)) {
        setStatus("error");
        setMessage("Параметр state некорректный — авторизация прервана");
        return;
      }
      try {
        const result = await api.exchangeBitrix24Code({
          integration_id: integrationId,
          code,
          domain: domain ?? "",
          member_id: memberId,
          scope,
        });
        if (cancelled) return;
        sessionStorage.removeItem(PENDING_KEY);
        setConn(result);
        setStatus("success");
      } catch (e) {
        if (cancelled) return;
        setStatus("error");
        setMessage(
          e instanceof ApiError
            ? `Ошибка обмена: ${e.message}`
            : "Неизвестная ошибка обмена кода на токен",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, state, domain, memberId, scope, oauthError, pending]);

  return (
    <>
      <PageHeader
        title="Bitrix24: авторизация"
        description="Обработка ответа от портала"
      />
      <div className="mx-auto max-w-2xl p-8">
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          {status === "loading" && (
            <div className="flex items-center gap-3 text-slate-600">
              <Loader2 className="h-5 w-5 animate-spin" />
              Обмениваем код на access_token…
            </div>
          )}

          {status === "success" && conn && (
            <>
              <div className="flex items-start gap-3 text-emerald-700">
                <CheckCircle2 className="mt-0.5 h-5 w-5" />
                <div>
                  <div className="font-medium">Подключение активировано</div>
                  <p className="mt-1 text-sm text-emerald-700/80">
                    Получены access_token и refresh_token. Подключение в
                    статусе «connected».
                  </p>
                </div>
              </div>

              <dl className="mt-5 grid grid-cols-[140px_1fr] gap-y-2 text-sm">
                <dt className="text-slate-500">Портал</dt>
                <dd className="font-medium">{conn.domain}</dd>
                <dt className="text-slate-500">member_id</dt>
                <dd className="font-mono text-xs">{conn.member_id ?? "—"}</dd>
                <dt className="text-slate-500">scope</dt>
                <dd className="font-mono text-xs">{conn.scope ?? "—"}</dd>
              </dl>

              <div className="mt-6 flex justify-end">
                <Link
                  to="/integrations"
                  className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
                >
                  К интеграциям <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </>
          )}

          {status === "error" && (
            <>
              <div className="flex items-start gap-3 text-rose-700">
                <AlertTriangle className="mt-0.5 h-5 w-5" />
                <div>
                  <div className="font-medium">Не удалось завершить авторизацию</div>
                  <p className="mt-1 text-sm text-rose-700/80">{message}</p>
                </div>
              </div>
              <div className="mt-6 flex justify-end">
                <Link
                  to="/integrations/bitrix24/new"
                  className="inline-flex items-center gap-2 rounded-md bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
                >
                  Попробовать снова
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
