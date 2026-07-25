import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { LayoutGrid, Pencil, Plus, RotateCcw, Save } from "lucide-react";
import { api } from "../api/client";
import {
  downloadDashboardExport,
  loadDashboardFilters,
  saveDashboardFilters,
  type DashboardFiltersState,
} from "../utils/dashboardFilters";
import DashboardExportMenu from "../components/dashboard/DashboardExportMenu";
import DashboardFiltersPanel from "../components/dashboard/DashboardFiltersPanel";
import DashboardWidgetCard from "../components/dashboard/DashboardWidget";
import WidgetEditorModal from "../components/dashboard/WidgetEditorModal";
import {
  DEFAULT_LAYOUT,
  METRIC_OPTIONS,
  newWidgetId,
  widgetGridSizeClass,
  type DashboardLayout,
  type DashboardWidget,
  suggestedWidgetSize,
  defaultWidgetType,
} from "../types/dashboard";

function SortableWidget({
  widget,
  filters,
  editing,
  onEdit,
  onRemove,
}: {
  widget: DashboardWidget;
  filters: DashboardFiltersState;
  editing: boolean;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: widget.id,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.85 : 1,
    zIndex: isDragging ? 2 : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`dash-sortable-item ${widgetGridSizeClass(widget.size)}`.trim()}
    >
      <DashboardWidgetCard
        widget={widget}
        filters={filters}
        editing={editing}
        onEdit={onEdit}
        onRemove={onRemove}
        dragHandleProps={editing ? { attributes, listeners } : undefined}
      />
    </div>
  );
}

export default function DashboardPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [filters, setFilters] = useState<DashboardFiltersState>(loadDashboardFilters);
  const [exporting, setExporting] = useState(false);
  const [widgets, setWidgets] = useState<DashboardWidget[]>(DEFAULT_LAYOUT.widgets);
  const [editorWidget, setEditorWidget] = useState<DashboardWidget | null>(null);
  const [dirty, setDirty] = useState(false);

  const { data: layoutData, isLoading } = useQuery({
    queryKey: ["dashboard-layout"],
    queryFn: () => api.get<DashboardLayout>("/dashboard/layout"),
  });

  useEffect(() => {
    if (layoutData?.widgets?.length && !dirty) {
      setWidgets(layoutData.widgets);
    }
  }, [layoutData, dirty]);

  const saveMutation = useMutation({
    mutationFn: (layout: DashboardLayout) => api.put<DashboardLayout>("/dashboard/layout", layout),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard-layout"] });
      qc.invalidateQueries({ queryKey: ["dashboard-metric"] });
      setDirty(false);
      setEditing(false);
    },
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const markDirty = useCallback((next: DashboardWidget[]) => {
    setWidgets(next);
    setDirty(true);
  }, []);

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = widgets.findIndex((w) => w.id === active.id);
    const newIndex = widgets.findIndex((w) => w.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = [...widgets];
    const [moved] = next.splice(oldIndex, 1);
    next.splice(newIndex, 0, moved);
    markDirty(next);
  };

  const addWidget = () => {
    const metric = "calls_total";
    const type = defaultWidgetType(metric);
    const w: DashboardWidget = {
      id: newWidgetId(),
      type,
      title: METRIC_OPTIONS.find((o) => o.value === metric)?.label ?? "Новый виджет",
      metric,
      size: suggestedWidgetSize(metric, type),
    };
    markDirty([...widgets, w]);
    setEditorWidget(w);
  };

  const removeWidget = (id: string) => {
    markDirty(widgets.filter((w) => w.id !== id));
  };

  const saveWidget = (updated: DashboardWidget) => {
    markDirty(widgets.map((w) => (w.id === updated.id ? updated : w)));
  };

  const resetLayout = () => {
    markDirty(DEFAULT_LAYOUT.widgets);
  };

  const handleFiltersChange = (next: DashboardFiltersState) => {
    setFilters(next);
    saveDashboardFilters(next);
    qc.invalidateQueries({ queryKey: ["dashboard-metric"] });
  };

  const handleExport = async (format: "json" | "csv") => {
    setExporting(true);
    try {
      await downloadDashboardExport(filters, format);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Ошибка экспорта");
    } finally {
      setExporting(false);
    }
  };

  const saveLayout = () => {
    saveMutation.mutate({ widgets });
  };

  if (isLoading && !widgets.length) return <p className="empty">Загрузка...</p>;

  return (
    <div className="dash-page">
      <div className="page-header dash-page-header">
        <h1 className="page-title">
          <LayoutGrid size={20} aria-hidden />
          Дашборд
        </h1>
        <div className="dash-toolbar-actions">
          {!editing ? (
            <>
              <DashboardExportMenu onExport={handleExport} exporting={exporting} />
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                onClick={() => setEditing(true)}
                aria-label="Редактировать дашборд"
                title="Редактировать дашборд"
              >
                <Pencil size={16} />
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn btn-secondary" onClick={addWidget}>
                <Plus size={16} />
                Виджет
              </button>
              <button type="button" className="btn btn-secondary" onClick={resetLayout}>
                <RotateCcw size={16} />
                Сброс
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={saveLayout}
                disabled={!dirty || saveMutation.isPending}
              >
                <Save size={16} />
                {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setEditing(false);
                  setDirty(false);
                  if (layoutData?.widgets?.length) setWidgets(layoutData.widgets);
                  else qc.invalidateQueries({ queryKey: ["dashboard-layout"] });
                }}
              >
                Готово
              </button>
            </>
          )}
        </div>
      </div>

      <DashboardFiltersPanel filters={filters} onChange={handleFiltersChange} />

      {editing && (
        <p className="dash-hint">
          Режим конструктора: перетаскивайте виджеты за ⋮⋮, настраивайте через ⚙. Метрики — звонки, оценки, длительность, операторы.
        </p>
      )}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={widgets.map((w) => w.id)} strategy={rectSortingStrategy}>
          <div className="dash-grid">
            {widgets.map((w) => (
              <SortableWidget
                key={w.id}
                widget={w}
                filters={filters}
                editing={editing}
                onEdit={() => setEditorWidget(w)}
                onRemove={() => removeWidget(w.id)}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      {editing && widgets.length === 0 && (
        <p className="empty">Добавьте виджет кнопкой «Виджет»</p>
      )}

      {editorWidget && (
        <WidgetEditorModal
          widget={editorWidget}
          onSave={saveWidget}
          onClose={() => setEditorWidget(null)}
        />
      )}

      {editing && !editorWidget && (
        <div className="card dash-catalog">
          <h3>Доступные метрики</h3>
          <div className="dash-catalog-grid">
            {[...new Set(METRIC_OPTIONS.map((o) => o.category))].map((cat) => (
              <div key={cat}>
                <div className="dash-catalog-category">{cat}</div>
                <ul className="dash-catalog-list">
                  {METRIC_OPTIONS.filter((o) => o.category === cat).map((o) => (
                    <li key={o.value}>{o.label}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
