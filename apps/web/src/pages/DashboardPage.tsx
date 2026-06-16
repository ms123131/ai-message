import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  LineChart as LineChartIcon,
  Plug,
  Sparkles,
  Users,
  UserSquare2,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { Tabs, type TabItem } from "../components/ui/Tabs";
import { DashboardFilterBar } from "../components/dashboard/DashboardFilters";
import { api, type DashboardFilters } from "../lib/api";
import { OverviewTab } from "./dashboard/OverviewTab";
import { ManagersTab } from "./dashboard/ManagersTab";
import { ContactsTab } from "./dashboard/ContactsTab";
import { AITab } from "./dashboard/AITab";

type TabId = "overview" | "managers" | "contacts" | "ai";

const TABS: ReadonlyArray<TabItem<TabId>> = [
  { id: "overview", label: "Обзор", icon: LineChartIcon },
  { id: "managers", label: "Менеджеры", icon: Users },
  { id: "contacts", label: "Контакты", icon: UserSquare2 },
  { id: "ai", label: "AI-аналитика", icon: Sparkles },
];

const TAB_IDS: readonly TabId[] = ["overview", "managers", "contacts", "ai"];

function isTab(v: string | null): v is TabId {
  return v !== null && (TAB_IDS as readonly string[]).includes(v);
}

export function DashboardPage() {
  // Активный таб храним в URL — переживает refresh и работает с history back.
  const [searchParams, setSearchParams] = useSearchParams();
  const urlTab = searchParams.get("tab");
  const tab: TabId = isTab(urlTab) ? urlTab : "overview";
  function setTab(next: TabId) {
    const params = new URLSearchParams(searchParams);
    if (next === "overview") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params, { replace: true });
  }
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
        <Tabs tabs={TABS} value={tab} onChange={setTab} />

        <DashboardFilterBar value={filters} onChange={setFilters} />

        {tab === "overview" && <OverviewTab filters={filters} />}
        {tab === "managers" && <ManagersTab filters={filters} />}
        {tab === "contacts" && <ContactsTab filters={filters} />}
        {tab === "ai" && <AITab filters={filters} />}
      </div>
    </>
  );
}
