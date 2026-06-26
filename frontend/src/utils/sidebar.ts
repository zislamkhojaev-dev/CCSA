const STORAGE_KEY = "ccsa-sidebar-collapsed";

export function getSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setSidebarCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function toggleSidebarCollapsed(): boolean {
  const next = !getSidebarCollapsed();
  setSidebarCollapsed(next);
  return next;
}
