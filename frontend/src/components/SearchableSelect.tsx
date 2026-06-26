import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, X } from "lucide-react";

export type SearchableOption = { id: number; label: string };

type SearchableSelectProps = {
  id?: string;
  value: number | null;
  onChange: (value: number | null) => void;
  onSelectOption?: (option: SearchableOption) => void;
  placeholder?: string;
  emptyLabel?: string;
  allowClear?: boolean;
  disabled?: boolean;
  fetchOptions: (query: string) => Promise<SearchableOption[]>;
  onCreateOption?: (name: string) => Promise<SearchableOption | null>;
};

export default function SearchableSelect({
  id,
  value,
  onChange,
  onSelectOption,
  placeholder = "Поиск…",
  emptyLabel = "Все",
  allowClear = true,
  disabled = false,
  fetchOptions,
  onCreateOption,
}: SearchableSelectProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const rootRef = useRef<HTMLDivElement>(null);
  const controlRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<SearchableOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [listStyle, setListStyle] = useState<React.CSSProperties>({});

  const updateListPosition = useCallback(() => {
    const el = controlRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setListStyle({
      position: "fixed",
      top: rect.bottom + 2,
      left: rect.left,
      width: rect.width,
    });
  }, []);

  const loadOptions = useCallback(
    async (q: string) => {
      setLoading(true);
      try {
        const items = await fetchOptions(q);
        setOptions(items);
      } finally {
        setLoading(false);
      }
    },
    [fetchOptions],
  );

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      void loadOptions(query);
    }, 200);
    return () => window.clearTimeout(timer);
  }, [open, query, loadOptions]);

  useEffect(() => {
    if (value == null) {
      setSelectedLabel(null);
      return;
    }
    const match = options.find((o) => o.id === value);
    if (match) {
      setSelectedLabel(match.label);
      return;
    }
    void fetchOptions("").then((items) => {
      const found = items.find((o) => o.id === value);
      if (found) setSelectedLabel(found.label);
    });
  }, [value, options, fetchOptions]);

  useEffect(() => {
    if (!open) return;
    updateListPosition();
    const onScrollOrResize = () => updateListPosition();
    window.addEventListener("resize", onScrollOrResize);
    window.addEventListener("scroll", onScrollOrResize, true);
    return () => {
      window.removeEventListener("resize", onScrollOrResize);
      window.removeEventListener("scroll", onScrollOrResize, true);
    };
  }, [open, updateListPosition]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (listRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const displayValue = open ? query : selectedLabel ?? "";

  const pick = (opt: SearchableOption) => {
    onChange(opt.id);
    onSelectOption?.(opt);
    setSelectedLabel(opt.label);
    setQuery("");
    setOpen(false);
  };

  const clear = () => {
    onChange(null);
    setSelectedLabel(null);
    setQuery("");
  };

  const trimmed = query.trim();
  const canCreate =
    onCreateOption &&
    trimmed.length > 0 &&
    !options.some((o) => o.label.toLowerCase() === trimmed.toLowerCase());

  const handleCreate = async () => {
    if (!onCreateOption || !trimmed) return;
    const created = await onCreateOption(trimmed);
    if (created) pick(created);
  };

  const listContent = (
    <ul ref={listRef} className="searchable-select-list" style={listStyle} role="listbox">
      {allowClear && (
        <li>
          <button type="button" className="searchable-select-option" onMouseDown={(e) => e.preventDefault()} onClick={clear}>
            {emptyLabel}
          </button>
        </li>
      )}
      {loading && <li className="searchable-select-hint">Загрузка…</li>}
      {!loading && options.length === 0 && !canCreate && (
        <li className="searchable-select-hint">Ничего не найдено</li>
      )}
      {options.map((opt) => (
        <li key={opt.id}>
          <button
            type="button"
            className={`searchable-select-option${value === opt.id ? " searchable-select-option--active" : ""}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => pick(opt)}
          >
            {opt.label}
          </button>
        </li>
      ))}
      {canCreate && (
        <li>
          <button
            type="button"
            className="searchable-select-option searchable-select-option--create"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => void handleCreate()}
          >
            Создать «{trimmed}»
          </button>
        </li>
      )}
    </ul>
  );

  return (
    <div ref={rootRef} className={`searchable-select${open ? " searchable-select--open" : ""}`}>
      <div ref={controlRef} className="searchable-select-control">
        <input
          id={inputId}
          type="text"
          className="searchable-select-input"
          placeholder={value == null && !open ? emptyLabel : placeholder}
          value={displayValue}
          disabled={disabled}
          autoComplete="off"
          onFocus={() => {
            setOpen(true);
            if (!open && selectedLabel) setQuery("");
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
        />
        {allowClear && value != null && !disabled && (
          <button
            type="button"
            className="searchable-select-clear"
            onClick={clear}
            aria-label="Сбросить"
            tabIndex={-1}
          >
            <X size={14} />
          </button>
        )}
        <ChevronDown size={16} className="searchable-select-chevron" aria-hidden />
      </div>
      {open && createPortal(listContent, document.body)}
    </div>
  );
}
