import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles,
  Plus,
  Send,
  Trash2,
  MessageSquare,
  AlertCircle,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { toast } from "../components/ui/Toast";
import { cn } from "../lib/cn";
import {
  api,
  type AiSource,
  type AiThreadMessage,
} from "../lib/api";

const SUGGESTIONS = [
  "Какие темы обращений встречаются чаще всего?",
  "Где у нас слабые места в поддержке?",
  "Как корректно отвечать на жалобы клиентов?",
  "Что чаще всего вызывает негатив?",
];

type ChatMsg = Pick<AiThreadMessage, "role" | "content"> & {
  sources?: AiSource[] | null;
};

export function AssistantPage() {
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [smartUnavailable, setSmartUnavailable] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const threadsQ = useQuery({
    queryKey: ["ai-threads"],
    queryFn: api.aiListThreads,
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function openThread(id: string) {
    setThreadId(id);
    setMessages([]);
    try {
      const detail = await api.aiGetThread(id);
      setMessages(
        detail.messages.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
        })),
      );
    } catch {
      toast.error("Не удалось загрузить тред");
    }
  }

  function newChat() {
    setThreadId(null);
    setMessages([]);
    setInput("");
  }

  async function deleteThread(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await api.aiDeleteThread(id);
      qc.invalidateQueries({ queryKey: ["ai-threads"] });
      if (id === threadId) newChat();
    } catch {
      toast.error("Не удалось удалить тред");
    }
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || sending) return;
    setInput("");
    setSmartUnavailable(false);
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setSending(true);
    try {
      const resp = await api.aiChat({
        thread_id: threadId ?? undefined,
        message: question,
      });
      if (!threadId) {
        setThreadId(resp.thread_id);
        qc.invalidateQueries({ queryKey: ["ai-threads"] });
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: resp.answer,
          sources: resp.sources,
        },
      ]);
    } catch (err) {
      const status = (err as { status?: number })?.status;
      if (status === 503) {
        setSmartUnavailable(true);
      } else {
        toast.error("Ассистент не ответил, попробуйте ещё раз");
      }
      // Откатываем добавленный вопрос, чтобы пользователь мог повторить.
      setMessages((prev) => prev.slice(0, -1));
      setInput(question);
    } finally {
      setSending(false);
    }
  }

  const threads = threadsQ.data ?? [];

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="AI-ассистент"
        description="Спросите про свою переписку: темы, слабые места, как вести себя с клиентами"
      />
      <div className="flex flex-1 overflow-hidden">
        {/* Список тредов */}
        <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
          <div className="p-3">
            <Button className="w-full justify-center" onClick={newChat}>
              <Plus className="h-4 w-4" /> Новый чат
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {threads.length === 0 ? (
              <p className="px-2 py-4 text-xs text-slate-400">Пока нет диалогов</p>
            ) : (
              threads.map((t) => (
                <button
                  key={t.id}
                  onClick={() => openThread(t.id)}
                  className={cn(
                    "group mb-1 flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition",
                    t.id === threadId
                      ? "bg-brand-50 text-brand-700"
                      : "text-slate-600 hover:bg-slate-50",
                  )}
                >
                  <MessageSquare className="h-4 w-4 shrink-0 opacity-60" />
                  <span className="flex-1 truncate">{t.title}</span>
                  <Trash2
                    className="h-3.5 w-3.5 shrink-0 opacity-0 transition hover:text-rose-600 group-hover:opacity-60"
                    onClick={(e) => deleteThread(t.id, e)}
                  />
                </button>
              ))
            )}
          </div>
        </aside>

        {/* Чат */}
        <main className="flex flex-1 flex-col bg-slate-50">
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {smartUnavailable && (
              <div className="mx-auto mb-4 flex max-w-3xl items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  AI-ассистент недоступен: не настроен Smart LLM. Задайте
                  провайдер в{" "}
                  <Link to="/settings?tab=ai" className="font-medium underline">
                    Настройки → AI-ассистент
                  </Link>
                  .
                </div>
              </div>
            )}

            {messages.length === 0 && !sending ? (
              <EmptyState onPick={(s) => send(s)} />
            ) : (
              <div className="mx-auto max-w-3xl space-y-4">
                {messages.map((m, i) => (
                  <Bubble key={i} msg={m} />
                ))}
                {sending && (
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <Sparkles className="h-4 w-4 animate-pulse" />
                    Ассистент думает…
                  </div>
                )}
                <div ref={endRef} />
              </div>
            )}
          </div>

          {/* Композер */}
          <div className="border-t border-slate-200 bg-white p-4">
            <form
              className="mx-auto flex max-w-3xl items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
            >
              <textarea
                className="max-h-40 min-h-[44px] flex-1 resize-none rounded-md border border-slate-200 px-3 py-2.5 text-sm outline-none transition focus:border-brand-500"
                placeholder="Спросите что-нибудь про ваши диалоги…"
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
              />
              <Button type="submit" disabled={!input.trim() || sending}>
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
        <Sparkles className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold text-slate-800">
        Спросите про свою переписку
      </h2>
      <p className="mt-1 max-w-md text-sm text-slate-500">
        Ассистент анализирует ваши диалоги и отвечает со ссылками на источники.
        Заполните профиль бизнеса в настройках, чтобы ответы учитывали вашу
        специфику.
      </p>
      <div className="mt-6 grid w-full max-w-xl gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-600 transition hover:border-brand-300 hover:bg-brand-50/40"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm",
          isUser
            ? "bg-brand-600 text-white"
            : "border border-slate-200 bg-white text-slate-700",
        )}
      >
        <div className="whitespace-pre-wrap break-words">{msg.content}</div>
        {!isUser && msg.sources && msg.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-100 pt-2.5">
            {msg.sources.map((s) => (
              <Link
                key={s.conversation_id}
                to={`/inbox/${s.conversation_id}`}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 transition hover:bg-brand-100 hover:text-brand-700"
                title={`Похожесть: ${(s.similarity * 100).toFixed(0)}%`}
              >
                <MessageSquare className="h-3 w-3" />
                {s.title}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
