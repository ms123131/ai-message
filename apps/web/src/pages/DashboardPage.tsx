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
import { MessagesSquare, Timer, Smile, Users } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatCard } from "../components/StatCard";

const volumeData = Array.from({ length: 14 }, (_, i) => ({
  day: `${i + 1}`,
  msgs: 120 + Math.round(Math.sin(i / 2) * 40 + Math.random() * 60),
}));

const sentimentData = [
  { name: "Позитив", value: 58 },
  { name: "Нейтрально", value: 31 },
  { name: "Негатив", value: 11 },
];

export function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Дашборд"
        description="Сводные показатели по всем подключённым каналам"
      />
      <div className="space-y-6 p-8">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Сообщений за 14 дн." value="3 482" delta="+12.4%" icon={MessagesSquare} />
          <StatCard label="Среднее время ответа" value="4 мин 12 с" delta="−18%" icon={Timer} />
          <StatCard label="Позитивный sentiment" value="58%" delta="+3 п.п." icon={Smile} />
          <StatCard label="Активных агентов" value="12" icon={Users} />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2 rounded-lg border border-slate-200 bg-white p-5">
            <div className="mb-3 text-sm font-medium text-slate-600">
              Объём сообщений (14 дней)
            </div>
            <div className="h-64">
              <ResponsiveContainer>
                <LineChart data={volumeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="day" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="msgs"
                    stroke="#3a66f5"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="mb-3 text-sm font-medium text-slate-600">
              Тональность
            </div>
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={sentimentData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#3a66f5" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
