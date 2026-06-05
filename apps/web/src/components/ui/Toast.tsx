import { Toaster, toast as sonnerToast } from "sonner";

/**
 * Глобальная toast-обвязка поверх sonner.
 *
 * Зачем wrapper: единые дефолты (позиция, длительность, стиль), один импорт
 * `toast` для всего приложения. Если соберёмся снять sonner — меняем только
 * этот файл, потребители не трогаем.
 */
export function ToastContainer() {
  return (
    <Toaster
      position="top-right"
      closeButton
      richColors
      duration={5000}
      toastOptions={{
        classNames: {
          toast: "rounded-md border border-slate-200 shadow-md text-sm",
        },
      }}
    />
  );
}

export const toast = {
  success: (msg: string, description?: string) =>
    sonnerToast.success(msg, { description }),
  error: (msg: string, description?: string) =>
    sonnerToast.error(msg, { description }),
  info: (msg: string, description?: string) =>
    sonnerToast.info(msg, { description }),
  warning: (msg: string, description?: string) =>
    sonnerToast.warning(msg, { description }),
  promise: sonnerToast.promise,
  dismiss: sonnerToast.dismiss,
};
