import { cn } from "../lib/cn";

// Порог согласован с бэком (app/api/v1/conversations.py::SENTIMENT_THRESHOLD).
// Менять только синхронно с бэком, иначе фильтр «только негатив» разойдётся
// с цветом бэйджа.
export const SENTIMENT_THRESHOLD = 0.2;

export type SentimentTone = "positive" | "neutral" | "negative" | "unknown";

export function toneFromScore(score: number | null | undefined): SentimentTone {
  if (score === null || score === undefined || Number.isNaN(score)) return "unknown";
  if (score > SENTIMENT_THRESHOLD) return "positive";
  if (score < -SENTIMENT_THRESHOLD) return "negative";
  return "neutral";
}

const TONE_LABEL: Record<SentimentTone, string> = {
  positive: "позитивная",
  neutral: "нейтральная",
  negative: "негативная",
  unknown: "ещё не оценена",
};

const SIZE_CLASS = {
  sm: "h-2 w-2",
  md: "h-2.5 w-2.5",
  lg: "h-3 w-3",
} as const;

export type SentimentBadgeProps = {
  score: number | null | undefined;
  size?: keyof typeof SIZE_CLASS;
  /** Опциональный счётчик «из M клиентских сообщений» для tooltip. */
  messageCount?: number | null;
  className?: string;
};

export function SentimentBadge({
  score,
  size = "md",
  messageCount,
  className,
}: SentimentBadgeProps) {
  const tone = toneFromScore(score);
  const label = TONE_LABEL[tone];
  const scoreText =
    score !== null && score !== undefined && !Number.isNaN(score)
      ? score.toFixed(2)
      : "—";
  const messagePart =
    messageCount && messageCount > 0 ? ` из ${messageCount} сообщений` : "";
  const title = `Тональность клиента: ${label} (${scoreText}${messagePart})`;

  const dotColor =
    tone === "positive"
      ? "bg-emerald-500"
      : tone === "negative"
        ? "bg-rose-500"
        : tone === "neutral"
          ? "bg-slate-400"
          : "border border-dashed border-slate-300 bg-transparent";

  return (
    <span
      data-testid="sentiment-badge"
      data-tone={tone}
      title={title}
      aria-label={title}
      className={cn(
        "inline-block shrink-0 rounded-full",
        SIZE_CLASS[size],
        dotColor,
        className,
      )}
    />
  );
}
