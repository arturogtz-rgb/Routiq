import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api from '@/lib/api';
import { DndContext, PointerSensor, useSensor, useSensors, closestCorners, DragOverlay } from '@dnd-kit/core';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import { Clock, AlertCircle, Plus } from 'lucide-react';
import { formatDateEs } from '@/lib/dates';

const COLUMNS = [
  { id: 'nueva_consulta', label: 'Nueva consulta', cls: 'kanban-col-nueva' },
  { id: 'cotizando', label: 'Cotizando', cls: 'kanban-col-cotizando' },
  { id: 'enviada', label: 'Enviada', cls: 'kanban-col-enviada' },
  { id: 'negociacion', label: 'En negociación', cls: 'kanban-col-negociacion' },
  { id: 'ganada', label: 'Ganada', cls: 'kanban-col-ganada' },
  { id: 'perdida', label: 'Perdida', cls: 'kanban-col-perdida' },
];

const STALE_DAYS = 3;

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

function Card({ q }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: q.id });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  const isStale = q.days_idle >= STALE_DAYS && !['ganada', 'perdida'].includes(q.state);
  return (
    <div
      ref={setNodeRef} style={style} {...listeners} {...attributes}
      className={`bg-white border border-ink-100 rounded-xl p-3 mb-3 shadow-sm hover:shadow-md transition-all cursor-grab active:cursor-grabbing ${isDragging ? 'opacity-40' : ''}`}
      data-testid={`kanban-card-${q.code}`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-xs text-brand-500 font-semibold">{q.code}</span>
        {isStale && (
          <span className="pill bg-red-100 text-red-700" title="Sin movimiento"><AlertCircle className="w-3 h-3" />{q.days_idle}d</span>
        )}
      </div>
      <p className="font-semibold text-ink-900 text-sm leading-tight">{q.client_snapshot?.name}</p>
      <p className="text-xs text-ink-500 mt-1 line-clamp-2">{q.package_snapshot?.name}</p>
      <div className="flex items-center justify-between mt-3 pt-2 border-t border-ink-100">
        <span className="text-[11px] text-ink-400 inline-flex items-center gap-1">
          <Clock className="w-3 h-3" />{q.dates?.start ? formatDateEs(q.dates.start) : formatDateEs(q.created_at)}
        </span>
        <span className="font-display font-semibold text-ink-900 text-sm">{money(q.total, q.currency)}</span>
      </div>
      <Link to={`/app/quotations/${q.id}`} className="text-xs text-brand-500 hover:underline mt-2 inline-block" data-testid={`open-quotation-${q.code}`}>Abrir →</Link>
    </div>
  );
}

function Column({ col, items }) {
  const { setNodeRef, isOver } = useDroppable({ id: col.id });
  return (
    <div
      ref={setNodeRef}
      className={`rounded-2xl p-4 min-w-[280px] md:min-w-0 ${col.cls} ${isOver ? 'ring-2 ring-brand-400' : ''} transition-all snap-start`}
      data-testid={`kanban-column-${col.id}`}
    >
      <div className="flex items-center justify-between mb-4 px-1">
        <h3 className="font-display font-semibold text-ink-900 text-sm">{col.label}</h3>
        <span className="pill bg-white/70 text-ink-700 border border-white">{items.length}</span>
      </div>
      <div className="space-y-0 min-h-[40px]">
        {items.map((q) => <Card key={q.id} q={q} />)}
        {items.length === 0 && <p className="text-xs text-ink-400 text-center py-6 italic">Arrastra aquí</p>}
      </div>
    </div>
  );
}

export default function Kanban() {
  const [quotations, setQuotations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const load = async () => {
    try {
      const { data } = await api.get('/quotations');
      setQuotations(data);
    } catch (_e) { /* noop */ }
  };
  useEffect(() => { load(); }, []);

  const onDragEnd = async (event) => {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;
    const card = quotations.find((q) => q.id === active.id);
    if (!card || card.state === over.id) return;
    const newState = over.id;
    setQuotations((prev) => prev.map((q) => q.id === card.id ? { ...q, state: newState } : q));
    try {
      await api.patch(`/quotations/${card.id}/state`, { state: newState });
    } catch (_e) {
      load();
    }
  };

  const active = quotations.find((q) => q.id === activeId);

  return (
    <AppShell>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Pipeline</h1>
          <p className="text-ink-500 mt-1">Arrastra las tarjetas para actualizar su estado.</p>
        </div>
        <Link to="/app/quotations/new" className="btn-primary" data-testid="kanban-new-btn"><Plus className="w-4 h-4" />Nueva cotización</Link>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCorners}
        onDragStart={(e) => setActiveId(e.active.id)} onDragCancel={() => setActiveId(null)}
        onDragEnd={onDragEnd}>
        <div className="flex md:grid md:grid-cols-6 gap-4 overflow-x-auto snap-x pb-4" data-testid="kanban-board">
          {COLUMNS.map((col) => (
            <Column key={col.id} col={col} items={quotations.filter((q) => q.state === col.id)} />
          ))}
        </div>
        <DragOverlay>
          {active ? (
            <div className="bg-white border-2 border-brand-400 rounded-xl p-3 shadow-2xl scale-105">
              <p className="font-mono text-xs text-brand-500 font-semibold">{active.code}</p>
              <p className="font-semibold text-ink-900 text-sm">{active.client_snapshot?.name}</p>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </AppShell>
  );
}
