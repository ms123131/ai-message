import { QueryCache, QueryClient, MutationCache } from "@tanstack/react-query";
import { toast } from "../components/ui/Toast";

/**
 * Единая фабрика QueryClient'а.
 *
 * - QueryCache.onError — показываем toast только если у запроса нет своего
 *   обработчика (`meta.silent: true` отключает), чтобы не дублировать с
 *   inline-сообщениями (формы логина и т.п.).
 * - MutationCache.onError — toast всегда, мутации редко имеют inline-обработку.
 * - 401 не показываем — это нормальная ситуация (auth-refresh-цикл в lib/api.ts).
 */
function isAuthError(err: unknown): boolean {
  const msg = (err as Error | undefined)?.message ?? "";
  return /(^|\b)401(\b|$)|unauthor/i.test(msg);
}

function describe(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return "Неизвестная ошибка";
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (err, query) => {
        if (query.meta?.silent) return;
        if (isAuthError(err)) return;
        toast.error("Не удалось загрузить данные", describe(err));
      },
    }),
    mutationCache: new MutationCache({
      onError: (err, _vars, _ctx, mutation) => {
        if (mutation.meta?.silent) return;
        if (isAuthError(err)) return;
        toast.error("Действие не выполнено", describe(err));
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, err) => {
          if (isAuthError(err)) return false;
          return failureCount < 2;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}

/**
 * Расширение типов TanStack Query: meta.silent = true отключает
 * автоматический toast.
 */
declare module "@tanstack/react-query" {
  interface Register {
    queryMeta: { silent?: boolean };
    mutationMeta: { silent?: boolean };
  }
}
