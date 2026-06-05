import { useEffect, type DependencyList, type RefObject } from "react";

/**
 * Хук глобальных клавиатурных сокращений для Inbox.
 *
 * Поддерживает:
 * - `j` / `k` или `ArrowDown` / `ArrowUp`: навигация по диалогам
 * - `Enter`: открыть текущий выделенный (по умолчанию уже открыт — оставлено
 *   на будущее, когда добавим preview-mode)
 * - `/`: фокус на поле поиска
 * - `Esc`: снять выделение / закрыть открытое поле
 * - `?`: показать справку (вызов callback)
 *
 * НЕ срабатывает в input/textarea/contenteditable, чтобы не ломать ввод.
 */
export interface InboxShortcutHandlers {
  onNext?: () => void;
  onPrev?: () => void;
  onOpen?: () => void;
  onEscape?: () => void;
  onFocusSearch?: () => void;
  onHelp?: () => void;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

export function useInboxShortcuts(
  handlers: InboxShortcutHandlers,
  deps: DependencyList = [],
) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = isTypingTarget(e.target);

      // ESC всегда работает (даже из inputs — это стандартное поведение
      // "выйти из режима ввода"). Дальнейшая обработка — на колбэке.
      if (e.key === "Escape") {
        handlers.onEscape?.();
        return;
      }

      // `/` фокусирует поиск даже из не-input контекста.
      if (e.key === "/" && !typing) {
        e.preventDefault();
        handlers.onFocusSearch?.();
        return;
      }

      // Остальные шорткаты — только когда не печатаем.
      if (typing) return;
      // Игнорируем модификаторы (cmd/ctrl/alt) — это команды браузера.
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      switch (e.key) {
        case "j":
        case "ArrowDown":
          e.preventDefault();
          handlers.onNext?.();
          break;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          handlers.onPrev?.();
          break;
        case "Enter":
          handlers.onOpen?.();
          break;
        case "?":
          handlers.onHelp?.();
          break;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** Утилита: focus input по ref. Возвращает функцию для onFocusSearch. */
export function focusInput(ref: RefObject<HTMLInputElement>) {
  return () => {
    ref.current?.focus();
    ref.current?.select();
  };
}
