import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  LineChart as LineChartIcon,
  Plug,
  Sparkles,
  Users,
  UserSquare2,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { DashboardFilterBar } from "../components/dashboard/DashboardFilters";
import { api, type DashboardFilters } from "../lib/api";
import { OverviewTab } from "./dashboard/OverviewTab";
import { ManagersTab } from "./dashboard/ManagersTab";
import { ContactsTab } from "./dashboard/ContactsTab";
import { AITab } from "./dashboard/AITab";
import { cn } from "../lib/cn";

type TabId = "overview" | "managers" | "contacts" | "ai";

const TABS: Array<{ id: TabId; label: string; icon: typeof LineChartIcon; soon?: boolean }> = [
  { id: "overview", label: "Обзор", icon: LineChartIcon },
  { id: "managers", label: "Менеджеры", icon: Users },
  { id: "contacts", label: "Контакты", icon: UserSquare2 },
  { id: "ai", label: "AI-аналитика", icon: Sparkles, soon: true },
];

export function DashboardPage() {
  const [tab, setTab] = useState<TabId>("overview");
  const [filters, setFilters] = useState<DashboardFilters>({ days: 14 });

  const integrationsQ = useQuery({
    queryKey: ["integrations"],
    queryFn: api.listIntegrations,
  });

  if (integrationsQ.isLoading) {
    return (
      <>
        <PageHeader title="Дашборд" />
        <div className="flex items-center justify-center p-16 text-sm text-slate-400">
          Загрузка…
        </div>
      </>
    );
  }

  if (integrationsQ.isSuccess && (integrationsQ.data ?? []).length === 0) {
    return (
      <>
        <PageHeader title="Дашборд" />
        <div className="flex items-center justify-center p-16">
          <div className="max-w-md text-center">
            <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-brand-50">
              <Plug className="h-6 w-6 text-brand-600" />
            </div>
            <h3 className="text-lg font-semibold text-slate-800">
              Нет данных для анализа
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              Подключите Bitrix24 — мы соберём метрики и покажем здесь.
            </p>
            <div className="mt-5">
              <Link to="/integrations/bitrix24/new">
                <Button>Подключить Bitrix24</Button>
              </Link>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Дашборд" />
      <div className="space-y-4 p-6">
        {/* Таб-бар */}
        <div className="flex items-center gap-1 border-b border-slate-200">
          {TABS.map(({ id, label, icon: Icon, soon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={cn(
                "relative -mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition",
                tab === id
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:text-slate-800",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
              {soon && (
                <span className="ml-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-slate-500">
                  скоро
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Фильтры скрыты на AI-табе — фильтровать там пока нечего */}
        {tab !== "ai" && (
          <DashboardFilterBar value={filters} onChange={setFilters} />
        )}

        {tab === "overview" && <OverviewTab filters={filters} />}
        {tab === "managers" && <ManagersTab filters={filters} />}
        {tab === "contacts" && <ContactsTab filters={filters} />}
        {tab === "ai" && <AITab />}
      </div>
    </>
  );
}
