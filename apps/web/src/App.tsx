import { Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { DashboardPage } from "./pages/DashboardPage";
import { InboxPage } from "./pages/InboxPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { Bitrix24Wizard } from "./pages/integrations/Bitrix24Wizard";
import { TelegramUserWizard } from "./pages/integrations/TelegramUserWizard";
import { SettingsPage } from "./pages/SettingsPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route
            path="/integrations/bitrix24/new"
            element={<Bitrix24Wizard />}
          />
          <Route
            path="/integrations/telegram-user/new"
            element={<TelegramUserWizard />}
          />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
