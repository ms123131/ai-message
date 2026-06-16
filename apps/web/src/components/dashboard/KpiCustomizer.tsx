import { useEffect, useState } from "react";
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
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Eye, EyeOff, GripVertical } from "lucide-react";
import { Dialog } from "../ui/Dialog";
import { Button } from "../ui/Button";
import {
  KPI_BY_ID,
  KPI_GROUP_LABEL,
  resolveKpiOrder,
  type KpiGroup,
} from "./kpiRegistry";

export function KpiCustomizer({
  open,
  onClose,
  order,
  hidden,
  onSave,
  saving,
}: {
  open: boolean;
  onClose: () => void;
  order: string[];
  hidden: string[];
  onSave: (next: { order: string[]; hidden: string[] }) => void;
  saving?: boolean;
}) {
  const [localOrder, setLocalOrder] = useState<string[]>(order);
  const [localHidden, setLocalHidden] = useState<string[]>(hidden);

  // Пересинхронизируемся с сервером при каждом открытии.
  useEffect(() => {
    if (open) {
      setLocalOrder(resolveKpiOrder(order));
      setLocalHidden(hidden);
    }
  }, [open, order, hidden]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  function handleDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setLocalOrder((prev) => {
      const from = prev.indexOf(String(active.id));
      const to = prev.indexOf(String(over.id));
      if (from === -1 || to === -1) return prev;
      return arrayMove(prev, from, to);
    });
  }

  function toggleHidden(id: string) {
    setLocalHidden((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function reset() {
    setLocalOrder(resolveKpiOrder(undefined));
    setLocalHidden([]);
  }

  const visibleCount = localOrder.filter((id) => !localHidden.includes(id))
    .length;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Настройка показателей"
      description="Перетащите карточки, чтобы изменить порядок. Глазок скрывает метрику."
      size="md"
    >
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={localOrder}
          strategy={verticalListSortingStrategy}
        >
          <ul className="max-h-[50vh] space-y-1 overflow-y-auto pr-1">
            {localOrder.map((id) => {
              const d = KPI_BY_ID[id];
              if (!d) return null;
              return (
                <SortableRow
                  key={id}
                  id={id}
                  label={d.label}
                  group={d.group}
                  hidden={localHidden.includes(id)}
                  onToggle={() => toggleHidden(id)}
                />
              );
            })}
          </ul>
        </SortableContext>
      </DndContext>

      <div className="mt-4 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={reset}
          className="text-xs text-slate-500 hover:text-slate-800 hover:underline"
        >
          Сбросить по умолчанию
        </button>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">
            Показано {visibleCount} из {localOrder.length}
          </span>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Отмена
          </Button>
          <Button
            onClick={() =>
              onSave({ order: localOrder, hidden: localHidden })
            }
            disabled={saving}
          >
            {saving ? "Сохраняю…" : "Сохранить"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

const GROUP_CHIP: Record<KpiGroup, string> = {
  volume: "bg-sky-50 text-sky-600",
  quality: "bg-emerald-50 text-emerald-600",
  crm: "bg-violet-50 text-violet-600",
};

function SortableRow({
  id,
  label,
  group,
  hidden,
  onToggle,
}: {
  id: string;
  label: string;
  group: KpiGroup;
  hidden: boolean;
  onToggle: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <li
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 rounded-md border bg-white px-2 py-1.5 ${
        isDragging
          ? "border-brand-300 shadow-sm"
          : "border-slate-200"
      } ${hidden ? "opacity-50" : ""}`}
    >
      <button
        type="button"
        className="cursor-grab touch-none text-slate-400 hover:text-slate-600 active:cursor-grabbing"
        aria-label="Перетащить"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <span className="flex-1 truncate text-sm text-slate-700">{label}</span>
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${GROUP_CHIP[group]}`}
      >
        {KPI_GROUP_LABEL[group]}
      </span>
      <button
        type="button"
        onClick={onToggle}
        aria-label={hidden ? "Показать" : "Скрыть"}
        title={hidden ? "Показать" : "Скрыть"}
        className="text-slate-400 transition hover:text-slate-700"
      >
        {hidden ? (
          <EyeOff className="h-4 w-4" />
        ) : (
          <Eye className="h-4 w-4" />
        )}
      </button>
    </li>
  );
}
