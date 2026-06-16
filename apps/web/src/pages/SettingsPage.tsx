import { useSearchParams } from "react-router-dom";
import { Building2, CreditCard, UserCog } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Tabs, type TabItem } from "../components/ui/Tabs";
import { CompanyTab } from "./settings/CompanyTab";
import { BillingTab } from "./settings/BillingTab";
import { ProfileTab } from "./settings/ProfileTab";

type TabId = "company" | "billing" | "profile";

const TABS: ReadonlyArray<TabItem<TabId>> = [
  { id: "company", label: "Компания", icon: Building2 },
  { id: "billing", label: "Оплата", icon: CreditCard },
  { id: "profile", label: "Информация", icon: UserCog },
];

const TAB_IDS: readonly TabId[] = ["company", "billing", "profile"];

function isTab(v: string | null): v is TabId {
  return v !== null && (TAB_IDS as readonly string[]).includes(v);
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlTab = searchParams.get("tab");
  const tab: TabId = isTab(urlTab) ? urlTab : "company";

  function setTab(next: TabId) {
    const params = new URLSearchParams(searchParams);
    if (next === "company") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params, { replace: true });
  }

  return (
    <>
      <PageHeader title="Настройки" description="Организация, тариф и профиль" />
      <div className="space-y-6 p-8">
        <Tabs tabs={TABS} value={tab} onChange={setTab} />
        {tab === "company" && <CompanyTab />}
        {tab === "billing" && <BillingTab />}
        {tab === "profile" && <ProfileTab />}
      </div>
    </>
  );
}
