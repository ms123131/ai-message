// Знак ai-message: речевой «пузырь» + восходящая пульс-линия (коммуникации
// под аналитикой). Линейный, наследует цвет через currentColor — в фирменном
// тайле получается белым, в тексте — цветом текста. Заменяет MessageSquareText.
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M5 6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-5l-4 3v-3H7a2 2 0 0 1-2-2z" />
      <path d="M8 11l2-2 1.8 2.4 2-3.4 1.6 2H17" />
    </svg>
  );
}
