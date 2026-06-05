import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { cn } from "../../lib/cn";

/**
 * Поле поиска по сообщениям диалогов. Дебаунсит ввод 300 мс перед тем,
 * как пушнуть `q` в URL — иначе на каждый символ дёргается backend.
 * Внешний `value` синхронизирует обратно (например, после сброса фильтров).
 *
 * Регистрирует ref на `<input>`, чтобы хук useKeyboardShortcuts мог
 * сфокусировать поле по нажатию `/`.
 */
export function SearchBar({
  value,
  onChange,
  placeholder = "Поиск по сообщениям…",
  inputRef,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  inputRef?: React.RefObject<HTMLInputElement>;
}) {
  const [local, setLocal] = useState(value);
  const localRef = useRef(local);
  localRef.current = local;

  // Внешнее значение обновилось (например, очистка фильтров) — синкаем.
  useEffect(() => {
    setLocal(value);
  }, [value]);

  // Дебаунс на 300 мс.
  useEffect(() => {
    if (local === value) return;
    const t = setTimeout(() => {
      // Если за время дебаунса успело прийти новое значение извне — не перезаписываем.
      if (localRef.current === local) onChange(local);
    }, 300);
    return () => clearTimeout(t);
    // onChange сознательно не в deps: его меняющаяся ссылка ресетит таймер.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local, value]);

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-1.5",
        "focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100",
      )}
    >
      <Search className="h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
      <input
        ref={inputRef}
        type="search"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setLocal("");
            onChange("");
            (e.target as HTMLInputElement).blur();
          }
        }}
        placeholder={placeholder}
        aria-label="Поиск по сообщениям"
        className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
      />
      {local && (
        <button
          type="button"
          onClick={() => {
            setLocal("");
            onChange("");
          }}
          aria-label="Очистить поиск"
          className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      <kbd className="hidden rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-mono text-slate-400 sm:inline">
        /
      </kbd>
    </div>
  );
}
