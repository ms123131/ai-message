// Лендинг живёт на 77ais.ru, приложение — на поддомене app.77ais.ru.
// CTA ведут на абсолютный адрес приложения (другой домен → нужен полный URL).
const APP_ORIGIN = "https://app.77ais.ru";

export const APP = {
  register: `${APP_ORIGIN}/register`,
  login: `${APP_ORIGIN}/login`,
  bitrix24New: `${APP_ORIGIN}/integrations/bitrix24/new`,
  dashboard: `${APP_ORIGIN}/dashboard`,
} as const;

// Контакты для блока продаж и футера. Заглушки до утверждения.
export const CONTACTS = {
  salesEmail: "sales@77ais.ru",
  telegram: "https://t.me/aimessage_support",
} as const;
