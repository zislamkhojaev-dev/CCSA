import { Suspense, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Phone,
  Users,
  ListChecks,
  FlaskConical,
  Settings,
  LogOut,
  Sun,
  Moon,
  Microscope,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { api } from "../api/client";
import { PlaygroundProvider } from "../context/PlaygroundContext";
import { getSidebarCollapsed, setSidebarCollapsed } from "../utils/sidebar";
import { getTheme, toggleTheme, type Theme } from "../utils/theme";

const nav = [
  { to: "/", label: "Дашборд", icon: LayoutDashboard },
  { to: "/calls", label: "Звонки", icon: Phone },
  { to: "/operators", label: "Операторы", icon: Users },
  { to: "/scenarios", label: "Сценарии", icon: ListChecks },
  { to: "/research", label: "Исследования", icon: Microscope },
  { to: "/playground", label: "Плейграунд", icon: FlaskConical },
  { to: "/settings", label: "Настройки", icon: Settings },
];

export default function SidebarLayout() {
  const [theme, setTheme] = useState<Theme>(getTheme);
  const [collapsed, setCollapsed] = useState(getSidebarCollapsed);
  const navigate = useNavigate();
  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<{ full_name: string; role: string }>("/auth/me"),
  });

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      setSidebarCollapsed(next);
      return next;
    });
  };

  const logout = async () => {
    await api.post("/auth/logout");
    navigate("/login");
  };

  return (
    <div className={`app-layout${collapsed ? " app-layout--sidebar-collapsed" : ""}`}>
      <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
        <div className="sidebar-header">
          {!collapsed && <div className="sidebar-logo">CCSA Analytics</div>}
          <button
            type="button"
            className="sidebar-toggle"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Развернуть панель" : "Свернуть панель"}
            title={collapsed ? "Развернуть панель" : "Свернуть панель"}
          >
            {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>
        <nav>
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) => (isActive ? "active" : "")}
              title={label}
              aria-label={label}
            >
              <Icon size={18} aria-hidden />
              <span className="sidebar-nav-label">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          {!collapsed && (
            <div className="sidebar-footer-user">
              <div>
                {user?.full_name || "..."}
                <div className="sidebar-footer-role">{user?.role}</div>
              </div>
            </div>
          )}
          <div className={`sidebar-footer-actions${collapsed ? " sidebar-footer-actions--collapsed" : ""}`}>
            <button
              type="button"
              className="theme-toggle"
              onClick={() => setTheme(toggleTheme())}
              aria-label={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
              title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            {!collapsed && (
              <button type="button" className="btn btn-secondary btn-block sidebar-logout" onClick={logout}>
                <LogOut size={16} /> Выход
              </button>
            )}
          </div>
        </div>
      </aside>
      <main className="main-content">
        <PlaygroundProvider>
          <Suspense fallback={<div className="loading-page">Загрузка…</div>}>
            <Outlet />
          </Suspense>
        </PlaygroundProvider>
      </main>
    </div>
  );
}
