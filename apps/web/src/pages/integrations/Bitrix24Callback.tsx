import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import {
  getConnection,
  saveConnection,
  type Bitrix24Connection,
} from "../../lib/connections";

const STATE_STORAGE_KEY = "ai-message:b24-pending-oauth";

type Status = "loading" | "success" | "error";

export function Bitrix24Callback() {
  const [params] = useSearchParams();
  const code = params.get("code");
  const state = params.get("state");
  const domain = params.get("domain");
  const memberId = params.get("member_id");
  const scope = params.get("scope");
  const error = params.get("error");

  const [status, setStatus] = useState<Status>("loading");
  const [message, setMessage] = useState<string>("");
  const [conn, setConn] = useState<Bitrix24Connection | null>(null);

  const expected = useMemo(() => {
    try {
      const raw = sessionStorage.getItem(STATE_STORAGE_KEY);
      return raw
        ? (JSON.parse(raw) as { state: string; id: string })
        : null;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (error) {
      setStatus("error");
      setMessage(`Bitrix24 вернул ошибку: ${error}`);
      return;
    }
    if (!code || !state) {
      setStatus("error");
      setMessage("Не получены параметры code и state в callback URL");
      return;
    }
    if (!expected || expected.state !== state) {
      setStatus("error");
      setMessage(
        "Параметр state не совпадает с ожидаемым. Возможна попытка CSRF — авторизация прервана.",
      );
      return;
    }

    const draft = getConnection(expected.id);
    if (!draft) {
      setStatus("error");
      setMessage("Черновик соединения не найден");
      return;
    }

    const updated: Bitrix24Connection = {
      ...draft,
      code,
      domain: domain ?? draft.domain,
      memberId: memberId ?? undefined,
      scope: scope ?? undefined,
      // status пока pending — реальный обмен code → access_token произойдёт на backend
      status: "pending",
    };
    saveConnection(updated);
    setConn(updated);
    sessionStorage.removeItem(STATE_STORAGE_KEY);
    setStatus("success");
  }, [code, state, domain, memberId, scope, error, expected]);

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
              Проверяем параметры авторизации…
            </div>
          )}

          {status === "success" && conn && (
            <>
              <div className="flex items-start gap-3 text-emerald-700">
                <CheckCircle2 className="mt-0.5 h-5 w-5" />
                <div>
                  <div className="font-medium">Код авторизации получен</div>
                  <p className="mt-1 text-sm text-emerald-700/80">
                    Параметры сохранены. Финальный обмен{" "}
                    <code className="rounded bg-emerald-100 px-1">code</code>{" "}
                    →{" "}
                    <code className="rounded bg-emerald-100 px-1">
                      access_token
                    </code>{" "}
                    выполнит backend (фаза 2).
                  </p>
                </div>
              </div>

              <dl className="mt-5 grid grid-cols-[140px_1fr] gap-y-2 text-sm">
                <dt className="text-slate-500">Портал</dt>
                <dd className="font-medium">{conn.domain}</dd>
                <dt className="text-slate-500">member_id</dt>
                <dd className="font-mono text-xs">{conn.memberId ?? "—"}</dd>
                <dt className="text-slate-500">scope</dt>
                <dd className="font-mono text-xs">{conn.scope ?? "—"}</dd>
                <dt className="text-slate-500">code</dt>
                <dd className="font-mono text-xs truncate">
                  {conn.code?.slice(0, 16)}…
                </dd>
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
