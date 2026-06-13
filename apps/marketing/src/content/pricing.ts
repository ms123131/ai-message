export interface Plan {
  name: string;
  price: string;
  period?: string;
  tagline: string;
  features: string[];
  cta: { label: string; href: string; external?: boolean };
  featured?: boolean;
  note?: string;
}

import { APP, CONTACTS } from "../lib/links";

// Цены (SITE_PLAN §6) — упрощены до первой продажи. Pro — заглушка
// «свяжитесь с нами» до утверждения тарифа.
export const PLANS: Plan[] = [
  {
    name: "Старт",
    price: "Бесплатно",
    tagline: "На время beta",
    features: [
      "1 портал Bitrix24",
      "Все каналы Открытых линий",
      "Дашборд и Inbox",
      "История за 30 дней",
    ],
    cta: { label: "Начать бесплатно", href: APP.register },
    note: "Без карты",
  },
  {
    name: "Pro",
    price: "По запросу",
    period: "до утверждения тарифа",
    tagline: "Для растущих команд",
    features: [
      "Несколько порталов",
      "SLA-таргеты и алерты",
      "Экспорт CSV",
      "AI-инсайты (скоро)",
      "Приоритетная поддержка",
    ],
    cta: { label: "Связаться с нами", href: `mailto:${CONTACTS.salesEmail}`, external: true },
    featured: true,
  },
  {
    name: "Enterprise",
    price: "Индивидуально",
    tagline: "Для крупного бизнеса",
    features: [
      "Self-hosted в вашем контуре",
      "SSO",
      "SLA по договору",
      "Выделенная поддержка",
    ],
    cta: { label: "Запросить демо", href: `mailto:${CONTACTS.salesEmail}`, external: true },
  },
];
