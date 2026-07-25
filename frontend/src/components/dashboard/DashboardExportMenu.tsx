import { useEffect, useRef, useState } from "react";
import { Download } from "lucide-react";

type Props = {
  onExport: (format: "json" | "csv") => void;
  exporting?: boolean;
};

export default function DashboardExportMenu({ onExport, exporting }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const pick = (format: "json" | "csv") => {
    onExport(format);
    setOpen(false);
  };

  return (
    <div className="dash-export-menu" ref={rootRef}>
      <button
        type="button"
        className="btn btn-secondary btn-icon"
        onClick={() => setOpen((v) => !v)}
        disabled={exporting}
        aria-label="Экспорт данных"
        aria-expanded={open}
        aria-haspopup="menu"
        title="Экспорт"
      >
        <Download size={16} />
      </button>
      {open && (
        <div className="dash-export-dropdown" role="menu">
          <button type="button" role="menuitem" className="dash-export-option" onClick={() => pick("csv")}>
            CSV
          </button>
          <button type="button" role="menuitem" className="dash-export-option" onClick={() => pick("json")}>
            JSON
          </button>
        </div>
      )}
    </div>
  );
}
