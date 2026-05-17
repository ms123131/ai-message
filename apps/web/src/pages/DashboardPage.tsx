import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
} from "recharts";
import {
  AlertTriangle,
  Loader2,
  MessagesSquare,
  MessageCircle,
  Plug,
  Radio,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatCard } from "../components/StatCard";
import { Button } from "../components/ui/Button";
import { api, type ConversationChannel } from "../lib/api";

const channelLabel: Record<ConversationChannel, string> = {
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  vk: "ВК",
  instagram: "Instagram",
  facebook: "Facebook",
  livechat: "Виджет",
  email: "Email",
  other: "Другое",
};

const RANGE_DAYS = 14;

export function DashboardPage() {
  const integrationsQ = useQuery({
    queryKey: ["integrations"],
    queryFn: api.listIntegrations,
  });

  const statsQ = useQuery({
    queryKey: ["dashboard-stats", RANGE_DAYS],
    queryFn: () => api.getDashboardStats({ days: RANGE_DAYS }),
    enabled: integrationsQ.isSuccess,
    refetchInterval: 30000,
  });

  if (integrationsQ.isLoading) {
    return (
      <>
        <PageHeader title="Дашборд" />
        <Center>
          <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
        </Center>
      </>
    );
  }

  if (integrationsQ.isSuccess && (integrationsQ.data ?? []).length === 0) {
    return (
      <>
        <PageHeader title="Дашборд" />
        <div className="flex items-center justify-center p-16">
          <div className="max-w-md text-center">
            <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-brand-50">
              <Plug className="h-6 w-6 text-brand-600" />
            </div>
            <h3 className="text-lg font-semibold text-slate-800">
              Нет данных для анализа
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              Подключите Bitrix24, чтобы увидеть сводные метрики по диалогам и
              сообщениям.
            </p>
            <div className="mt-5">
              <Link to="/integrations/bitrix24/new">
                <Button>Подключить Bitrix24</Button>
              </Link>
            </div>
          </div>
        </div>
      </>
    );
  }

  const stats = statsQ.data;
  const volumeData =
    stats?.volume_by_day.map((p) => ({
      day: p.day.slice(5), // MM-DD
      msgs: p.count,
    })) ?? [];

  const channelData =
    stats?.by_channel.map((c) => ({
      name: channelLabel[c.channel] ?? c.channel,
      value: c.messages,
    })) ?? [];

  return (
    <>
      <PageHeader
        title="Дашборд"
        description={`Сводные показатели за последние ${RANGE_DAYS} дней`}
      />
      <div className="space-y-6 p-8">
        {statsQ.isError && (
          <div className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <div>Не удалось загрузить статистику: {(statsQ.error as Error).message}</div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label={`Сообщений за ${RANGE_DAYS} дн.`}
            value={fmtNum(stats?.total_messages)}
            icon={MessagesSquare}
          />
          <StatCard
            label="Всего диалогов"
            value={fmtNum(stats?.total_conversations)}
            icon={MessageCircle}
          />
          <StatCard
            label="Открытых диалогов"
            value={fmtNum(stats?.open_conversations)}
            icon={Radio}
          />
          <StatCard
            label="Активных каналов"
            value={fmtNum(stats?.by_channel.length)}
            icon={Plug}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <ChartCard
            title={`Объём сообщений (${RANGE_DAYS} дней)`}
            loading={statsQ.isLoading}
            empty={volumeData.every((p) => p.msgs === 0)}
            className="lg:col-span-2"
          >
            <LineChart data={volumeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="day" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="msgs"
                stroke="#3a66f5"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ChartCard>

          <ChartCard
            title="Сообщения по каналам"
            loading={statsQ.isLoading}
            empty={channelData.length === 0}
          >
            <BarChart data={channelData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#3a66f5" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ChartCard>
        </div>
      </div>
    </>
  );
}

function ChartCard({
  title,
  children,
  loading,
  empty,
  className,
}: {
  title: string;
  children: React.ReactElement;
  loading?: boolean;
  empty?: boolean;
  className?: string;
}) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-white p-5 ${className ?? ""}`}>
      <div className="mb-3 text-sm font-medium text-slate-600">{title}</div>
      <div className="h-64">
        {loading ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Загрузка…
          </div>
        ) : empty ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            нет данных за выбранный период
          </div>
        ) : (
          <ResponsiveContainer>{children}</ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center p-16">{children}</div>
  );
}

function fmtNum(n: number | undefined | null): string {
  if (n === undefined || n === null) return "—";
  return new Intl.NumberFormat("ru-RU").format(n);
}
