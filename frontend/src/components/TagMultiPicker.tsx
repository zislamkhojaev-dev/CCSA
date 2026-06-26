import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import SearchableSelect, { type SearchableOption } from "./SearchableSelect";
import { createTag, fetchTagOptions } from "./TagMultiPicker.utils";

export type TagItem = { id: number; name: string };

type TagMultiPickerProps = {
  value: TagItem[];
  onChange: (value: TagItem[]) => void;
  disabled?: boolean;
};

export default function TagMultiPicker({ value, onChange, disabled }: TagMultiPickerProps) {
  const qc = useQueryClient();
  const [pickerKey, setPickerKey] = useState(0);

  const fetchOptions = useCallback(
    async (q: string) => {
      const items = await fetchTagOptions(q);
      const selectedIds = new Set(value.map((t) => t.id));
      return items.filter((o) => !selectedIds.has(o.id));
    },
    [value],
  );

  const handleCreate = useCallback(
    async (name: string) => {
      const created = await createTag(name);
      if (created) {
        qc.invalidateQueries({ queryKey: ["tags"] });
        qc.invalidateQueries({ queryKey: ["research-filter-options"] });
      }
      return created;
    },
    [qc],
  );

  const addTag = (opt: SearchableOption) => {
    if (value.some((t) => t.id === opt.id)) return;
    onChange([...value, { id: opt.id, name: opt.label }]);
    setPickerKey((k) => k + 1);
  };

  const removeTag = (id: number) => {
    onChange(value.filter((t) => t.id !== id));
  };

  return (
    <div className="tag-multi-picker">
      {value.length > 0 && (
        <div className="tag-chips">
          {value.map((t) => (
            <span key={t.id} className="tag-chip">
              {t.name}
              {!disabled && (
                <button
                  type="button"
                  className="tag-chip-remove"
                  onClick={() => removeTag(t.id)}
                  aria-label={`Удалить ${t.name}`}
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
          onSelectOption={addTag}
          placeholder="Добавить тег…"
          emptyLabel="Выберите тег"
          allowClear={false}
          fetchOptions={fetchOptions}
          onCreateOption={async (name) => {
            const created = await handleCreate(name);
            if (created) addTag(created);
            return created;
          }}
        />
      )}
    </div>
  );
}

export { fetchTagOptions, createTag } from "./TagMultiPicker.utils";
