"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  ApiError,
  adminActualizarEstudiante,
  adminCrearEstudiante,
  adminImportarEstudiantes,
  adminListarEstudiantes,
  adminListarGrados,
  adminResetPasswordEstudiante,
  type EstudianteAdminResumen,
  type EstudianteCreado,
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

export default function EstudiantesAdminPage() {
  const [estudiantes, setEstudiantes] = useState<EstudianteAdminResumen[]>([]);
  const [grados, setGrados] = useState<GradoResumen[]>([]);
  const [filtroGrado, setFiltroGrado] = useState<string>("");
  const [cargando, setCargando] = useState(true);
  const [refresh, setRefresh] = useState(0);

  const [creando, setCreando] = useState(false);
  const [editar, setEditar] = useState<EstudianteAdminResumen | null>(null);
  const [resetear, setResetear] = useState<EstudianteAdminResumen | null>(null);
  const [importar, setImportar] = useState(false);
  const [credenciales, setCredenciales] = useState<EstudianteCreado[] | null>(null);

  useEffect(() => {
    let activo = true;
    const params = filtroGrado ? { grado_id: Number(filtroGrado) } : undefined;
    Promise.all([adminListarEstudiantes(params), adminListarGrados()])
      .then(([e, g]) => {
        if (!activo) return;
        setEstudiantes(e);
        setGrados(g);
      })
      .catch((err) => activo && toast.error(err instanceof ApiError ? err.message : "Error al cargar"))
      .finally(() => activo && setCargando(false));
    return () => {
      activo = false;
    };
  }, [refresh, filtroGrado]);

  const recargar = () => setRefresh((n) => n + 1);

  async function toggleActivo(e: EstudianteAdminResumen) {
    try {
      await adminActualizarEstudiante(e.id, { activo: !e.activo });
      toast.success(e.activo ? "Estudiante desactivado" : "Estudiante activado");
      recargar();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo actualizar");
    }
  }

  return (
    <div className="px-9 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <div className="text-2xl font-black text-slate-900">👩‍🎓 Estudiantes</div>
          <div className="mt-1 text-sm font-bold text-slate-500">
            Gestiona inscripciones, grados y credenciales.
          </div>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={filtroGrado}
            onChange={(e) => {
              setCargando(true);
              setFiltroGrado(e.target.value);
            }}
            className="rounded-xl border-2 border-slate-200 bg-white px-4 py-2.5 text-sm font-extrabold text-slate-700 outline-none"
          >
            <option value="">Todos los grados</option>
            {grados.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nombre}
              </option>
            ))}
          </select>
          <BotonSecundario onClick={() => setImportar(true)}>📥 Importar CSV</BotonSecundario>
          <BotonPrimario onClick={() => setCreando(true)}>+ Agregar</BotonPrimario>
        </div>
      </div>

      <div className="overflow-hidden rounded-[16px] border border-slate-200 bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
        <div className="flex items-center border-b border-slate-100 px-5 py-3 text-[11px] font-extrabold uppercase tracking-wide text-slate-400">
          <div className="flex-1">Estudiante</div>
          <div className="w-[130px]">Usuario</div>
          <div className="w-[130px]">Grado</div>
          <div className="w-[150px]">Progreso</div>
          <div className="w-[90px] text-center">Estado</div>
          <div className="w-[120px] text-right">Acciones</div>
        </div>
        {cargando && <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">Cargando…</div>}
        {!cargando && estudiantes.length === 0 && (
          <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
            No hay estudiantes en este filtro.
          </div>
        )}
        {!cargando &&
          estudiantes.map((e) => (
            <div key={e.id} className="flex items-center border-b border-slate-50 px-5 py-3.5 last:border-0">
              <div className="flex flex-1 items-center gap-3">
                <div className="grid h-9 w-9 flex-none place-items-center rounded-full bg-slate-800 text-sm font-black text-white">
                  {e.nombre[0]}
                  {e.apellido[0]}
                </div>
                <span className="text-sm font-extrabold text-slate-900">
                  {e.nombre} {e.apellido}
                </span>
              </div>
              <div className="w-[130px] text-sm font-bold text-slate-500">{e.username}</div>
              <div className="w-[130px] text-sm font-bold text-slate-500">{e.grado ?? "—"}</div>
              <div className="flex w-[150px] items-center gap-2.5">
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-slate-700" style={{ width: `${Math.min(100, e.progreso)}%` }} />
                </div>
                <span className="w-9 text-xs font-extrabold text-slate-600">{Math.round(e.progreso)}%</span>
              </div>
              <div className="w-[90px] text-center">
                <EstadoBadge activo={e.activo} />
              </div>
              <div className="flex w-[120px] items-center justify-end gap-1.5">
                <IconBtn title="Editar / cambiar grado" onClick={() => setEditar(e)}>✏️</IconBtn>
                <IconBtn title="Resetear contraseña" onClick={() => setResetear(e)}>🔑</IconBtn>
                <IconBtn title={e.activo ? "Desactivar" : "Activar"} onClick={() => toggleActivo(e)}>
                  {e.activo ? "🚫" : "✅"}
                </IconBtn>
              </div>
            </div>
          ))}
      </div>

      {(creando || editar) && (
        <EstudianteModal
          estudiante={editar}
          grados={grados}
          onClose={() => {
            setCreando(false);
            setEditar(null);
          }}
          onCreado={(cred) => {
            setCreando(false);
            setEditar(null);
            recargar();
            if (cred) setCredenciales([cred]);
          }}
        />
      )}
      {resetear && (
        <ResetPasswordModal
          nombre={`${resetear.nombre} ${resetear.apellido}`}
          onClose={() => setResetear(null)}
          onConfirm={async (nueva) => {
            try {
              await adminResetPasswordEstudiante(resetear.id, nueva);
              toast.success("Contraseña actualizada");
              setResetear(null);
            } catch (err) {
              toast.error(err instanceof ApiError ? err.message : "No se pudo resetear");
            }
          }}
        />
      )}
      {importar && (
        <ImportarModal
          onClose={() => setImportar(false)}
          onImportado={(creds) => {
            setImportar(false);
            recargar();
            setCredenciales(creds);
          }}
        />
      )}
      {credenciales && (
        <CredencialesModal credenciales={credenciales} onClose={() => setCredenciales(null)} />
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

function EstudianteModal({
  estudiante,
  grados,
  onClose,
  onCreado,
}: {
  estudiante: EstudianteAdminResumen | null;
  grados: GradoResumen[];
  onClose: () => void;
  onCreado: (cred: EstudianteCreado | null) => void;
}) {
  const editando = estudiante != null;
  const [nombre, setNombre] = useState(estudiante?.nombre ?? "");
  const [apellido, setApellido] = useState(estudiante?.apellido ?? "");
  const [gradoId, setGradoId] = useState<string>(estudiante?.grado_id != null ? String(estudiante.grado_id) : "");
  const [guardando, setGuardando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!nombre.trim() || !apellido.trim() || guardando) return;
    if (!editando && !gradoId) {
      toast.error("Selecciona un grado");
      return;
    }
    setGuardando(true);
    try {
      if (editando) {
        await adminActualizarEstudiante(estudiante.id, {
          nombre: nombre.trim(), apellido: apellido.trim(),
          grado_id: gradoId ? Number(gradoId) : null,
        });
        toast.success("Estudiante actualizado");
        onCreado(null);
      } else {
        const cred = await adminCrearEstudiante({
          nombre: nombre.trim(), apellido: apellido.trim(), grado_id: Number(gradoId),
        });
        toast.success("Estudiante creado");
        onCreado(cred);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo guardar");
      setGuardando(false);
    }
  }

  return (
    <ModalShell titulo={editando ? "Editar estudiante" : "Agregar estudiante"} onClose={guardando ? undefined : onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-4">
          <Campo label="Nombre">
            <input value={nombre} onChange={(e) => setNombre(e.target.value)} className={inputCls} />
          </Campo>
          <Campo label="Apellido">
            <input value={apellido} onChange={(e) => setApellido(e.target.value)} className={inputCls} />
          </Campo>
        </div>
        <Campo label="Grado">
          <select value={gradoId} onChange={(e) => setGradoId(e.target.value)} className={inputCls}>
            <option value="">Selecciona un grado…</option>
            {grados.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nombre}
              </option>
            ))}
          </select>
        </Campo>
        {!editando && (
          <div className="rounded-xl bg-slate-50 px-4 py-3 text-[13px] font-bold text-slate-500">
            El usuario y la contraseña se generan automáticamente y se mostrarán al crear.
          </div>
        )}
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

function ImportarModal({
  onClose,
  onImportado,
}: {
  onClose: () => void;
  onImportado: (creds: EstudianteCreado[]) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [texto, setTexto] = useState("");
  const [subiendo, setSubiendo] = useState(false);

  const preview = useMemo(() => {
    if (!texto) return [];
    return texto
      .split(/\r?\n/)
      .filter((l) => l.trim())
      .slice(0, 6); // encabezado + 5 filas
  }, [texto]);

  function onPick(f: File | null) {
    setFile(f);
    if (!f) {
      setTexto("");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setTexto(String(reader.result ?? ""));
    reader.readAsText(f);
  }

  async function confirmar() {
    if (!file || subiendo) return;
    setSubiendo(true);
    try {
      const fd = new FormData();
      fd.append("archivo", file);
      const creds = await adminImportarEstudiantes(fd);
      toast.success(`${creds.length} estudiante(s) importado(s)`);
      onImportado(creds);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo importar");
      setSubiendo(false);
    }
  }

  return (
    <ModalShell titulo="Importar estudiantes (CSV)" onClose={subiendo ? undefined : onClose} ancho="max-w-[640px]">
      <div className="flex flex-col gap-4">
        <div className="rounded-xl bg-slate-50 px-4 py-3 text-[13px] font-bold text-slate-500">
          Formato de columnas: <code className="font-black text-slate-700">nombre,apellido,grado_id</code>.
          El usuario y la contraseña se generan automáticamente.
        </div>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          className="w-full rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm font-semibold text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-1.5 file:font-extrabold file:text-white"
        />
        {preview.length > 0 && (
          <div>
            <div className="mb-2 text-[13px] font-extrabold text-slate-600">
              Vista previa (primeras filas)
            </div>
            <div className="overflow-hidden rounded-xl border border-slate-200 text-[13px]">
              {preview.map((linea, i) => (
                <div
                  key={i}
                  className={`px-4 py-2 font-semibold ${
                    i === 0 ? "bg-slate-100 font-black text-slate-700" : "border-t border-slate-100 text-slate-600"
                  }`}
                >
                  {linea}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="mt-1 flex justify-end gap-3">
          <BotonSecundario type="button" onClick={onClose} disabled={subiendo}>
            Cancelar
          </BotonSecundario>
          <BotonPrimario onClick={confirmar} disabled={!file || subiendo}>
            {subiendo ? "Importando…" : "Importar"}
          </BotonPrimario>
        </div>
      </div>
    </ModalShell>
  );
}

function CredencialesModal({
  credenciales,
  onClose,
}: {
  credenciales: EstudianteCreado[];
  onClose: () => void;
}) {
  function descargar() {
    const filas = [
      "nombre,apellido,username,password",
      ...credenciales.map((c) => `${c.nombre},${c.apellido},${c.username},${c.password_generado}`),
    ];
    const blob = new Blob([filas.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "credenciales_estudiantes.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <ModalShell titulo="Credenciales generadas" onClose={onClose} ancho="max-w-[640px]">
      <div className="mb-4 rounded-xl bg-amber-50 px-4 py-3 text-[13px] font-bold text-amber-700">
        ⚠️ Estas contraseñas se muestran <b>una sola vez</b>. Descárgalas o cópialas ahora para entregarlas.
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200">
        <div className="flex bg-slate-100 px-4 py-2 text-[11px] font-extrabold uppercase tracking-wide text-slate-500">
          <div className="flex-1">Estudiante</div>
          <div className="w-[130px]">Usuario</div>
          <div className="w-[120px]">Contraseña</div>
        </div>
        {credenciales.map((c, i) => (
          <div key={i} className="flex border-t border-slate-100 px-4 py-2.5 text-sm">
            <div className="flex-1 font-extrabold text-slate-900">
              {c.nombre} {c.apellido}
            </div>
            <div className="w-[130px] font-bold text-slate-600">{c.username}</div>
            <div className="w-[120px] font-mono font-bold text-slate-600">{c.password_generado}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 flex justify-end gap-3">
        <BotonSecundario onClick={onClose}>Cerrar</BotonSecundario>
        <BotonPrimario onClick={descargar}>⬇️ Descargar lista</BotonPrimario>
      </div>
    </ModalShell>
  );
}
