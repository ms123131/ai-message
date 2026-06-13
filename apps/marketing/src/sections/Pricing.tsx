import { Check } from "lucide-react";
import { Section, SectionHeading } from "../components/Section";
import { CTAButton } from "../components/CTAButton";
import { PLANS } from "../content/pricing";
import { cn } from "../lib/cn";

export function Pricing() {
  return (
    <Section id="pricing">
      <SectionHeading
        eyebrow="Тарифы"
        title="Начните бесплатно на время beta"
        lead="Платные тарифы вводим после запуска. Сейчас — полный доступ без оплаты."
        align="center"
      />

      <div className="mx-auto mt-12 grid max-w-5xl gap-5 lg:grid-cols-3">
        {PLANS.map((plan) => (
          <div
            key={plan.name}
            className={cn(
              "relative flex flex-col rounded-2xl border bg-white p-6",
              plan.featured
                ? "border-brand-300 shadow-xl shadow-brand-600/10 ring-1 ring-brand-200"
                : "border-slate-200",
            )}
          >
            {plan.featured && (
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-600 px-3 py-1 text-xs font-semibold text-white">
                Популярный
              </span>
            )}

            <h3 className="font-semibold text-slate-900">{plan.name}</h3>
            <p className="mt-1 text-sm text-slate-500">{plan.tagline}</p>

            <div className="mt-4 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {plan.price}
              </span>
              {plan.period && (
                <span className="text-xs text-slate-400">{plan.period}</span>
              )}
            </div>

            <ul className="mt-5 flex-1 space-y-2.5">
              {plan.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
                  {f}
                </li>
              ))}
            </ul>

            <CTAButton
              href={plan.cta.href}
              external={plan.cta.external}
              variant={plan.featured ? "primary" : "secondary"}
              size="md"
              className="mt-6 w-full"
            >
              {plan.cta.label}
            </CTAButton>

            {plan.note && (
              <p className="mt-2 text-center text-xs text-slate-400">{plan.note}</p>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}
