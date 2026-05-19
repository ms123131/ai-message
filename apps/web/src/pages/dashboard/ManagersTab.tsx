import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import { Download, Loader2, UserCircle2 } from "lucide-react";
import type { DashboardFilters, ManagerRow } from "../../lib/api";
import { api, downloadCSV } from "../../lib/api";
import { Button } from "../../components/ui/Button";
import { fmtDuration, fmtNumber } from "../../components/dashboard/format";
import { buildInboxLink } from "../../components/dashboard/inboxLink";

function csvParams(f: DashboardFilters): string {
  const usp = new URLSearchParams();
  if (f.days) usp.set("days", String(f.days));
  if (f.integration_id) usp.set("integration_id", f.integration_id);
  if (f.channel) usp.set("channel", f.channel);
  if (f.operator_id) usp.set("operator_id", f.operator_id);
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export function ManagersTab({ filters }: { filters: DashboardFilters }) {
  const q = useQuery({
    queryKey: ["dash-by-manager", filters],
    queryFn: () => api.getDashboardByManager({ ...filters, limit: 50 }),
    refetchInterval: 60_000,
  });

  if (q.isLoading) {
    return (
      <div className="flex items-center justify-center p-16 text-slate-400">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загрузка операторов…
      </div>
    );
  }

  const rows = q.data?.rows ?? [];
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-12 text-center">
        <UserCircle2 className="mx-auto mb-3 h-10 w-10 text-slate-300" />
        <div className="text-sm font-medium text-slate-700">
          Операторы не назначены
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Когда в диалогах появятся закреплённые операторы Bitrix24 — мы
          посчитаем их нагрузку и время ответа здесь.
        </p>
      </div>
    );
  }

  const chartData = rows.slice(0, 10).map((r) => ({
    name: shortName(r),
    frt: r.frt_median_sec ?? 0,
    diag: r.conversations,
  }));

  return (
    <div className="space-y-6">
      {/* Гистограмма медианного времени первого ответа по топ-10 */}
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <div className="mb-2 text-sm font-medium text-slate-700">
          Время первого ответа (медиана)
        </div>
        <div className="mb-4 text-xs text-slate-400">
          Чем ниже — тем быстрее оператор берёт диалог в работу. Топ-10 по числу диалогов.
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              type="number"
              stroke="#94a3b8"
              fontSize={11}
              tickFormatter={(v) => fmtDuration(v)}
            />
            <YAxis
              type="category"
              dataKey="name"
              stroke="#94a3b8"
              fontSize={11}
              width={140}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: "1px solid #e2e8f0",
              }}
              formatter={(v: number, key: string) =>
                key === "frt"
                  ? [fmtDuration(v), "Время ответа (медиана)"]
                  : [v, "Диалогов"]
              }
            />
            <Bar dataKey="frt" fill="#3a66f5" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Таблица операторов */}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
          <div className="text-sm font-medium text-slate-700">
            Все операторы за период
          </div>
          <Button
            variant="secondary"
            onClick={() =>
              downloadCSV(
                `/api/v1/dashboard/by-manager.csv${csvParams(filters)}`,
                `operators-${filters.days ?? 14}d.csv`,
              )
            }
          >
            <Download className="h-4 w-4" /> Скачать CSV
          </Button>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Оператор</th>
              <th className="px-4 py-3 text-right font-medium">Диалогов</th>
              <th className="px-4 py-3 text-right font-medium">Открыто</th>
              <th className="px-4 py-3 text-right font-medium">
                Сообщений отправил
              </th>
              <th className="px-4 py-3 text-right font-medium">
                Время ответа (медиана)
              </th>
              <th className="px-4 py-3 text-right font-medium">
                Самые медленные (90%)
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.operator_id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    to={buildInboxLink(filters, { operator_id: r.operator_id })}
                    className="flex items-center gap-2.5 hover:text-brand-700"
                  >
                    <Avatar row={r} />
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-800">
                        {r.full_name || `#${r.operator_id}`}
                      </div>
                      {r.work_position && (
                        <div className="truncate text-xs text-slate-400">
                          {r.work_position}
                        </div>
                      )}
                    </div>
                  </Link>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  <Link
                    to={buildInboxLink(filters, { operator_id: r.operator_id })}
                    className="hover:underline"
                  >
                    {fmtNumber(r.conversations)}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {r.open_conversations > 0 ? (
                    <Link
                      to={buildInboxLink(filters, {
                        operator_id: r.operator_id,
                        status: "open",
                      })}
                      className="inline-flex items-center rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-700 hover:bg-amber-100"
                    >
                      {r.open_conversations}
                    </Link>
                  ) : (
                    <span className="text-slate-300">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtNumber(r.messages_sent)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtDuration(r.frt_median_sec)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {fmtDuration(r.frt_p90_sec)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Avatar({ row }: { row: ManagerRow }) {
  if (row.avatar_url) {
    return (
      <img
        src={row.avatar_url}
        alt=""
        className="h-8 w-8 rounded-full object-cover"
        loading="lazy"
      />
    );
  }
  const initials = (row.full_name || row.operator_id)
    .split(/\s+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-medium text-brand-700">
      {initials || "?"}
    </div>
  );
}

function shortName(r: ManagerRow): string {
  const n = r.full_name || `#${r.operator_id}`;
  // Иван Иванов → И. Иванов
  const parts = n.split(/\s+/);
  if (parts.length < 2) return n;
  return `${parts[0][0]}. ${parts.slice(1).join(" ")}`;
}
