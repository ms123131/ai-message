import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { cn } from "../lib/cn";

type Conversation = {
  id: string;
  contact: string;
  channel: "Bitrix24" | "Email" | "Telegram" | "WhatsApp";
  lastMessage: string;
  time: string;
  sentiment: "pos" | "neu" | "neg";
  unread: number;
};

const mock: Conversation[] = [
  { id: "1", contact: "Иван Петров", channel: "Bitrix24", lastMessage: "Спасибо, всё получил!", time: "10:42", sentiment: "pos", unread: 0 },
  { id: "2", contact: "ООО «Альфа»", channel: "Email", lastMessage: "Когда будет готов счёт?", time: "10:31", sentiment: "neu", unread: 2 },
  { id: "3", contact: "Anonymous", channel: "Telegram", lastMessage: "Это просто издевательство…", time: "09:58", sentiment: "neg", unread: 1 },
  { id: "4", contact: "Мария К.", channel: "WhatsApp", lastMessage: "Договорились, до встречи", time: "вчера", sentiment: "pos", unread: 0 },
];

const sentimentColor: Record<Conversation["sentiment"], string> = {
  pos: "bg-emerald-100 text-emerald-700",
  neu: "bg-slate-100 text-slate-600",
  neg: "bg-rose-100 text-rose-700",
};

const sentimentLabel: Record<Conversation["sentiment"], string> = {
  pos: "позитив",
  neu: "нейтрально",
  neg: "негатив",
};

export function InboxPage() {
  const [selected, setSelected] = useState<Conversation>(mock[0]);

  return (
    <>
      <PageHeader
        title="Inbox"
        description="Объединённая лента диалогов из всех подключённых каналов"
      />
      <div className="grid h-[calc(100%-77px)] grid-cols-[360px_1fr]">
        <div className="overflow-y-auto border-r border-slate-200 bg-white">
          {mock.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelected(c)}
              className={cn(
                "w-full border-b border-slate-100 px-5 py-4 text-left transition hover:bg-slate-50",
                selected.id === c.id && "bg-brand-50 hover:bg-brand-50",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="font-medium text-sm">{c.contact}</div>
                <div className="text-xs text-slate-400">{c.time}</div>
              </div>
              <div className="mt-1 truncate text-sm text-slate-500">
                {c.lastMessage}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                  {c.channel}
                </span>
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-xs",
                    sentimentColor[c.sentiment],
                  )}
                >
                  {sentimentLabel[c.sentiment]}
                </span>
                {c.unread > 0 && (
                  <span className="ml-auto rounded-full bg-brand-600 px-1.5 py-0.5 text-xs text-white">
                    {c.unread}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>

        <div className="flex flex-col overflow-hidden bg-slate-50">
          <div className="border-b border-slate-200 bg-white px-6 py-4">
            <div className="font-medium">{selected.contact}</div>
            <div className="text-xs text-slate-500">
              Канал: {selected.channel}
            </div>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto p-6">
            <Message side="them" text="Здравствуйте, у меня вопрос по заказу №3421" />
            <Message side="me" text="Добрый день! Подскажу, минуту, посмотрю статус" />
            <Message side="them" text={selected.lastMessage} />
          </div>
          <div className="border-t border-slate-200 bg-white p-4">
            <input
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
              placeholder="Написать сообщение… (демо)"
              disabled
            />
          </div>
        </div>
      </div>
    </>
  );
}

function Message({ side, text }: { side: "me" | "them"; text: string }) {
  return (
    <div className={cn("flex", side === "me" ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[70%] rounded-lg px-3 py-2 text-sm shadow-sm",
          side === "me" ? "bg-brand-600 text-white" : "bg-white text-slate-800",
        )}
      >
        {text}
      </div>
    </div>
  );
}
