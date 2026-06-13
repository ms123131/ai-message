import { Plus } from "lucide-react";
import { Section, SectionHeading } from "../components/Section";
import { FAQ as ITEMS } from "../content/faq";

// Нативные <details>: раскрытие без JS, доступно с клавиатуры из коробки.
export function FAQ() {
  return (
    <Section id="faq" tone="muted">
      <SectionHeading
        eyebrow="Вопросы"
        title="Частые вопросы"
        lead="Если не нашли ответ — напишите нам, отвечаем быстро."
      />

      <div className="mx-auto mt-10 max-w-3xl divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
        {ITEMS.map((item) => (
          <details key={item.q} className="group px-5 sm:px-6">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 font-medium text-slate-900 [&::-webkit-details-marker]:hidden">
              {item.q}
              <Plus className="h-5 w-5 shrink-0 text-slate-400 transition-transform group-open:rotate-45" />
            </summary>
            <p className="pb-5 text-sm leading-relaxed text-slate-600">
              {item.a}
            </p>
          </details>
        ))}
      </div>
    </Section>
  );
}
