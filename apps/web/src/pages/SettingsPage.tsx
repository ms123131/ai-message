import { PageHeader } from "../components/PageHeader";

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Настройки" description="Профиль организации и параметры" />
      <div className="p-8">
        <div className="max-w-2xl rounded-lg border border-slate-200 bg-white p-6">
          <div className="space-y-4">
            <Field label="Название организации" value="Моя компания" />
            <Field label="Часовой пояс" value="Europe/Moscow" />
            <Field label="Язык интерфейса" value="Русский" />
          </div>
        </div>
      </div>
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-sm text-slate-800">{value}</div>
    </div>
  );
}
