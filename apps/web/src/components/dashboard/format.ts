/** Утилиты форматирования для дашборда. */

export function fmtNumber(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("ru-RU").format(Math.round(v));
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || sec < 1) return "—";
  if (sec < 60) return `${Math.round(sec)}с`;
  const m = sec / 60;
  if (m < 60) {
    const v = Math.round(m * 10) / 10;
    return `${v % 1 === 0 ? v : v.toFixed(1)} мин`;
  }
  const h = m / 60;
  if (h < 24) {
    const v = Math.round(h * 10) / 10;
    return `${v % 1 === 0 ? v : v.toFixed(1)} ч`;
  }
  return `${(h / 24).toFixed(1)} д`;
}

export function fmtDateShort(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtMinutesWaiting(min: number): string {
  if (min < 60) return `${min} мин`;
  const h = min / 60;
  if (h < 24) return `${h.toFixed(1).replace(".0", "")} ч`;
  return `${(h / 24).toFixed(1)} д`;
}
