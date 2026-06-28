"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  ApiError,
  adminActualizarGrado,
  adminCrearGrado,
  adminEliminarGrado,
  adminListarGrados,
  adminPromoverGrado,
  type GradoResumen,
} from "@/lib/api";
import { BotonPrimario, BotonSecundario, Campo, inputCls, ModalShell } from "@/components/admin/ui";

export default function GradosPage() {
  const [grados, setGrados] = useState<GradoResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [refresh, setRefresh] = useState(0);

  const [creando, setCreando] = useState(false);
  const [editar, setEditar] = useState<GradoResumen | null>(null);
  const [promover, setPromover] = useState(false);

  useEffect(() => {
    let activo = true;
    adminListarGrados()
      .then((g) => activo && setGrados(g))
      .catch((err) => activo && toast.error(err instanceof ApiError ? err.message : "Error al cargar"))
      .finally(() => activo && setCargando(false));
    return () => {
      activo = false;
    };
  }, [refresh]);

  const recargar = () => setRefresh((n) => n + 1);

  async function eliminar(g: GradoResumen) {
    if (!window.confirm(`¿Eliminar el grado "${g.nombre}"?`)) return;
    try {
      await adminEliminarGrado(g.id);
      toast.success("Grado eliminado");
      recargar();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo eliminar");
    }
  }

  return (
    <div className="px-9 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="text-2xl font-black text-slate-900">🏫 Grados</div>
          <div className="mt-1 text-sm font-bold text-slate-500">
            Define los grados del colegio y promueve estudiantes de año.
          </div>
        </div>
        <div className="flex gap-3">
          <BotonSecundario onClick={() => setPromover(true)}>⬆️ Promover año</BotonSecundario>
          <BotonPrimario onClick={() => setCreando(true)}>+ Agregar grado</BotonPrimario>
        </div>
      </div>

      <div className="overflow-hidden rounded-[16px] border border-slate-200 bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
        <div className="flex items-center border-b border-slate-100 px-5 py-3 text-[11px] font-extrabold uppercase tracking-wide text-slate-400">
          <div className="flex-1">Grado</div>
          <div className="w-[140px]">Nivel</div>
          <div className="w-[120px] text-center">Estudiantes</div>
          <div className="w-[110px] text-center">Docentes</div>
          <div className="w-[110px] text-right">Acciones</div>
        </div>
        {cargando && <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">Cargando…</div>}
        {!cargando && grados.length === 0 && (
          <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
            No hay grados. Agrega el primero.
          </div>
        )}
        {!cargando &&
          grados.map((g) => (
            <div key={g.id} className="flex items-center border-b border-slate-50 px-5 py-3.5 last:border-0">
              <div className="flex-1 text-sm font-extrabold text-slate-900">{g.nombre}</div>
              <div className="w-[140px] text-sm font-bold capitalize text-slate-500">{g.nivel}</div>
              <div className="w-[120px] text-center text-sm font-black text-slate-900">{g.cantidad_estudiantes}</div>
              <div className="w-[110px] text-center text-sm font-bold text-slate-500">{g.cantidad_docentes}</div>
              <div className="flex w-[110px] items-center justify-end gap-1.5">
                <IconBtn title="Editar" onClick={() => setEditar(g)}>✏️</IconBtn>
                <IconBtn title="Eliminar" onClick={() => eliminar(g)}>🗑️</IconBtn>
              </div>
            </div>
          ))}
      </div>

      {(creando || editar) && (
        <GradoModal
          grado={editar}
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
      {promover && (
        <PromoverModal
          grados={grados}
          onClose={() => setPromover(false)}
          onPromovido={() => {
            setPromover(false);
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

function GradoModal({
  grado,
  onClose,
  onGuardado,
}: {
  grado: GradoResumen | null;
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = grado != null;
  const [nombre, setNombre] = useState(grado?.nombre ?? "");
  const [guardando, setGuardando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!nombre.trim() || guardando) return;
    setGuardando(true);
    try {
      if (editando) await adminActualizarGrado(grado.id, nombre.trim());
      else await adminCrearGrado(nombre.trim());
      toast.success(editando ? "Grado actualizado" : "Grado creado");
      onGuardado();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo guardar");
      setGuardando(false);
    }
  }

  return (
    <ModalShell titulo={editando ? "Editar grado" : "Agregar grado"} onClose={guardando ? undefined : onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Campo label="Nombre del grado">
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Ej: 5to Primaria"
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

function PromoverModal({
  grados,
  onClose,
  onPromovido,
}: {
  grados: GradoResumen[];
  onClose: () => void;
  onPromovido: () => void;
}) {
  const [origen, setOrigen] = useState("");
  const [destino, setDestino] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!origen || !destino || origen === destino || guardando) return;
    setGuardando(true);
    try {
      const r = await adminPromoverGrado(Number(origen), Number(destino));
      toast.success(`${r.estudiantes_promovidos} estudiante(s) promovido(s)`);
      onPromovido();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo promover");
      setGuardando(false);
    }
  }

  return (
    <ModalShell titulo="Promover de año" onClose={guardando ? undefined : onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="rounded-xl bg-slate-50 px-4 py-3 text-[13px] font-bold text-slate-500">
          Mueve a <b>todos los estudiantes activos</b> del grado origen al grado destino.
        </div>
        <Campo label="Grado origen">
          <select value={origen} onChange={(e) => setOrigen(e.target.value)} className={inputCls}>
            <option value="">Selecciona…</option>
            {grados.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nombre} ({g.cantidad_estudiantes} est.)
              </option>
            ))}
          </select>
        </Campo>
        <Campo label="Grado destino">
          <select value={destino} onChange={(e) => setDestino(e.target.value)} className={inputCls}>
            <option value="">Selecciona…</option>
            {grados.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nombre}
              </option>
            ))}
          </select>
        </Campo>
        {origen && destino && origen === destino && (
          <div className="text-[13px] font-bold text-red-500">El origen y el destino deben ser distintos.</div>
        )}
        <div className="mt-1 flex justify-end gap-3">
          <BotonSecundario type="button" onClick={onClose} disabled={guardando}>
            Cancelar
          </BotonSecundario>
          <BotonPrimario type="submit" disabled={!origen || !destino || origen === destino || guardando}>
            {guardando ? "Promoviendo…" : "Promover"}
          </BotonPrimario>
        </div>
      </form>
    </ModalShell>
  );
}
