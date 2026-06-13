import { MessagesSquare } from "lucide-react";
import { APP, CONTACTS } from "../lib/links";

// Footer (SITE_PLAN §9). Юр.информация — заглушки до коммерческого запуска;
// без реквизитов платёжки не пропустят, но для beta достаточно контактов.
export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto w-full max-w-6xl px-5 py-12 sm:px-8">
        <div className="flex flex-col gap-10 md:flex-row md:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2 font-bold text-slate-900">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
                <MessagesSquare className="h-5 w-5" />
              </span>
              ai-message
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-500">
              Аналитика клиентских чатов из Bitrix24 в одном окне.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            <FooterCol title="Продукт">
              <FooterLink href="#features">Возможности</FooterLink>
              <FooterLink href="#pricing">Цены</FooterLink>
              <FooterLink href="#faq">FAQ</FooterLink>
            </FooterCol>
            <FooterCol title="Кабинет">
              <FooterLink href={APP.login}>Войти</FooterLink>
              <FooterLink href={APP.register}>Регистрация</FooterLink>
              <FooterLink href={APP.bitrix24New}>Подключить Bitrix24</FooterLink>
            </FooterCol>
            <FooterCol title="Правовое">
              <FooterLink href="/legal/privacy">Обработка данных</FooterLink>
              <FooterLink href="/legal/offer">Оферта</FooterLink>
              <FooterLink href={`mailto:${CONTACTS.salesEmail}`} external>
                {CONTACTS.salesEmail}
              </FooterLink>
            </FooterCol>
          </div>
        </div>

        <div className="mt-10 flex flex-col gap-2 border-t border-slate-100 pt-6 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between">
          <span>© {year} ai-message. Все права защищены.</span>
          <span>Реквизиты юр. лица — уточняются.</span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <ul className="mt-3 space-y-2">{children}</ul>
    </div>
  );
}

function FooterLink({
  href,
  children,
  external,
}: {
  href: string;
  children: React.ReactNode;
  external?: boolean;
}) {
  return (
    <li>
      <a
        href={href}
        {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        className="text-sm text-slate-500 transition-colors hover:text-slate-900"
      >
        {children}
      </a>
    </li>
  );
}
