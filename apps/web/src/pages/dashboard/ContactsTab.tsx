import { useQuery } from "@tanstack/react-query";
import { Download, Loader2, UserSquare2 } from "lucide-react";
import type { DashboardFilters } from "../../lib/api";
import { api, downloadCSV } from "../../lib/api";
import { Button } from "../../components/ui/Button";
import { fmtDateTime, fmtNumber } from "../../components/dashboard/format";

function csvParams(f: DashboardFilters): string {
  const usp = new URLSearchParams();
  if (f.days) usp.set("days", String(f.days));
  if (f.integration_id) usp.set("integration_id", f.integration_id);
  if (f.channel) usp.set("channel", f.channel);
  if (f.operator_id) usp.set("operator_id", f.operator_id);
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export function ContactsTab({ filters }: { filters: DashboardFilters }) {
  const q = useQuery({
    queryKey: ["dash-top-contacts", filters],
    queryFn: () => api.getDashboardTopContacts({ ...filters, limit: 30 }),
    refetchInterval: 60_000,
  });

  if (q.isLoading) {
    return (
      <div className="flex items-center justify-center p-16 text-slate-400">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Загрузка…
      </div>
    );
  }

  const items = q.data?.items ?? [];
  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-12 text-center">
        <UserSquare2 className="mx-auto mb-3 h-10 w-10 text-slate-300" />
        <div className="text-sm font-medium text-slate-700">
          Контакты не найдены
        </div>
        <p className="mt-1 text-xs text-slate-500">
          За выбранный период не было обращений от внешних клиентов.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <div className="text-sm font-medium text-slate-700">
          Топ контактов по объёму сообщений
        </div>
        <Button
          variant="secondary"
          onClick={() =>
            downloadCSV(
              `/api/v1/dashboard/top-contacts.csv${csvParams(filters)}`,
              `contacts-${filters.days ?? 30}d.csv`,
            )
          }
        >
          <Download className="h-4 w-4" /> Скачать CSV
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-5 py-3 text-left font-medium">#</th>
              <th className="px-5 py-3 text-left font-medium">Контакт</th>
              <th className="px-5 py-3 text-right font-medium">Диалогов</th>
              <th className="px-5 py-3 text-right font-medium">Сообщений</th>
              <th className="px-5 py-3 text-right font-medium">
                Последняя активность
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((c, i) => (
              <tr key={c.contact_external_id ?? i} className="hover:bg-slate-50">
                <td className="px-5 py-3 text-slate-400">{i + 1}</td>
                <td className="px-5 py-3">
                  <div className="font-medium text-slate-800">
                    {c.contact_name || "Без имени"}
                  </div>
                  {c.contact_external_id && (
                    <div className="text-xs text-slate-400">
                      id: {c.contact_external_id}
                    </div>
                  )}
                </td>
                <td className="px-5 py-3 text-right tabular-nums">
                  {c.conversations > 1 ? (
                    <span className="inline-flex items-center rounded bg-violet-50 px-1.5 py-0.5 text-xs font-medium text-violet-700">
                      {c.conversations}
                    </span>
                  ) : (
                    fmtNumber(c.conversations)
                  )}
                </td>
                <td className="px-5 py-3 text-right tabular-nums">
                  {fmtNumber(c.messages)}
                </td>
                <td className="px-5 py-3 text-right text-slate-500">
                  {c.last_message_at ? fmtDateTime(c.last_message_at) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
