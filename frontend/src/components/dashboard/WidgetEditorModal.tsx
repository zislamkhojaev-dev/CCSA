import { useEffect, useState } from "react";
import {
  METRIC_OPTIONS,
  WIDGET_TYPES,
  allowedWidgetTypes,
  clampWidgetHeight,
  clampWidgetWidth,
  defaultWidgetType,
  formatWidgetDimensions,
  suggestedWidgetDimensions,
  widgetSizeHint,
  type DashboardWidget,
  type WidgetHeight,
  type WidgetType,
  type WidgetWidth,
} from "../../types/dashboard";

type Props = {
  widget: DashboardWidget | null;
  onSave: (widget: DashboardWidget) => void;
  onClose: () => void;
};

const WIDTH_OPTIONS: { value: WidgetWidth; label: string }[] = [
  { value: 1, label: "1 — ¼ ширины" },
  { value: 2, label: "2 — ½ ширины" },
  { value: 3, label: "3 — ¾ ширины" },
  { value: 4, label: "4 — на всю ширину" },
];

const HEIGHT_OPTIONS: { value: WidgetHeight; label: string }[] = [
  { value: 1, label: "1 — стандартная" },
  { value: 2, label: "2 — высокая" },
];

export default function WidgetEditorModal({ widget, onSave, onClose }: Props) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState<WidgetType>("kpi");
  const [metric, setMetric] = useState("calls_total");
  const [width, setWidth] = useState<WidgetWidth>(2);
  const [height, setHeight] = useState<WidgetHeight>(1);

  useEffect(() => {
    if (widget) {
      setTitle(widget.title);
      const allowed = allowedWidgetTypes(widget.metric);
      setType(allowed.includes(widget.type) ? widget.type : allowed[0]);
      setMetric(widget.metric);
      setWidth(clampWidgetWidth(widget.width));
      setHeight(clampWidgetHeight(widget.height));
    }
  }, [widget]);

  if (!widget) return null;

  const typeOptions = WIDGET_TYPES.filter((t) => allowedWidgetTypes(metric).includes(t.value));

  const handleMetricChange = (m: string) => {
    setMetric(m);
    const opt = METRIC_OPTIONS.find((o) => o.value === m);
    if (opt && !title.trim()) setTitle(opt.label);
    const nextType = defaultWidgetType(m);
    setType(nextType);
    const dims = suggestedWidgetDimensions(m, nextType);
    setWidth(dims.width);
    setHeight(dims.height);
  };

  const handleTypeChange = (nextType: WidgetType) => {
    setType(nextType);
    const dims = suggestedWidgetDimensions(metric, nextType);
    setWidth(dims.width);
    setHeight(dims.height);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      ...widget,
      title: title.trim() || metric,
      type,
      metric,
      width: clampWidgetWidth(width),
      height: clampWidgetHeight(height),
    });
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
            <label>Тип отображения</label>
            <select
              value={type}
              onChange={(e) => handleTypeChange(e.target.value as WidgetType)}
              disabled={typeOptions.length <= 1}
            >
              {typeOptions.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            {typeOptions.length <= 1 && (
              <p className="form-hint">Для этой метрики доступен один вид отображения.</p>
            )}
          </div>
          <div className="form-row form-row--2">
            <div className="form-group">
              <label>Ширина (1–4)</label>
              <select
                value={width}
                onChange={(e) => setWidth(clampWidgetWidth(Number(e.target.value)))}
              >
                {WIDTH_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Высота (1–2)</label>
              <select
                value={height}
                onChange={(e) => setHeight(clampWidgetHeight(Number(e.target.value)))}
              >
                {HEIGHT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="form-hint">
            Сейчас: {formatWidgetDimensions(width, height)}. Рекомендуется: {widgetSizeHint(metric, type)}
          </p>
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
