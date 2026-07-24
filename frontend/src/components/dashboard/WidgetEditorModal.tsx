import { useEffect, useState } from "react";
import {
  METRIC_OPTIONS,
  WIDGET_TYPES,
  type DashboardWidget,
  type WidgetSize,
  type WidgetType,
} from "../../types/dashboard";

type Props = {
  widget: DashboardWidget | null;
  onSave: (widget: DashboardWidget) => void;
  onClose: () => void;
};

export default function WidgetEditorModal({ widget, onSave, onClose }: Props) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState<WidgetType>("kpi");
  const [metric, setMetric] = useState("calls_total");
  const [size, setSize] = useState<WidgetSize>("small");

  useEffect(() => {
    if (widget) {
      setTitle(widget.title);
      setType(widget.type);
      setMetric(widget.metric);
      setSize(widget.size);
    }
  }, [widget]);

  if (!widget) return null;

  const handleMetricChange = (m: string) => {
    setMetric(m);
    const opt = METRIC_OPTIONS.find((o) => o.value === m);
    if (opt && !title.trim()) setTitle(opt.label);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({ ...widget, title: title.trim() || metric, type, metric, size });
    onClose();
  };

  const categories = [...new Set(METRIC_OPTIONS.map((o) => o.category))];

  return (
    <div className="dash-modal-backdrop" onClick={onClose} role="presentation">
      <div className="card dash-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-labelledby="widget-editor-title">
        <h2 id="widget-editor-title" className="modal-title">
          Настройка виджета
        </h2>
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Заголовок</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Тип отображения</label>
            <select value={type} onChange={(e) => setType(e.target.value as WidgetType)}>
              {WIDGET_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Источник данных</label>
            <select value={metric} onChange={(e) => handleMetricChange(e.target.value)}>
              {categories.map((cat) => (
                <optgroup key={cat} label={cat}>
                  {METRIC_OPTIONS.filter((o) => o.category === cat).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Размер</label>
            <select value={size} onChange={(e) => setSize(e.target.value as WidgetSize)}>
              <option value="small">Малый</option>
              <option value="medium">Средний</option>
              <option value="large">Большой</option>
            </select>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="btn btn-primary">
              Применить
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
