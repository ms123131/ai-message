import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Inbox,
  Plug,
  Settings,
  MessageSquareText,
} from "lucide-react";
import { cn } from "../lib/cn";

const nav = [
  { to: "/dashboard", label: "Дашборд", icon: LayoutDashboard },
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/integrations", label: "Интеграции", icon: Plug },
  { to: "/settings", label: "Настройки", icon: Settings },
];

export function AppLayout() {
  return (
    <div className="flex h-full">
      <aside className="w-60 shrink-0 border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-200">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-brand-600 text-white">
            <MessageSquareText className="h-5 w-5" />
          </div>
          <div className="font-semibold tracking-tight">ai-message</div>
        </div>
        <nav className="p-2">
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
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
