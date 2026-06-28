"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  ApiError,
  adminActualizarAsignatura,
  adminCrearAsignatura,
  adminEliminarAsignatura,
  adminListarAsignaturas,
  type AsignaturaResumen,
} from "@/lib/api";
import { BotonPrimario, BotonSecundario, Campo, inputCls, ModalShell } from "@/components/admin/ui";

export default function AsignaturasPage() {
  const [asignaturas, setAsignaturas] = useState<AsignaturaResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [refresh, setRefresh] = useState(0);

  const [creando, setCreando] = useState(false);
  const [editar, setEditar] = useState<AsignaturaResumen | null>(null);

  useEffect(() => {
    let activo = true;
    adminListarAsignaturas()
      .then((a) => activo && setAsignaturas(a))
      .catch((err) => activo && toast.error(err instanceof ApiError ? err.message : "Error al cargar"))
      .finally(() => activo && setCargando(false));
    return () => {
      activo = false;
    };
  }, [refresh]);

  const recargar = () => setRefresh((n) => n + 1);

  async function eliminar(a: AsignaturaResumen) {
    if (!window.confirm(`¿Eliminar la asignatura "${a.nombre}"?`)) return;
    try {
      await adminEliminarAsignatura(a.id);
      toast.success("Asignatura eliminada");
      recargar();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo eliminar");
    }
  }

  return (
    <div className="px-9 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="text-2xl font-black text-slate-900">📚 Asignaturas</div>
          <div className="mt-1 text-sm font-bold text-slate-500">
            Las materias que el colegio imparte y para las que se suben libros.
          </div>
        </div>
        <BotonPrimario onClick={() => setCreando(true)}>+ Agregar asignatura</BotonPrimario>
      </div>

      <div className="overflow-hidden rounded-[16px] border border-slate-200 bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
        <div className="flex items-center border-b border-slate-100 px-5 py-3 text-[11px] font-extrabold uppercase tracking-wide text-slate-400">
          <div className="flex-1">Asignatura</div>
          <div className="w-[120px] text-center">Libros</div>
          <div className="w-[110px] text-right">Acciones</div>
        </div>
        {cargando && <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">Cargando…</div>}
        {!cargando && asignaturas.length === 0 && (
          <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
            No hay asignaturas. Agrega la primera.
          </div>
        )}
        {!cargando &&
          asignaturas.map((a) => (
            <div key={a.id} className="flex items-center border-b border-slate-50 px-5 py-3.5 last:border-0">
              <div className="flex-1 text-sm font-extrabold text-slate-900">{a.nombre}</div>
              <div className="w-[120px] text-center text-sm font-black text-slate-900">{a.cantidad_libros}</div>
              <div className="flex w-[110px] items-center justify-end gap-1.5">
                <IconBtn title="Editar" onClick={() => setEditar(a)}>✏️</IconBtn>
                <IconBtn title="Eliminar" onClick={() => eliminar(a)}>🗑️</IconBtn>
              </div>
            </div>
          ))}
      </div>

      {(creando || editar) && (
        <AsignaturaModal
          asignatura={editar}
          onClose={() => {
            setCreando(false);
            setEditar(null);
          }}
          onGuardado={() => {
            setCreando(false);
            setEditar(null);
            recargar();
          }}
        />
      )}
    </div>
  );
}

function IconBtn({ children, title, onClick }: { children: React.ReactNode; title: string; onClick: () => void }) {
  return (
    <button
      title={title}
      onClick={onClick}
      className="grid h-8 w-8 place-items-center rounded-lg bg-slate-100 text-sm hover:bg-slate-200"
    >
      {children}
    </button>
  );
}

function AsignaturaModal({
  asignatura,
  onClose,
  onGuardado,
}: {
  asignatura: AsignaturaResumen | null;
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = asignatura != null;
  const [nombre, setNombre] = useState(asignatura?.nombre ?? "");
  const [guardando, setGuardando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!nombre.trim() || guardando) return;
    setGuardando(true);
    try {
      if (editando) await adminActualizarAsignatura(asignatura.id, nombre.trim());
      else await adminCrearAsignatura(nombre.trim());
      toast.success(editando ? "Asignatura actualizada" : "Asignatura creada");
      onGuardado();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo guardar");
      setGuardando(false);
    }
  }

  return (
    <ModalShell titulo={editando ? "Editar asignatura" : "Agregar asignatura"} onClose={guardando ? undefined : onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Campo label="Nombre de la asignatura">
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Ej: Comunicación y Lenguaje"
            className={inputCls}
            autoFocus
          />
        </Campo>
        <div className="mt-1 flex justify-end gap-3">
          <BotonSecundario type="button" onClick={onClose} disabled={guardando}>
            Cancelar
          </BotonSecundario>
          <BotonPrimario type="submit" disabled={guardando}>
            {guardando ? "Guardando…" : editando ? "Guardar" : "Crear"}
          </BotonPrimario>
        </div>
      </form>
    </ModalShell>
  );
}
