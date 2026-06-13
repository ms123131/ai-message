import { ArrowRight, Mail, Send } from "lucide-react";
import { CTAButton } from "../components/CTAButton";
import { APP, CONTACTS } from "../lib/links";

export function FinalCTA() {
  return (
    <section className="relative overflow-hidden bg-brand-700">
      {/* Тонкая сетка поверх акцентного фона — перекликается с hero. */}
      <div className="absolute inset-0 opacity-[0.07] [background-image:linear-gradient(to_right,white_1px,transparent_1px),linear-gradient(to_bottom,white_1px,transparent_1px)] [background-size:40px_40px]" />
      <div className="relative mx-auto w-full max-w-6xl px-5 py-20 text-center sm:px-8 sm:py-24">
        <h2 className="text-balance text-3xl font-bold tracking-tight text-white sm:text-4xl">
          Соберите все чаты в одном дашборде
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-lg text-brand-100">
          Бесплатно на время beta. Подключение за 5 минут, без карты.
        </p>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <CTAButton
            href={APP.register}
            variant="secondary"
            size="lg"
            className="!bg-white"
          >
            Начать бесплатно
            <ArrowRight className="h-4 w-4" />
          </CTAButton>
          <CTAButton
            href={`mailto:${CONTACTS.salesEmail}`}
            external
            variant="ghost"
            size="lg"
            className="!text-white hover:!text-brand-100"
          >
            <Mail className="h-4 w-4" />
            Связаться с продажами
          </CTAButton>
        </div>

        <div className="mt-6 flex items-center justify-center gap-2 text-sm text-brand-200">
          <Send className="h-4 w-4" />
          <a
            href={CONTACTS.telegram}
            target="_blank"
            rel="noopener noreferrer"
            className="underline-offset-2 hover:underline"
          >
            Поддержка в Telegram
          </a>
        </div>
      </div>
    </section>
  );
}
