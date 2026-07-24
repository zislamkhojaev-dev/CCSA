import { useCallback, useState } from "react";
import { X } from "lucide-react";
import SearchableSelect, { type SearchableOption } from "./SearchableSelect";
import { api } from "../api/client";

export type OperatorItem = { id: number; name: string };

type PaginatedOps = { items: { id: number; full_name: string }[] };

type OperatorMultiPickerProps = {
  value: OperatorItem[];
  onChange: (value: OperatorItem[]) => void;
  disabled?: boolean;
};

async function fetchOperatorOptions(query: string): Promise<SearchableOption[]> {
  const data = await api.get<PaginatedOps>("/operators?page=1&page_size=100");
  const q = query.trim().toLowerCase();
  return data.items
    .filter((op) => !q || op.full_name.toLowerCase().includes(q))
    .map((op) => ({ id: op.id, label: op.full_name }));
}

export default function OperatorMultiPicker({ value, onChange, disabled }: OperatorMultiPickerProps) {
  const [pickerKey, setPickerKey] = useState(0);

  const fetchOptions = useCallback(
    async (q: string) => {
      const items = await fetchOperatorOptions(q);
      const selectedIds = new Set(value.map((o) => o.id));
      return items.filter((o) => !selectedIds.has(o.id));
    },
    [value],
  );

  const addOperator = (opt: SearchableOption) => {
    if (value.some((o) => o.id === opt.id)) return;
    onChange([...value, { id: opt.id, name: opt.label }]);
    setPickerKey((k) => k + 1);
  };

  const removeOperator = (id: number) => {
    onChange(value.filter((o) => o.id !== id));
  };

  return (
    <div className="operator-multi-picker">
      {value.length > 0 && (
        <div className="tag-chips">
          {value.map((op) => (
            <span key={op.id} className="tag-chip">
              {op.name}
              {!disabled && (
                <button
                  type="button"
                  className="tag-chip-remove"
                  onClick={() => removeOperator(op.id)}
                  aria-label={`Удалить ${op.name}`}
                >
                  <X size={12} />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {!disabled && (
        <SearchableSelect
          key={pickerKey}
          value={null}
          onChange={() => {}}
          onSelectOption={addOperator}
          placeholder="Добавить оператора…"
          emptyLabel="Все операторы"
          allowClear={false}
          fetchOptions={fetchOptions}
        />
      )}
    </div>
  );
}
