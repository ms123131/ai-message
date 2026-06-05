import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";

/**
 * Лёгкий модальный диалог с порталом, focus-trap, ESC и кликом по бэкдропу.
 * Сознательно без зависимостей (Radix/Headless UI) — у нас 1-2 кейса
 * (confirm-удаление, edit-форма). Если число модалок вырастет — заменим
 * на @radix-ui/react-dialog без правок call site'ов.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  size = "md",
  closeOnOverlay = true,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  size?: "sm" | "md" | "lg";
  closeOnOverlay?: boolean;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    // Закрытие по ESC + блокировка скролла body.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Фокус в панель после открытия (первый focusable или сама панель).
    requestAnimationFrame(() => {
      const focusable = panelRef.current?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      (focusable ?? panelRef.current)?.focus();
    });

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  const sizeCls = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-2xl",
  }[size];

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dialog-title"
      aria-describedby={description ? "dialog-description" : undefined}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
        onClick={closeOnOverlay ? onClose : undefined}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cn(
          "relative w-full rounded-xl border border-slate-200 bg-white shadow-xl outline-none",
          sizeCls,
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 id="dialog-title" className="text-base font-medium text-slate-900">
              {title}
            </h2>
            {description && (
              <p id="dialog-description" className="mt-1 text-xs text-slate-500">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

/**
 * Стандартная confirm-модалка для деструктивных действий
 * (удалить, отвязать интеграцию, очистить разметку).
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  destructive = false,
  loading = false,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      size="sm"
      closeOnOverlay={!loading}
    >
      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onClose}
          disabled={loading}
          className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={loading}
          className={cn(
            "rounded-md px-3 py-2 text-sm font-medium text-white shadow-sm disabled:opacity-50",
            destructive
              ? "bg-rose-600 hover:bg-rose-700"
              : "bg-brand-600 hover:bg-brand-700",
          )}
        >
          {loading ? "..." : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
