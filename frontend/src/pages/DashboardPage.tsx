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
import { GripVertical, LayoutGrid, Pencil, Plus, RotateCcw, Save } from "lucide-react";
import {
  DASHBOARD_PERIOD_OPTIONS,
  getDashboardPeriodDays,
  setDashboardPeriodDays,
  type DashboardPeriodDays,
} from "../utils/dashboardPeriod";
import DashboardWidgetCard from "../components/dashboard/DashboardWidget";
import WidgetEditorModal from "../components/dashboard/WidgetEditorModal";
import {
  DEFAULT_LAYOUT,
  METRIC_OPTIONS,
  newWidgetId,
  widgetGridSizeClass,
  type DashboardLayout,
  type DashboardWidget,
  type WidgetType,
} from "../types/dashboard";

function SortableWidget({
  widget,
  periodDays,
  editing,
  onEdit,
  onRemove,
}: {
  widget: DashboardWidget;
  periodDays: number;
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
      {editing && (
        <button
          type="button"
          className="dash-drag-handle btn btn-secondary"
          {...attributes}
          {...listeners}
          aria-label="Перетащить"
        >
          <GripVertical size={16} />
        </button>
      )}
      <DashboardWidgetCard
        widget={widget}
        periodDays={periodDays}
        editing={editing}
        onEdit={onEdit}
        onRemove={onRemove}
      />
    </div>
  );
}

export default function DashboardPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [periodDays, setPeriodDays] = useState<DashboardPeriodDays>(getDashboardPeriodDays);
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
    const w: DashboardWidget = {
      id: newWidgetId(),
      type: "kpi" as WidgetType,
      title: "Новый виджет",
      metric: "calls_total",
      size: "small",
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

  const saveLayout = () => {
    saveMutation.mutate({ widgets });
  };

  if (isLoading && !widgets.length) return <p className="empty">Загрузка...</p>;

  return (
    <>
      <div className="dash-page-header">
        <h1 className="page-title" style={{ marginBottom: 0 }}>
          <LayoutGrid size={22} style={{ verticalAlign: "middle", marginRight: "0.4rem" }} />
          Дашборд
        </h1>
        <div className="dash-toolbar">
          <div className="filter-field dash-period-field">
            <label htmlFor="dash-period">Период</label>
            <select
              id="dash-period"
              value={periodDays}
              onChange={(e) => {
                const days = Number(e.target.value) as DashboardPeriodDays;
                setPeriodDays(days);
                setDashboardPeriodDays(days);
              }}
            >
              {DASHBOARD_PERIOD_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d} дней
                </option>
              ))}
            </select>
          </div>
          {!editing ? (
            <button type="button" className="btn btn-primary" onClick={() => setEditing(true)}>
              <Pencil size={16} />
              Конструктор
            </button>
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

      {editing && (
        <p className="dash-hint card" style={{ marginBottom: "1rem", padding: "0.75rem 1rem" }}>
          Режим конструктора: перетаскивайте виджеты, добавляйте метрики по звонкам, оценкам, длительности и
          операторам. Нажмите ⚙ для настройки.
        </p>
      )}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={widgets.map((w) => w.id)} strategy={rectSortingStrategy}>
          <div className="dash-grid">
            {widgets.map((w) => (
              <SortableWidget
                key={w.id}
                widget={w}
                periodDays={periodDays}
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
        <div className="card dash-catalog" style={{ marginTop: "1.5rem" }}>
          <h3 style={{ marginBottom: "0.75rem" }}>Доступные метрики</h3>
          <div className="dash-catalog-grid">
            {[...new Set(METRIC_OPTIONS.map((o) => o.category))].map((cat) => (
              <div key={cat}>
                <strong style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{cat}</strong>
                <ul style={{ marginTop: "0.35rem", paddingLeft: "1.1rem", fontSize: "0.875rem" }}>
                  {METRIC_OPTIONS.filter((o) => o.category === cat).map((o) => (
                    <li key={o.value}>{o.label}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
