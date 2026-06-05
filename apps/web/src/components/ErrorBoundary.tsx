import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./ui/Button";

interface Props {
  children: ReactNode;
  /** Если задан — используется вместо дефолтного экрана. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Корневой ErrorBoundary. Ловит render-ошибки во всём дереве React и показывает
 * восстановительный экран с retry, не белую страницу. Сетевые ошибки сюда не
 * долетают — для них есть QueryClient.onError → toast.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Когда подключим Sentry — сюда уйдёт captureException(error, { extra: info }).
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <div
        role="alert"
        className="flex min-h-screen items-center justify-center bg-slate-50 px-4"
      >
        <div className="w-full max-w-md rounded-xl border border-rose-200 bg-white p-6 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-rose-600">
            <AlertTriangle className="h-5 w-5" />
            <div className="font-medium">Что-то пошло не так</div>
          </div>
          <p className="mb-4 text-sm text-slate-600">
            Произошла ошибка в интерфейсе. Попробуйте перезагрузить раздел —
            если проблема повторится, обновите страницу.
          </p>
          <details className="mb-4 rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600 [&_summary]:cursor-pointer">
            <summary className="font-medium text-slate-700">
              Детали ошибки
            </summary>
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap font-mono">
              {error.message}
            </pre>
          </details>
          <div className="flex gap-2">
            <Button onClick={this.reset}>
              <RefreshCw className="h-4 w-4" /> Попробовать снова
            </Button>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Обновить страницу
            </Button>
          </div>
        </div>
      </div>
    );
  }
}
