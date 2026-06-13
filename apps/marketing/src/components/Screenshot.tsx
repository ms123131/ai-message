import type { ReactNode } from "react";
import { cn } from "../lib/cn";

// Браузерная рамка вокруг любого «экрана продукта». Пока реальных
// скриншотов нет — внутрь кладём CSS-мокапы (см. mocks ниже). Когда снимем
// настоящие .webp на тестовых данных, передаём <Screenshot src=... />.
export function BrowserFrame({
  children,
  className,
  label = "app.77ais.ru/dashboard",
}: {
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10 ring-1 ring-slate-900/5",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/80 px-4 py-2.5">
        <span className="h-3 w-3 rounded-full bg-slate-300" />
        <span className="h-3 w-3 rounded-full bg-slate-300" />
        <span className="h-3 w-3 rounded-full bg-slate-300" />
        <div className="ml-3 flex-1 rounded-md bg-white px-3 py-1 text-xs text-slate-400 ring-1 ring-inset ring-slate-200">
          {label}
        </div>
      </div>
      <div className="bg-slate-50">{children}</div>
    </div>
  );
}

// Если когда-нибудь появится реальный растровый скриншот — этот компонент
// отдаст его с ленивой загрузкой. Заглушка-мокап живёт отдельно (DashboardMock).
export function Screenshot({
  src,
  alt,
  className,
}: {
  src: string;
  alt: string;
  className?: string;
}) {
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={cn("block w-full", className)}
    />
  );
}

const bar = (h: string, w: string, c = "bg-slate-200") =>
  cn("rounded-full", h, w, c);

// Мокап дашборда: 4 KPI с дельтами + столбчатая динамика. Цифры выдуманные,
// но правдоподобные — не «лорем».
export function DashboardMock() {
  const kpis = [
    { label: "Диалогов", value: "1 248", delta: "+12%", up: true },
    { label: "Ср. ответ", value: "4м 12с", delta: "−18%", up: true },
    { label: "SLA-нарушений", value: "23", delta: "+4", up: false },
    { label: "Позитив", value: "78%", delta: "+6 п.п.", up: true },
  ];
  const heights = [38, 52, 44, 61, 70, 48, 80, 66, 90, 72, 84, 58];
  return (
    <div className="p-5 sm:p-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {kpis.map((k) => (
          <div
            key={k.label}
            className="rounded-lg border border-slate-200 bg-white p-3"
          >
            <div className="text-[11px] text-slate-400">{k.label}</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">
              {k.value}
            </div>
            <div
              className={cn(
                "mt-0.5 text-[11px] font-medium",
                k.up ? "text-emerald-600" : "text-rose-500",
              )}
            >
              {k.delta}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className={bar("h-2.5", "w-28", "bg-slate-300")} />
          <div className={bar("h-2.5", "w-16")} />
        </div>
        <div className="flex h-28 items-end gap-1.5">
          {heights.map((h, i) => (
            <div
              key={i}
              className="flex-1 rounded-t bg-gradient-to-t from-brand-500 to-brand-400"
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// Мокап Inbox: список диалогов с каналами и статусами.
export function InboxMock() {
  const rows = [
    { name: "Анна Кузнецова", ch: "WA", txt: "Подскажите по доставке…", t: "2м", c: "bg-emerald-500" },
    { name: "ООО «Север»", ch: "TG", txt: "Счёт получили, спасибо", t: "14м", c: "bg-sky-500" },
    { name: "Игорь П.", ch: "ВК", txt: "А есть рассрочка?", t: "31м", c: "bg-blue-600" },
    { name: "Авито / 4412", ch: "AV", txt: "Ещё актуально?", t: "1ч", c: "bg-green-600" },
    { name: "Мария Л.", ch: "WA", txt: "Оплатила, жду", t: "2ч", c: "bg-emerald-500" },
  ];
  return (
    <div className="p-5 sm:p-6">
      <div className="space-y-2">
        {rows.map((r) => (
          <div
            key={r.name}
            className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5"
          >
            <span
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[10px] font-bold text-white",
                r.c,
              )}
            >
              {r.ch}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium text-slate-900">
                {r.name}
              </div>
              <div className="truncate text-[11px] text-slate-400">{r.txt}</div>
            </div>
            <span className="shrink-0 text-[10px] text-slate-400">{r.t}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Мокап heatmap: активность день недели × час.
export function HeatmapMock() {
  const days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  // Псевдослучайные, но детерминированные значения интенсивности.
  const cell = (d: number, h: number) => ((d * 7 + h * 13) % 5) / 4;
  return (
    <div className="p-5 sm:p-6">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="space-y-1.5">
          {days.map((day, d) => (
            <div key={day} className="flex items-center gap-2">
              <span className="w-6 text-[10px] text-slate-400">{day}</span>
              <div className="flex flex-1 gap-1">
                {Array.from({ length: 16 }).map((_, h) => {
                  const v = cell(d, h);
                  return (
                    <div
                      key={h}
                      className="h-3.5 flex-1 rounded-sm"
                      style={{
                        backgroundColor: `rgba(39, 72, 219, ${0.08 + v * 0.85})`,
                      }}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Мокап воронки CRM.
export function FunnelMock() {
  const stages = [
    { label: "Новые", w: 100, v: "1 248" },
    { label: "В работе", w: 74, v: "923" },
    { label: "Счёт выставлен", w: 48, v: "601" },
    { label: "Оплачено", w: 29, v: "362" },
  ];
  return (
    <div className="p-5 sm:p-6">
      <div className="space-y-2.5 rounded-lg border border-slate-200 bg-white p-4">
        {stages.map((s, i) => (
          <div key={s.label}>
            <div className="mb-1 flex justify-between text-[11px]">
              <span className="text-slate-500">{s.label}</span>
              <span className="font-medium text-slate-700">{s.v}</span>
            </div>
            <div className="h-5 rounded-md bg-slate-100">
              <div
                className="h-5 rounded-md bg-gradient-to-r from-brand-600 to-brand-400"
                style={{ width: `${s.w}%`, opacity: 1 - i * 0.12 }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
