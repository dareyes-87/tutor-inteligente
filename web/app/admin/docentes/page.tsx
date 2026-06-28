"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  ApiError,
  adminActualizarDocente,
  adminCrearDocente,
  adminListarDocentes,
  adminListarGrados,
  adminResetPasswordDocente,
  type DocenteResumen,
  type GradoResumen,
} from "@/lib/api";
import {
  BotonPrimario,
  BotonSecundario,
  Campo,
  EstadoBadge,
  inputCls,
  ModalShell,
  ResetPasswordModal,
} from "@/components/admin/ui";

export default function DocentesPage() {
  const [docentes, setDocentes] = useState<DocenteResumen[]>([]);
  const [grados, setGrados] = useState<GradoResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [refresh, setRefresh] = useState(0);

  const [editar, setEditar] = useState<DocenteResumen | null>(null);
  const [creando, setCreando] = useState(false);
  const [resetear, setResetear] = useState<DocenteResumen | null>(null);

  useEffect(() => {
    let activo = true;
    Promise.all([adminListarDocentes(), adminListarGrados()])
      .then(([d, g]) => {
        if (!activo) return;
        setDocentes(d);
        setGrados(g);
      })
      .catch((err) => activo && toast.error(err instanceof ApiError ? err.message : "Error al cargar"))
      .finally(() => activo && setCargando(false));
    return () => {
      activo = false;
    };
  }, [refresh]);

  const recargar = () => setRefresh((n) => n + 1);

  async function toggleActivo(d: DocenteResumen) {
    try {
      await adminActualizarDocente(d.id, { activo: !d.activo });
      toast.success(d.activo ? "Docente desactivado" : "Docente activado");
      recargar();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo actualizar");
    }
  }

  return (
    <div className="px-9 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="text-2xl font-black text-slate-900">👨‍🏫 Docentes</div>
          <div className="mt-1 text-sm font-bold text-slate-500">
            Registra y gestiona a los maestros del colegio.
          </div>
        </div>
        <BotonPrimario onClick={() => setCreando(true)}>+ Agregar docente</BotonPrimario>
      </div>

      <div className="overflow-hidden rounded-[16px] border border-slate-200 bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
        <div className="flex items-center border-b border-slate-100 px-5 py-3 text-[11px] font-extrabold uppercase tracking-wide text-slate-400">
          <div className="flex-1">Docente</div>
          <div className="w-[150px]">Usuario</div>
          <div className="w-[140px]">Grado</div>
          <div className="w-[70px] text-center">Libros</div>
          <div className="w-[90px] text-center">Estado</div>
          <div className="w-[150px] text-right">Acciones</div>
        </div>
        {cargando && <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">Cargando…</div>}
        {!cargando && docentes.length === 0 && (
          <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
            No hay docentes. Agrega el primero.
          </div>
        )}
        {!cargando &&
          docentes.map((d) => (
            <div key={d.id} className="flex items-center border-b border-slate-50 px-5 py-3.5 last:border-0">
              <div className="flex flex-1 items-center gap-3">
                <div className="grid h-9 w-9 flex-none place-items-center rounded-full bg-slate-800 text-sm font-black text-white">
                  {d.nombre[0]}
                  {d.apellido[0]}
                </div>
                <span className="text-sm font-extrabold text-slate-900">
                  {d.nombre} {d.apellido}
                </span>
              </div>
              <div className="w-[150px] text-sm font-bold text-slate-500">{d.username}</div>
              <div className="w-[140px] text-sm font-bold text-slate-500">{d.grado ?? "—"}</div>
              <div className="w-[70px] text-center text-sm font-black text-slate-900">{d.libros_subidos}</div>
              <div className="w-[90px] text-center">
                <EstadoBadge activo={d.activo} />
              </div>
              <div className="flex w-[150px] items-center justify-end gap-1.5">
                <IconBtn title="Editar" onClick={() => setEditar(d)}>✏️</IconBtn>
                <IconBtn title="Resetear contraseña" onClick={() => setResetear(d)}>🔑</IconBtn>
                <IconBtn title={d.activo ? "Desactivar" : "Activar"} onClick={() => toggleActivo(d)}>
                  {d.activo ? "🚫" : "✅"}
                </IconBtn>
              </div>
            </div>
          ))}
      </div>

      {(creando || editar) && (
        <DocenteModal
          docente={editar}
          grados={grados}
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
      {resetear && (
        <ResetPasswordModal
          nombre={`${resetear.nombre} ${resetear.apellido}`}
          onClose={() => setResetear(null)}
          onConfirm={async (nueva) => {
            try {
              await adminResetPasswordDocente(resetear.id, nueva);
              toast.success("Contraseña actualizada");
              setResetear(null);
            } catch (err) {
              toast.error(err instanceof ApiError ? err.message : "No se pudo resetear");
            }
          }}
        />
      )}
    </div>
  );
}

function IconBtn({
  children,
  title,
  onClick,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
}) {
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

function DocenteModal({
  docente,
  grados,
  onClose,
  onGuardado,
}: {
  docente: DocenteResumen | null;
  grados: GradoResumen[];
  onClose: () => void;
  onGuardado: () => void;
}) {
  const editando = docente != null;
  const [nombre, setNombre] = useState(docente?.nombre ?? "");
  const [apellido, setApellido] = useState(docente?.apellido ?? "");
  const [username, setUsername] = useState(docente?.username ?? "");
  const [password, setPassword] = useState("");
  const [gradoId, setGradoId] = useState<string>(docente?.grado_id != null ? String(docente.grado_id) : "");
  const [guardando, setGuardando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!nombre.trim() || !apellido.trim() || guardando) return;
    if (!editando && (!username.trim() || !password.trim())) return;
    setGuardando(true);
    try {
      const grado_id = gradoId ? Number(gradoId) : null;
      if (editando) {
        await adminActualizarDocente(docente.id, { nombre: nombre.trim(), apellido: apellido.trim(), grado_id });
      } else {
        await adminCrearDocente({
          nombre: nombre.trim(), apellido: apellido.trim(),
          username: username.trim(), password: password.trim(), grado_id,
        });
      }
      toast.success(editando ? "Docente actualizado" : "Docente creado");
      onGuardado();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo guardar");
      setGuardando(false);
    }
  }

  return (
    <ModalShell titulo={editando ? "Editar docente" : "Agregar docente"} onClose={guardando ? undefined : onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-4">
          <Campo label="Nombre">
            <input value={nombre} onChange={(e) => setNombre(e.target.value)} className={inputCls} />
          </Campo>
          <Campo label="Apellido">
            <input value={apellido} onChange={(e) => setApellido(e.target.value)} className={inputCls} />
          </Campo>
        </div>
        {!editando && (
          <div className="grid grid-cols-2 gap-4">
            <Campo label="Usuario">
              <input value={username} onChange={(e) => setUsername(e.target.value)} className={inputCls} />
            </Campo>
            <Campo label="Contraseña">
              <input value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
            </Campo>
          </div>
        )}
        <Campo label="Grado (opcional)">
          <select value={gradoId} onChange={(e) => setGradoId(e.target.value)} className={inputCls}>
            <option value="">Sin grado asignado</option>
            {grados.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <div className="mt-2 flex justify-end gap-3">
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
