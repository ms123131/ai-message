import { ArrowRight, Check } from "lucide-react";
import { CTAButton } from "../components/CTAButton";
import { BrowserFrame, DashboardMock } from "../components/Screenshot";
import { APP } from "../lib/links";

const CHANNELS = ["WhatsApp", "Telegram", "ВКонтакте", "Авито", "Виджет сайта"];

export function Hero() {
  return (
    <div id="top" className="relative overflow-hidden">
      {/* Атмосфера: инженерная сетка + мягкое световое пятно акцентного цвета.
          Без «фиолетовых градиентов на чёрном» — светлый фон, один акцент. */}
      <div className="absolute inset-0 bg-grid [mask-image:radial-gradient(ellipse_80%_60%_at_50%_0%,black_40%,transparent_100%)]" />
      <div className="absolute -top-40 left-1/2 h-[32rem] w-[64rem] -translate-x-1/2 rounded-full bg-brand-100/50 blur-3xl" />

      <div className="relative mx-auto w-full max-w-6xl px-5 pb-20 pt-16 sm:px-8 sm:pb-28 sm:pt-24">
        <div className="mx-auto max-w-3xl text-center">
          <a
            href="#how"
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-sm text-slate-600 backdrop-blur transition-colors hover:border-slate-300"
          >
            <span className="flex h-2 w-2 rounded-full bg-emerald-500" />
            Для Bitrix24 · подключение за 5 минут
          </a>

          <h1 className="mt-6 text-balance text-4xl font-bold tracking-tight text-slate-900 sm:text-6xl">
            Аналитика всех ваших чатов{" "}
            <span className="text-brand-600">в одном окне</span>
          </h1>

          <p className="mx-auto mt-5 max-w-2xl text-pretty text-lg leading-relaxed text-slate-600 sm:text-xl">
            WhatsApp, Telegram, ВКонтакте, Авито и виджет сайта из Bitrix24 —
            SLA, тональность и AI-инсайты в едином дашборде.
          </p>

          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <CTAButton href={APP.bitrix24New} variant="primary" size="lg">
              Подключить Bitrix24 за 5 минут
              <ArrowRight className="h-4 w-4" />
            </CTAButton>
            <CTAButton href="#how" variant="secondary" size="lg">
              Как это работает
            </CTAButton>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-slate-500">
            {CHANNELS.map((c) => (
              <span key={c} className="inline-flex items-center gap-1.5">
                <Check className="h-4 w-4 text-brand-500" />
                {c}
              </span>
            ))}
          </div>
        </div>

        {/* Скриншот дашборда (пока CSS-мокап на правдоподобных данных). */}
        <div className="relative mx-auto mt-14 max-w-4xl">
          <BrowserFrame>
            <DashboardMock />
          </BrowserFrame>
        </div>
      </div>
    </div>
  );
}
