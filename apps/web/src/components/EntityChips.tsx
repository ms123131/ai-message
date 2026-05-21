import { Mail, MapPin, Package, Phone, Building2, User, Banknote, Link as LinkIcon } from "lucide-react";

import type { MessageEntities } from "../lib/api";

type ChipDef = {
  key: keyof MessageEntities;
  label: string;
  icon: typeof Phone;
  className: string;
  href?: (v: string) => string;
};

const DEFS: ChipDef[] = [
  {
    key: "phone",
    label: "телефон",
    icon: Phone,
    className: "bg-emerald-50 text-emerald-700 hover:bg-emerald-100",
    href: (v) => `tel:${v}`,
  },
  {
    key: "email",
    label: "email",
    icon: Mail,
    className: "bg-sky-50 text-sky-700 hover:bg-sky-100",
    href: (v) => `mailto:${v}`,
  },
  {
    key: "url",
    label: "ссылка",
    icon: LinkIcon,
    className: "bg-indigo-50 text-indigo-700 hover:bg-indigo-100",
    href: (v) => (v.startsWith("http") ? v : `https://${v}`),
  },
  {
    key: "tracking",
    label: "трек",
    icon: Package,
    className: "bg-amber-50 text-amber-700 hover:bg-amber-100",
  },
  {
    key: "person",
    label: "имя",
    icon: User,
    className: "bg-violet-50 text-violet-700 hover:bg-violet-100",
  },
  {
    key: "location",
    label: "город",
    icon: MapPin,
    className: "bg-rose-50 text-rose-700 hover:bg-rose-100",
  },
  {
    key: "organization",
    label: "организация",
    icon: Building2,
    className: "bg-slate-100 text-slate-700 hover:bg-slate-200",
  },
];

const CURRENCY_SIGN: Record<string, string> = {
  RUB: "₽",
  USD: "$",
  EUR: "€",
  KZT: "₸",
  UAH: "₴",
};

function formatMoney(amount: number, currency: string): string {
  const sign = CURRENCY_SIGN[currency] || currency;
  const formatted = new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 2,
  }).format(amount);
  return `${formatted} ${sign}`;
}

export function EntityChips({ entities }: { entities: MessageEntities | null | undefined }) {
  if (!entities || Object.keys(entities).length === 0) return null;

  const chips: JSX.Element[] = [];

  for (const def of DEFS) {
    const values = entities[def.key] as string[] | undefined;
    if (!values || values.length === 0) continue;
    const Icon = def.icon;
    for (const value of values) {
      const content = (
        <span className="inline-flex items-center gap-1">
          <Icon className="h-3 w-3" />
          {value}
        </span>
      );
      const className = `inline-flex items-center rounded px-1.5 py-0.5 text-[11px] transition ${def.className}`;
      chips.push(
        def.href ? (
          <a
            key={`${def.key}-${value}`}
            href={def.href(value)}
            target={def.key === "url" ? "_blank" : undefined}
            rel="noreferrer"
            className={className}
            title={def.label}
          >
            {content}
          </a>
        ) : (
          <span
            key={`${def.key}-${value}`}
            className={className}
            title={def.label}
          >
            {content}
          </span>
        ),
      );
    }
  }

  if (entities.money && entities.money.length > 0) {
    for (const m of entities.money) {
      chips.push(
        <span
          key={`money-${m.amount}-${m.currency}`}
          className="inline-flex items-center gap-1 rounded bg-green-50 px-1.5 py-0.5 text-[11px] text-green-700"
          title={`Сумма (распознано из: ${m.raw})`}
        >
          <Banknote className="h-3 w-3" />
          {formatMoney(m.amount, m.currency)}
        </span>,
      );
    }
  }

  if (chips.length === 0) return null;
  return <div className="mt-1 flex flex-wrap gap-1">{chips}</div>;
}
