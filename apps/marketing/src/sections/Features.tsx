import { Section, SectionHeading } from "../components/Section";
import { FEATURES } from "../content/features";

export function Features() {
  return (
    <Section id="features" tone="muted">
      <SectionHeading
        eyebrow="Возможности"
        title="Всё для контроля клиентских коммуникаций"
        lead="Метрики, поиск, экспорт и реальное время — без надстроек и сторонних BI."
      />

      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map(({ icon: Icon, title, text, soon }) => (
          <div
            key={title}
            className="group relative rounded-2xl border border-slate-200 bg-white p-5 transition-all hover:border-brand-200 hover:shadow-lg hover:shadow-slate-900/5"
          >
            {soon && (
              <span className="absolute right-4 top-4 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                Скоро
              </span>
            )}
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
              <Icon className="h-5 w-5" />
            </div>
            <h3 className="mt-4 font-semibold text-slate-900">{title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-slate-600">
              {text}
            </p>
          </div>
        ))}
      </div>
    </Section>
  );
}
