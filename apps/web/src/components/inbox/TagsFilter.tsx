import { useEffect, useRef, useState } from "react";
import { Check, Hash, ChevronDown } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";

/**
 * Multi-select фильтр по темам обращений с toggle режима ANY/ALL.
 *
 * Источник тегов — топ-20 из /dashboard/tags (то, что реально встречается
 * у tenant'а, а не весь словарь). Если тегов нет вообще — фильтр скрыт.
 *
 * Открытие по клику, закрытие — клик вне, ESC, выбор. Закрываем активный
 * popover через document-level listener (один popover в Inbox, перекрытий нет).
 */

const TAG_LABEL_OVERRIDE: Record<string, string> = {
  оплата: "Оплата",
  доставка: "Доставка",
  возврат_средств: "Возврат средств",
  жалоба: "Жалоба",
  гарантия: "Гарантия",
  вопрос_о_товаре: "Вопрос о товаре",
  техническая_проблема: "Техническая проблема",
  статус_заказа: "Статус заказа",
};

function tagLabel(slug: string): string {
  return (
    TAG_LABEL_OVERRIDE[slug] ??
    slug.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
  );
}

export function TagsFilter({
  selected,
  onChange,
  mode,
  onModeChange,
  integrationId,
}: {
  selected: readonly string[];
  onChange: (next: string[]) => void;
  mode: "any" | "all";
  onModeChange: (next: "any" | "all") => void;
  integrationId?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const tagsQ = useQuery({
    queryKey: ["dash-tags-filter", integrationId ?? null],
    queryFn: () =>
      api.getDashboardTags({
        integration_id: integrationId,
        limit: 20,
      }),
    staleTime: 60_000,
  });
  const buckets = tagsQ.data?.buckets ?? [];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Если у tenant'а ещё нет ни одного протегированного диалога — фильтр
  // бесполезен, не показываем. Иначе кнопка-загушка пустеет.
  if (!tagsQ.isLoading && buckets.length === 0) return null;

  function toggle(slug: string) {
    if (selected.includes(slug)) {
      onChange(selected.filter((s) => s !== slug));
    } else {
      onChange([...selected, slug]);
    }
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition",
          selected.length > 0
            ? "border-brand-200 bg-brand-50 text-brand-700"
            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Hash className="h-3.5 w-3.5" />
        Темы
        {selected.length > 0 && (
          <span className="rounded-full bg-brand-600 px-1.5 text-[10px] font-semibold text-white">
            {selected.length}
          </span>
        )}
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 transition",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-multiselectable="true"
          className="absolute left-0 top-full z-20 mt-1 w-72 rounded-md border border-slate-200 bg-white shadow-lg"
        >
          <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
            <span className="text-[11px] uppercase tracking-wider text-slate-500">
              Режим
            </span>
            <div className="inline-flex rounded-md border border-slate-200 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => onModeChange("any")}
                className={cn(
                  "rounded px-2 py-0.5 transition",
                  mode === "any"
                    ? "bg-brand-600 text-white"
                    : "text-slate-600 hover:bg-slate-100",
                )}
                title="Хотя бы одна из выбранных тем"
              >
                Любая
              </button>
              <button
                type="button"
                onClick={() => onModeChange("all")}
                className={cn(
                  "rounded px-2 py-0.5 transition",
                  mode === "all"
                    ? "bg-brand-600 text-white"
                    : "text-slate-600 hover:bg-slate-100",
                )}
                title="Все выбранные темы одновременно"
              >
                Все
              </button>
            </div>
          </div>

          <div className="max-h-72 overflow-y-auto py-1">
            {buckets.map((b) => {
              const isSelected = selected.includes(b.tag);
              return (
                <button
                  key={b.tag}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => toggle(b.tag)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-slate-50"
                >
                  <span className="flex items-center gap-2">
                    <span
                      className={cn(
                        "grid h-4 w-4 place-items-center rounded border",
                        isSelected
                          ? "border-brand-600 bg-brand-600 text-white"
                          : "border-slate-300 bg-white",
                      )}
                    >
                      {isSelected && <Check className="h-3 w-3" />}
                    </span>
                    {tagLabel(b.tag)}
                  </span>
                  <span className="text-xs text-slate-400">{b.count}</span>
                </button>
              );
            })}
          </div>

          {selected.length > 0 && (
            <div className="border-t border-slate-100 px-3 py-2">
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-xs text-slate-500 hover:text-slate-800"
              >
                Сбросить выбор
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export { tagLabel };
