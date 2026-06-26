import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import SidebarLayout from "./layouts/SidebarLayout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import CallsPage from "./pages/CallsPage";
import CallDetailPage from "./pages/CallDetailPage";
import OperatorsPage from "./pages/OperatorsPage";
import ScenariosPage from "./pages/ScenariosPage";
import ScenarioEditPage from "./pages/ScenarioEditPage";
import ResearchListPage from "./pages/ResearchListPage";
import ResearchNewPage from "./pages/ResearchNewPage";
import ResearchDetailPage from "./pages/ResearchDetailPage";
import PlaygroundPage from "./pages/PlaygroundPage";
import SettingsPage from "./pages/SettingsPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<{ login: string }>("/auth/me"),
    retry: false,
  });
  if (isLoading) return <div className="empty">Загрузка...</div>;
  if (isError) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <SidebarLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="calls" element={<CallsPage />} />
        <Route path="calls/:id" element={<CallDetailPage />} />
        <Route path="operators" element={<OperatorsPage />} />
        <Route path="scenarios" element={<ScenariosPage />} />
        <Route path="scenarios/:id" element={<ScenarioEditPage />} />
        <Route path="scenarios/new" element={<ScenarioEditPage />} />
        <Route path="research" element={<ResearchListPage />} />
        <Route path="research/new" element={<ResearchNewPage />} />
        <Route path="research/:id" element={<ResearchDetailPage />} />
        <Route path="playground" element={<PlaygroundPage />} />
        <Route path="settings/*" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
