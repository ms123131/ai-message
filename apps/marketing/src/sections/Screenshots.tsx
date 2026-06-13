import { useState } from "react";
import { Section, SectionHeading } from "../components/Section";
import {
  BrowserFrame,
  DashboardMock,
  InboxMock,
  HeatmapMock,
  FunnelMock,
} from "../components/Screenshot";
import { cn } from "../lib/cn";

// Скриншоты продукта (SITE_PLAN §4) — табами, чтобы не раздувать высоту.
const TABS = [
  { id: "dashboard", label: "Дашборд", url: "app.77ais.ru/dashboard", Mock: DashboardMock },
  { id: "inbox", label: "Inbox", url: "app.77ais.ru/inbox", Mock: InboxMock },
  { id: "heatmap", label: "Heatmap", url: "app.77ais.ru/dashboard", Mock: HeatmapMock },
  { id: "funnel", label: "Воронка", url: "app.77ais.ru/dashboard", Mock: FunnelMock },
] as const;

export function Screenshots() {
  const [active, setActive] = useState<(typeof TABS)[number]["id"]>("dashboard");
  const current = TABS.find((t) => t.id === active)!;
  const Mock = current.Mock;

  return (
    <Section id="screenshots">
      <SectionHeading
        eyebrow="Интерфейс"
        title="Всё, что нужно, — на одном экране"
        lead="Дашборд, Inbox, тепловая карта и воронка. Данные на примерах — для демонстрации."
      />

      <div className="mt-10 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActive(t.id)}
            className={cn(
              "rounded-full px-4 py-2 text-sm font-medium transition-colors",
              active === t.id
                ? "bg-brand-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6 max-w-4xl">
        <BrowserFrame label={current.url}>
          <Mock />
        </BrowserFrame>
      </div>
    </Section>
  );
}
