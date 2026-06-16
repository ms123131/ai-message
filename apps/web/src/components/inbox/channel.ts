import type { ConversationChannel } from "../../lib/api";

export const channelLabel: Record<ConversationChannel, string> = {
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  vk: "ВКонтакте",
  instagram: "Instagram",
  facebook: "Facebook",
  livechat: "Виджет сайта",
  email: "Email",
  other: "Другое",
};

export const channelBadge: Record<ConversationChannel, string> = {
  whatsapp: "bg-emerald-100 text-emerald-700",
  telegram: "bg-sky-100 text-sky-700",
  vk: "bg-blue-100 text-blue-700",
  instagram: "bg-pink-100 text-pink-700",
  facebook: "bg-indigo-100 text-indigo-700",
  livechat: "bg-violet-100 text-violet-700",
  email: "bg-amber-100 text-amber-700",
  other: "bg-slate-100 text-slate-600",
};
