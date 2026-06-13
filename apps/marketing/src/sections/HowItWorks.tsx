import { Section, SectionHeading } from "../components/Section";
import { CTAButton } from "../components/CTAButton";
import { APP } from "../lib/links";
import { ArrowRight } from "lucide-react";

// Как работает (SITE_PLAN §3) — 3 шага.
const STEPS = [
  {
    n: "01",
    title: "Ставите приложение",
    text: "Находите ai-message в Bitrix24 Маркетплейс и устанавливаете на свой портал в один клик.",
  },
  {
    n: "02",
    title: "Указываете домен",
    text: "Возвращаетесь в наш кабинет и подтверждаете подключение портала. Никаких выгрузок вручную.",
  },
  {
    n: "03",
    title: "Получаете дашборд",
    text: "Через 5 минут готов дашборд и Inbox — с историей переписки за последние 30 дней.",
  },
];

export function HowItWorks() {
  return (
    <Section id="how" tone="muted">
      <SectionHeading
        eyebrow="Как это работает"
        title="От установки до дашборда — 5 минут"
        lead="Без интеграторов и технических настроек. Всё внутри Bitrix24."
      />

      <div className="mt-12 grid gap-5 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <div key={s.n} className="relative">
            <div className="rounded-2xl border border-slate-200 bg-white p-6">
              <span className="text-sm font-bold tracking-widest text-brand-600">
                {s.n}
              </span>
              <h3 className="mt-3 text-lg font-semibold text-slate-900">
                {s.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                {s.text}
              </p>
            </div>
            {/* Стрелка-связка между шагами на десктопе. */}
            {i < STEPS.length - 1 && (
              <ArrowRight className="absolute -right-4 top-1/2 hidden h-6 w-6 -translate-y-1/2 text-slate-300 md:block" />
            )}
          </div>
        ))}
      </div>

      <div className="mt-10">
        <CTAButton href={APP.bitrix24New} variant="primary" size="lg">
          Подключить за 5 минут
          <ArrowRight className="h-4 w-4" />
        </CTAButton>
      </div>
    </Section>
  );
}
