import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { LogOut, ShieldCheck } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";
import { ApiError, api } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export function ProfileTab() {
  const { user, logout } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name ?? "");

  const profileMut = useMutation({
    mutationFn: () => api.updateProfile({ full_name: fullName }),
    onSuccess: () => toast.success("Профиль обновлён"),
    onError: () => toast.error("Не удалось обновить профиль"),
  });

  // Смена пароля.
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const pwdMismatch = confirmPwd.length > 0 && newPwd !== confirmPwd;

  const passwordMut = useMutation({
    mutationFn: () =>
      api.changePassword({ old_password: oldPwd, new_password: newPwd }),
    onSuccess: () => {
      toast.success("Пароль изменён");
      setOldPwd("");
      setNewPwd("");
      setConfirmPwd("");
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError && err.status === 400
          ? "Неверный текущий пароль"
          : "Не удалось сменить пароль";
      toast.error(msg);
    },
  });

  const logoutAllMut = useMutation({
    mutationFn: () => api.logoutAll(),
    onSuccess: async () => {
      toast.success("Сессии на других устройствах завершены");
      await logout();
    },
    onError: () => toast.error("Не удалось завершить сессии"),
  });

  const canChangePwd =
    oldPwd.length >= 1 && newPwd.length >= 8 && newPwd === confirmPwd;

  return (
    <div className="max-w-2xl space-y-4">
      {/* Профиль */}
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 text-sm font-medium text-slate-800">Профиль</div>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            profileMut.mutate();
          }}
        >
          <Input
            label="Имя"
            value={fullName}
            placeholder="Как к вам обращаться"
            onChange={(e) => setFullName(e.target.value)}
          />
          <Input
            label="Email"
            value={user?.email ?? ""}
            disabled
            hint="Email менять нельзя — это логин для входа"
          />
          <Button
            type="submit"
            disabled={
              profileMut.isPending || fullName === (user?.full_name ?? "")
            }
          >
            {profileMut.isPending ? "Сохранение…" : "Сохранить"}
          </Button>
        </form>
      </div>

      {/* Смена пароля */}
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 text-sm font-medium text-slate-800">
          Смена пароля
        </div>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canChangePwd) passwordMut.mutate();
          }}
        >
          <Input
            label="Текущий пароль"
            type="password"
            autoComplete="current-password"
            value={oldPwd}
            onChange={(e) => setOldPwd(e.target.value)}
          />
          <Input
            label="Новый пароль"
            type="password"
            autoComplete="new-password"
            value={newPwd}
            hint="Минимум 8 символов"
            onChange={(e) => setNewPwd(e.target.value)}
          />
          <Input
            label="Повторите новый пароль"
            type="password"
            autoComplete="new-password"
            value={confirmPwd}
            error={pwdMismatch ? "Пароли не совпадают" : undefined}
            onChange={(e) => setConfirmPwd(e.target.value)}
          />
          <Button
            type="submit"
            disabled={!canChangePwd || passwordMut.isPending}
          >
            {passwordMut.isPending ? "Сохранение…" : "Сменить пароль"}
          </Button>
        </form>
      </div>

      {/* Безопасность сессий */}
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-800">
          <ShieldCheck className="h-4 w-4 text-slate-500" /> Безопасность
        </div>
        <p className="mb-4 text-sm text-slate-500">
          Завершить все активные сессии (на этом и других устройствах). После
          этого потребуется войти заново.
        </p>
        <Button
          variant="secondary"
          disabled={logoutAllMut.isPending}
          onClick={() => logoutAllMut.mutate()}
        >
          <LogOut className="h-4 w-4" />
          {logoutAllMut.isPending ? "Завершение…" : "Выйти со всех устройств"}
        </Button>
      </div>
    </div>
  );
}
