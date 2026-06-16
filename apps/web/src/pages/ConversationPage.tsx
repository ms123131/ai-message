import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { ConversationView } from "../components/inbox/ConversationView";

export function ConversationPage() {
  const { id } = useParams<{ id: string }>();

  if (!id) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="text-sm text-slate-400">Диалог не найден</span>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-3">
        <Link
          to="/inbox"
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2.5 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
        >
          <ArrowLeft className="h-4 w-4" />
          К списку диалогов
        </Link>
      </div>
      <div className="flex-1 overflow-hidden bg-slate-50">
        <ConversationView
          key={id}
          conversationId={id}
          showExpand={false}
        />
      </div>
    </div>
  );
}
