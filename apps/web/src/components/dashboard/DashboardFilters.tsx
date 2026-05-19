import { useQuery } from "@tanstack/react-query";
import { api, type ConversationChannel, type DashboardFilters } from "../../lib/api";
import { cn } from "../../lib/cn";

const RANGE_OPTIONS = [
  { value: 1, label: "Сегодня" },
  { value: 7, label: "7 дней" },
  { value: 30, label: "30 дней" },
  { value: 90, label: "90 дней" },
];

const CHANNEL_LABELS: Record<ConversationChannel, string> = {
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  vk: "ВКонтакте",
  instagram: "Instagram",
  facebook: "Facebook",
  livechat: "Виджет сайта",
  email: "Email",
  other: "Другое",
};

const CHANNELS: ConversationChannel[] = [
  "whatsapp",
  "telegram",
  "vk",
  "livechat",
  "email",
  "other",
];

export type FilterBarProps = {
  value: DashboardFilters;
  onChange: (next: DashboardFilters) => void;
};

export function DashboardFilterBar({ value, onChange }: FilterBarProps) {
  const integrationsQ = useQuery({
    queryKey: ["integrations"],
    queryFn: api.listIntegrations,
  });
  const operatorsQ = useQuery({
    queryKey: ["portal-users", value.integration_id ?? null],
    queryFn: () =>
      api.getPortalUsers({ integration_id: value.integration_id }),
    enabled: integrationsQ.isSuccess && (integrationsQ.data ?? []).length > 0,
  });

  function set<K extends keyof DashboardFilters>(
    key: K,
    next: DashboardFilters[K],
  ) {
    onChange({ ...value, [key]: next || undefined });
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 text-sm">
      {/* Период */}
      <div className="flex items-center gap-1">
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => set("days", opt.value)}
            className={cn(
              "rounded-md px-2.5 py-1 transition",
              (value.days ?? 14) === opt.value
                ? "bg-brand-50 text-brand-700"
                : "text-slate-500 hover:bg-slate-100",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="h-5 w-px bg-slate-200" />

      {/* Интеграция */}
      <Select
        value={value.integration_id ?? ""}
        onChange={(v) => set("integration_id", v || undefined)}
        ariaLabel="Интеграция"
        options={[
          { value: "", label: "Все порталы" },
          ...(integrationsQ.data ?? []).map((i) => ({
            value: i.id,
            label: i.label || i.domain,
          })),
        ]}
      />

      {/* Канал */}
      <Select
        value={value.channel ?? ""}
        onChange={(v) =>
          set("channel", (v || undefined) as ConversationChannel | undefined)
        }
        ariaLabel="Канал"
        options={[
          { value: "", label: "Все каналы" },
          ...CHANNELS.map((c) => ({ value: c, label: CHANNEL_LABELS[c] })),
        ]}
      />

      {/* Оператор */}
      <Select
        value={value.operator_id ?? ""}
        onChange={(v) => set("operator_id", v || undefined)}
        ariaLabel="Оператор"
        disabled={(operatorsQ.data ?? []).length === 0}
        options={[
          { value: "", label: "Все операторы" },
          ...(operatorsQ.data ?? []).map((u) => ({
            value: u.external_id,
            label: u.full_name || u.email || `#${u.external_id}`,
          })),
        ]}
      />
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
  ariaLabel,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
  ariaLabel: string;
  disabled?: boolean;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "rounded-md border border-slate-200 bg-white px-2 py-1 text-sm",
        "focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100",
        "disabled:cursor-not-allowed disabled:opacity-50",
      )}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
