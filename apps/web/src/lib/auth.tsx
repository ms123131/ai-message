import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  ApiError,
  tokenStore,
  setUnauthorizedHandler,
  type CurrentUser,
  type TenantInfo,
} from "./api";

type Status = "loading" | "authenticated" | "anonymous";

type AuthState = {
  status: Status;
  user: CurrentUser | null;
  tenant: TenantInfo | null;
  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    full_name?: string;
    workspace_name?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [tenant, setTenant] = useState<TenantInfo | null>(null);

  // Колбэк для api-клиента: при 401, который не починился refresh'ом, разлогиниваем.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setTenant(null);
      setStatus("anonymous");
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // На старте: если есть access-токен — спрашиваем /me.
  // Если нет — пробуем refresh (cookie может быть жива после F5).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (tokenStore.get()) {
          const me = await api.me();
          if (!cancelled) {
            setUser(me.user);
            setTenant(me.tenant);
            setStatus("authenticated");
            return;
          }
        }
        try {
          const refreshed = await api.refresh();
          tokenStore.set(refreshed.access_token);
          if (!cancelled) {
            setUser(refreshed.user);
            setTenant(refreshed.tenant);
            setStatus("authenticated");
          }
        } catch {
          if (!cancelled) setStatus("anonymous");
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          if (!cancelled) setStatus("anonymous");
        } else if (!cancelled) {
          setStatus("anonymous");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const resp = await api.login({ email, password });
    tokenStore.set(resp.access_token);
    setUser(resp.user);
    setTenant(resp.tenant);
    setStatus("authenticated");
  }, []);

  const register = useCallback(
    async (data: {
      email: string;
      password: string;
      full_name?: string;
      workspace_name?: string;
    }) => {
      const resp = await api.register(data);
      tokenStore.set(resp.access_token);
      setUser(resp.user);
      setTenant(resp.tenant);
      setStatus("authenticated");
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // даже если сервер недоступен — гасим локально
    }
    tokenStore.clear();
    setUser(null);
    setTenant(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthState>(
    () => ({ status, user, tenant, login, register, logout }),
    [status, user, tenant, login, register, logout],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
