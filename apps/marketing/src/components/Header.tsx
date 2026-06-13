import { useEffect, useState } from "react";
import { MessagesSquare } from "lucide-react";
import { CTAButton } from "./CTAButton";
import { APP } from "../lib/links";
import { cn } from "../lib/cn";

const NAV = [
  { label: "Возможности", href: "#features" },
  { label: "Как работает", href: "#how" },
  { label: "Цены", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

export function Header() {
  // Лёгкая тень и фон появляются после прокрутки — чистый hero сверху.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-50 transition-colors",
        scrolled
          ? "border-b border-slate-200 bg-white/80 backdrop-blur-md"
          : "border-b border-transparent",
      )}
    >
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
        <a href="#top" className="flex items-center gap-2 font-bold text-slate-900">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
            <MessagesSquare className="h-5 w-5" />
          </span>
          ai-message
        </a>

        <nav className="hidden items-center gap-8 md:flex">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <CTAButton href={APP.login} variant="ghost" size="md" className="hidden sm:inline-flex">
            Войти
          </CTAButton>
          <CTAButton href={APP.register} variant="primary" size="md">
            Начать бесплатно
          </CTAButton>
        </div>
      </div>
    </header>
  );
}
