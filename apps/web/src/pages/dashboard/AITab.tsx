import {
  AlertCircle,
  Bot,
  Hash,
  Lightbulb,
  Lock,
  Smile,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wand2,
} from "lucide-react";
import { Button } from "../../components/ui/Button";

/**
 * Phase 4Г — заглушки AI-аналитики.
 *
 * Карточки описывают, что появится в финальной версии. Реальные модели
 * (sentiment, BERTopic, LLM-резюмирование) добавим в фазе 6.
 */

type Feature = {
  icon: typeof Sparkles;
  title: string;
  description: string;
  preview: React.ReactNode;
  accent: string; // tailwind bg-* для иконки
};

const FEATURES: Feature[] = [
  {
    icon: Smile,
    accent: "bg-emerald-50 text-emerald-600",
    title: "Тональность диалогов",
    description:
      "Автоматическая разметка каждого диалога по эмоциональному фону: позитив, нейтрал, негатив. Динамика и тренды по периодам.",
    preview: (
      <SentimentPreview values={{ positive: 64, neutral: 27, negative: 9 }} />
    ),
  },
  {
    icon: Hash,
    accent: "bg-violet-50 text-violet-600",
    title: "Темы обращений",
    description:
      "BERTopic кластеризует похожие диалоги в темы без ручной разметки. Видно, о чём чаще всего пишут клиенты.",
    preview: (
      <TopicsPreview
        topics={[
          { name: "Доставка", weight: 42 },
          { name: "Возврат товара", weight: 28 },
          { name: "Оплата", weight: 16 },
          { name: "Гарантия", weight: 9 },
          { name: "Другое", weight: 5 },
        ]}
      />
    ),
  },
  {
    icon: AlertCircle,
    accent: "bg-rose-50 text-rose-600",
    title: "Обнаружение аномалий",
    description:
      "Мониторинг резких всплесков по темам и тональности. Уведомление, когда что-то идёт не так — до того, как заметит руководитель.",
    preview: (
      <AnomalyPreview
        text="Жалоб на «не приходит код» сегодня в 4× выше нормы"
      />
    ),
  },
  {
    icon: Wand2,
    accent: "bg-amber-50 text-amber-600",
    title: "Оценка качества ответов",
    description:
      "LLM проверяет диалог по чек-листу: эмпатия, полнота ответа, корректность, грамматика. Не только скорость, но и качество.",
    preview: <QualityScorePreview score={87} />,
  },
  {
    icon: Bot,
    accent: "bg-sky-50 text-sky-600",
    title: "Авто-резюме длинных диалогов",
    description:
      "Не читать 50 сообщений — кнопка «Сводка» в Inbox даёт 3 буллета с сутью и решением.",
    preview: (
      <ul className="space-y-1 text-xs text-slate-600">
        <li>• Клиент не получил товар, заказ #12345</li>
        <li>• Оператор отправил трек-номер и принёс извинения</li>
        <li>• Решено: компенсация 500 ₽ на следующий заказ</li>
      </ul>
    ),
  },
  {
    icon: TrendingDown,
    accent: "bg-pink-50 text-pink-600",
    title: "Прогноз оттока клиентов",
    description:
      "Модель оценивает риск ухода клиента на основе истории обращений и тональности. Список «обратите внимание» — в дашборде.",
    preview: <ChurnPreview at_risk={3} watch={12} healthy={84} />,
  },
  {
    icon: Sparkles,
    accent: "bg-indigo-50 text-indigo-600",
    title: "Авто-тегирование диалогов",
    description:
      "Каждый диалог получает 3–5 тегов автоматически по теме и интенту. Поиск и фильтры становятся точными без ручного труда.",
    preview: (
      <div className="flex flex-wrap gap-1.5">
        {["доставка", "срочно", "повторное обращение", "vip-клиент"].map(
          (t) => (
            <span
              key={t}
              className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
            >
              #{t}
            </span>
          ),
        )}
      </div>
    ),
  },
  {
    icon: Lightbulb,
    accent: "bg-orange-50 text-orange-600",
    title: "Еженедельные инсайты",
    description:
      "Раз в неделю система сама собирает наблюдения: что выросло, что упало, на что обратить внимание руководителю.",
    preview: (
      <ul className="space-y-1 text-xs text-slate-600">
        <li className="flex items-start gap-1">
          <TrendingUp className="mt-0.5 h-3 w-3 text-emerald-600" />
          <span>Скорость ответа улучшилась на 18%</span>
        </li>
        <li className="flex items-start gap-1">
          <TrendingDown className="mt-0.5 h-3 w-3 text-rose-600" />
          <span>Негатив по теме «возврат» вырос на 32%</span>
        </li>
        <li className="flex items-start gap-1">
          <AlertCircle className="mt-0.5 h-3 w-3 text-amber-600" />
          <span>Иванов перегружен: +40% нагрузки vs среднего</span>
        </li>
      </ul>
    ),
  },
];

