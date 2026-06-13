import { EyeOff, UserX, HelpCircle, ArrowRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Section, SectionHeading } from "../components/Section";

interface Problem {
  icon: LucideIcon;
  pain: string;
  solution: string;
}

// Боли и решения (SITE_PLAN §2).
const PROBLEMS: Problem[] = [
  {
    icon: EyeOff,
    pain: "Не видно общую картину",
    solution: "Один дашборд по всем каналам сразу — без переключения между приложениями.",
  },
  {
    icon: UserX,
    pain: "Менеджер пропустил клиента",
    solution: "Нарушения SLA подсвечены: видно, где не ответили вовремя, и кто именно.",
  },
  {
    icon: HelpCircle,
    pain: "Непонятно, о чём пишут чаще",
    solution: "AI-темы и тональность диалогов показывают, что волнует клиентов.",
  },
];

export function Problems() {
  return (
    <Section id="problems">
      <SectionHeading
        eyebrow="Зачем это нужно"
        title="Переписка есть — а управлять ей нечем"
        lead="Каналов всё больше, а сводной картины нет. Вот что мы закрываем."
      />
      <div className="mt-12 grid gap-5 md:grid-cols-3">
        {PROBLEMS.map(({ icon: Icon, pain, solution }) => (
          <div
            key={pain}
            className="group rounded-2xl border border-slate-200 bg-white p-6 transition-all hover:border-brand-200 hover:shadow-lg hover:shadow-slate-900/5"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500 transition-colors group-hover:bg-brand-50 group-hover:text-brand-600">
              <Icon className="h-5 w-5" />
            </div>
            <h3 className="mt-4 font-semibold text-slate-900">«{pain}»</h3>
            <div className="mt-3 flex items-start gap-2 text-sm leading-relaxed text-slate-600">
              <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
              <span>{solution}</span>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}
