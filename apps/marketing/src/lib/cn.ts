// Минимальный join классов — не тянем clsx/tailwind-merge ради лендинга.
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