export function AITab() {
  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-xl border border-brand-200 bg-gradient-to-br from-brand-50 via-white to-violet-50 p-6">
        <div className="flex items-start gap-4">
          <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-white shadow-sm">
            <Sparkles className="h-6 w-6 text-brand-600" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">
                AI-аналитика
              </h2>
              <span className="rounded-full bg-brand-600 px-2 py-0.5 text-xs font-medium text-white">
                скоро
              </span>
            </div>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              Восемь возможностей, которые превратят сырые цифры в действия:
              автоматическая разметка тональности, выделение тем без
              ручного тегирования, LLM-оценка качества и предсказание ухода
              клиентов. Доступно в одном из ближайших обновлений.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button disabled className="cursor-not-allowed">
                <Lock className="h-4 w-4" /> Подключить — скоро
              </Button>
              <span className="text-xs text-slate-500">
                Хотите узнать первыми о запуске?{" "}
                <a
                  href="mailto:info@gitpro.pro?subject=AI-аналитика%20в%20ai-message"
                  className="font-medium text-brand-700 hover:underline"
                >
                  Напишите нам
                </a>
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {FEATURES.map((f) => (
          <FeatureCard key={f.title} {...f} />
        ))}
      </div>
    </div>
  );
}

function FeatureCard({ icon: Icon, title, description, preview, accent }: Feature) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-white p-5">
      <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-500">
        <Lock className="h-3 w-3" /> скоро
      </span>
      <div className="flex items-start gap-3">
        <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${accent}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="font-medium text-slate-800">{title}</div>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            {description}
          </p>
        </div>
      </div>
      <div className="mt-4 rounded-md border border-slate-100 bg-slate-50 p-3">
        {preview}
      </div>
    </div>
  );
}

// --- Превью-блоки (имитация будущего UI) ---

function SentimentPreview({
  values,
}: {
  values: { positive: number; neutral: number; negative: number };
}) {
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
        <div
          className="bg-emerald-500"
          style={{ width: `${values.positive}%` }}
        />
        <div className="bg-slate-300" style={{ width: `${values.neutral}%` }} />
        <div className="bg-rose-500" style={{ width: `${values.negative}%` }} />
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-slate-500">
        <span>😀 {values.positive}%</span>
        <span>😐 {values.neutral}%</span>
        <span>😞 {values.negative}%</span>
      </div>
    </div>
  );
}

function TopicsPreview({
  topics,
}: {
  topics: { name: string; weight: number }[];
}) {
  return (
    <ul className="space-y-1">
      {topics.map((t) => (
        <li
          key={t.name}
          className="flex items-center justify-between gap-2 text-xs"
        >
          <span className="truncate text-slate-700">{t.name}</span>
          <div className="flex shrink-0 items-center gap-2">
            <div className="h-1.5 w-20 overflow-hidden rounded bg-slate-200">
              <div
                className="h-full bg-violet-500"
                style={{ width: `${t.weight}%` }}
              />
            </div>
            <span className="w-7 text-right tabular-nums text-slate-500">
              {t.weight}%
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function AnomalyPreview({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
      <div>
        <div className="font-medium text-slate-700">Обнаружена аномалия</div>
        <div className="text-slate-500">{text}</div>
      </div>
    </div>
  );
}

function QualityScorePreview({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid h-14 w-14 place-items-center rounded-full border-4 border-emerald-200">
        <span className="text-sm font-semibold text-emerald-700">{score}</span>
      </div>
      <ul className="space-y-0.5 text-xs text-slate-600">
        <li>✓ Эмпатия</li>
        <li>✓ Полнота ответа</li>
        <li>· Время ответа</li>
      </ul>
    </div>
  );
}

function ChurnPreview({
  at_risk,
  watch,
  healthy,
}: {
  at_risk: number;
  watch: number;
  healthy: number;
}) {
  return (
    <div className="flex items-stretch gap-2 text-xs">
      <Stat color="bg-rose-50 text-rose-700" label="в зоне риска" value={at_risk} />
      <Stat color="bg-amber-50 text-amber-700" label="наблюдать" value={watch} />
      <Stat color="bg-emerald-50 text-emerald-700" label="лояльные" value={healthy} />
    </div>
  );
}

function Stat({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <div className={`flex-1 rounded-md px-2 py-1.5 ${color}`}>
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wider opacity-70">
        {label}
      </div>
    </div>
  );
}
