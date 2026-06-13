import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  CalendarClock,
  Filter,
  AlarmClockOff,
  Search,
  FileDown,
  Radio,
  Sparkles,
} from "lucide-react";

export interface Feature {
  icon: LucideIcon;
  title: string;
  text: string;
  /** Помечает функцию как ещё не выпущенную. */
  soon?: boolean;
}

// Возможности (SITE_PLAN §5). Порядок = приоритет показа.
export const FEATURES: Feature[] = [
  {
    icon: LayoutDashboard,
    title: "8 KPI на дашборде",
    text: "Объём диалогов, время ответа, SLA, тональность — с дельтами к прошлому периоду.",
  },
  {
    icon: CalendarClock,
    title: "Heatmap день × час",
    text: "Видно, когда клиенты пишут чаще всего, чтобы планировать смены операторов.",
  },
  {
    icon: Filter,
    title: "Воронка CRM",
    text: "Сделки по стадиям в привязке к переписке — от первого сообщения до оплаты.",
  },
  {
    icon: AlarmClockOff,
    title: "SLA-таргеты",
    text: "Задаёте порог ответа — нарушения подсвечиваются, никто не теряется.",
  },
  {
    icon: Search,
    title: "Полнотекстовый поиск",
    text: "Поиск по всем сообщениям всех каналов из одного окна.",
  },
  {
    icon: FileDown,
    title: "Экспорт CSV",
    text: "Выгрузка диалогов и метрик для отчётов и собственной аналитики.",
  },
  {
    icon: Radio,
    title: "Реальное время",
    text: "Сообщения приходят через Открытые линии Bitrix24 без задержек.",
  },
  {
    icon: Sparkles,
    title: "AI-инсайты",
    text: "Автоматические темы обращений и тональность диалогов.",
    soon: true,
  },
];
