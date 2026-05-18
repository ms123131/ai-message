import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Inbox,
  Plug,
  Settings,
  MessageSquareText,
  LogOut,
} from "lucide-react";
import { cn } from "../lib/cn";
import { useAuth } from "../lib/auth";

const nav = [
  { to: "/dashboard", label: "Дашборд", icon: LayoutDashboard },
  { to: "/inbox", label: "Диалоги", icon: Inbox },
  { to: "/integrations", label: "Интеграции", icon: Plug },
  { to: "/settings", label: "Настройки", icon: Settings },
];

export function AppLayout() {
  const { user, tenant, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-brand-600 text-white">
            <MessageSquareText className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="truncate font-semibold tracking-tight">
              ai-message
            </div>
            {tenant && (
              <div className="truncate text-xs text-slate-400">
                {tenant.name}
              </div>
            )}
          </div>
        </div>
        <nav className="flex-1 p-2">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition",
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-700 hover:bg-slate-100",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        {user && (
          <div className="border-t border-slate-200 p-3">
            <div className="mb-2 px-1 text-xs">
              <div className="truncate font-medium text-slate-700">
                {user.full_name || user.email}
              </div>
              <div className="truncate text-slate-400">{user.email}</div>
            </div>
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
            >
              <LogOut className="h-4 w-4" />
              Выйти
            </button>
          </div>
        )}
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
