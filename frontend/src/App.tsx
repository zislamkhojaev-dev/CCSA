import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import SidebarLayout from "./layouts/SidebarLayout";
import LoginPage from "./pages/LoginPage";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const CallsPage = lazy(() => import("./pages/CallsPage"));
const CallDetailPage = lazy(() => import("./pages/CallDetailPage"));
const OperatorsPage = lazy(() => import("./pages/OperatorsPage"));
const ScenariosPage = lazy(() => import("./pages/ScenariosPage"));
const ScenarioEditPage = lazy(() => import("./pages/ScenarioEditPage"));
const ResearchListPage = lazy(() => import("./pages/ResearchListPage"));
const ResearchNewPage = lazy(() => import("./pages/ResearchNewPage"));
const ResearchDetailPage = lazy(() => import("./pages/ResearchDetailPage"));
const PlaygroundPage = lazy(() => import("./pages/PlaygroundPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<{ login: string }>("/auth/me"),
    retry: false,
  });
  if (isLoading) return <div className="loading-page">Загрузка…</div>;
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
