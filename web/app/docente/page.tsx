"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import {
  ApiError,
  obtenerEstadisticas,
  obtenerEstudiantes,
  obtenerLibros,
  subirLibro,
  type EstadisticasDocente,
  type EstudianteResumen,
  type LibroDocente,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

// Color por % de progreso (verde ≥80 / naranja 50–79 / rojo <50).
function colorProgreso(pct: number): string {
  if (pct >= 80) return "#22C55E";
  if (pct >= 50) return "#F97316";
  return "#EF4444";
}

const ESTADO_LIBRO: Record<string, { bg: string; color: string; label: string }> = {
  completado: { bg: "#E9F9EF", color: "#16A34A", label: "Completado" },
  procesando: { bg: "#FEF6E7", color: "#D97706", label: "Procesando…" },
  pendiente: { bg: "#F1EDE5", color: "#8A8F9C", label: "Pendiente" },
  error: { bg: "#FDECEC", color: "#DC2626", label: "Error" },
};

export default function DocentePage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<EstadisticasDocente | null>(null);
  const [libros, setLibros] = useState<LibroDocente[]>([]);
  const [estudiantes, setEstudiantes] = useState<EstudianteResumen[]>([]);
  const [refresh, setRefresh] = useState(0);

  const [showUpload, setShowUpload] = useState(false);

  // Carga principal (se re-dispara con `refresh`).
  useEffect(() => {
    let activo = true;
    Promise.all([obtenerEstadisticas(), obtenerLibros(), obtenerEstudiantes()])
      .then(([s, l, e]) => {
        if (!activo) return;
        setStats(s);
        setLibros(l);
        setEstudiantes(e);
      })
      .catch((err) => {
        if (activo) toast.error(err instanceof ApiError ? err.message : "No se pudieron cargar los datos");
      });
    return () => {
      activo = false;
    };
  }, [refresh]);

  // Auto-poll cada 5s mientras algún libro esté procesándose.
  const hayProcesando = useMemo(
    () => libros.some((l) => l.estado === "procesando" || l.estado === "pendiente"),
    [libros],
  );
  useEffect(() => {
    if (!hayProcesando) return;
    const id = setInterval(() => setRefresh((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, [hayProcesando]);

  const totalLecciones = stats?.total_lecciones ?? 0;
  const pctEstudiante = (e: EstudianteResumen) =>
    totalLecciones > 0 ? Math.round((e.lecciones_completadas / totalLecciones) * 100) : 0;

  return (
    <div className="px-9 py-8">
      {/* Header */}
      <div className="mb-1 text-2xl font-black text-navy">Panel docente</div>
      <div className="mb-6 text-sm font-bold text-[#7B8194]">
        {user ? `Prof. ${user.apellido || user.nombre}` : "Docente"} · Oasis Christian School
      </div>

      {/* Estadísticas */}
      <div className="mb-8 grid grid-cols-4 gap-4">
        {[
          { label: "Estudiantes", val: stats?.total_estudiantes ?? "—" },
          { label: "Libros", val: stats?.total_libros ?? "—" },
          { label: "Lecciones", val: stats?.total_lecciones ?? "—" },
          {
            label: "Progreso promedio",
            val: stats ? `${Math.round(stats.promedio_progreso)}%` : "—",
          },
        ].map((c) => (
          <div
            key={c.label}
            className="rounded-[18px] border border-[#E6E9F0] bg-white px-6 py-5 shadow-[0_5px_16px_rgba(30,43,77,.05)]"
          >
            <div className="text-[32px] font-black leading-none text-navy">{c.val}</div>
            <div className="mt-1.5 text-xs font-extrabold uppercase tracking-wide text-muted-foreground">
              {c.label}
            </div>
          </div>
        ))}
      </div>

      {/* Sección Libros */}
      <section className="mb-8">
        <div className="mb-4 flex items-center justify-between">
          <div className="text-lg font-black text-navy">📚 Mis libros</div>
          <button
            onClick={() => setShowUpload(true)}
            className="rounded-xl bg-brand-blue px-5 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_#1D4ED8] active:translate-y-px"
          >
            + Subir nuevo libro
          </button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {libros.length === 0 && (
            <div className="col-span-2 rounded-[16px] border border-dashed border-[#D8DEE9] bg-white px-6 py-8 text-center text-sm font-bold text-muted-foreground">
              Aún no hay libros. Sube el primero con “Subir nuevo libro”.
            </div>
          )}
          {libros.map((l) => {
            const est = ESTADO_LIBRO[l.estado] ?? ESTADO_LIBRO.pendiente;
            return (
              <div
                key={l.id}
                className="flex items-center gap-4 rounded-[16px] border border-[#E6E9F0] bg-white px-5 py-4 shadow-[0_5px_16px_rgba(30,43,77,.05)]"
              >
                <div className="grid h-12 w-10 flex-none place-items-center rounded-md bg-navy text-lg">
                  📕
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[15px] font-extrabold text-navy">{l.titulo}</div>
                  <div className="text-xs font-bold text-muted-foreground">
                    {l.asignatura} · {l.grado}
                  </div>
                  <div className="mt-1 text-[11.5px] font-bold text-[#9AA0AD]">
                    {l.total_fragmentos} fragmentos · {l.total_lecciones} lecciones
                  </div>
                </div>
                <span
                  className="flex-none rounded-full px-3 py-1.5 text-[11.5px] font-extrabold"
                  style={{ background: est.bg, color: est.color }}
                >
                  {l.estado === "procesando" && <span className="mr-1 inline-block animate-spin">⏳</span>}
                  {est.label}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* Sección Estudiantes */}
      <section>
        <div className="mb-4 text-lg font-black text-navy">👩‍🎓 Mis estudiantes</div>
        <div className="overflow-hidden rounded-[16px] border border-[#E6E9F0] bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
          <div className="flex items-center border-b border-[#EEF1F6] px-5 py-3 text-[11px] font-extrabold uppercase tracking-wide text-muted-foreground">
            <div className="flex-1">Estudiante</div>
            <div className="w-[200px]">Progreso</div>
            <div className="w-[90px] text-center">Puntos</div>
            <div className="w-[80px] text-center">Racha</div>
            <div className="w-[120px] text-right">Última act.</div>
          </div>
          {estudiantes.length === 0 && (
            <div className="px-5 py-8 text-center text-sm font-bold text-muted-foreground">
              No hay estudiantes registrados.
            </div>
          )}
          {estudiantes.map((e) => {
            const pct = pctEstudiante(e);
            return (
              <Link
                key={e.id}
                href={`/docente/estudiantes/${e.id}`}
                className="flex w-full items-center border-b border-[#F4F6FA] px-5 py-3.5 text-left transition-colors last:border-0 hover:bg-[#F7F9FC]"
              >
                <div className="flex flex-1 items-center gap-3">
                  <div className="grid h-9 w-9 flex-none place-items-center rounded-full bg-navy text-sm font-black text-white">
                    {e.nombre[0]}
                    {e.apellido[0]}
                  </div>
                  <span className="text-sm font-extrabold text-navy">
                    {e.nombre} {e.apellido}
                  </span>
                </div>
                <div className="flex w-[200px] items-center gap-2.5">
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-[#ECE7DE]">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${pct}%`, background: colorProgreso(pct) }}
                    />
                  </div>
                  <span className="w-9 text-xs font-extrabold" style={{ color: colorProgreso(pct) }}>
                    {pct}%
                  </span>
                </div>
                <div className="w-[90px] text-center text-sm font-black text-navy">
                  {e.puntos_totales}
                </div>
                <div className="w-[80px] text-center text-sm font-extrabold text-brand-orange">
                  🔥 {e.racha_actual}
                </div>
                <div className="w-[120px] text-right text-xs font-bold text-muted-foreground">
                  {e.ultima_actividad ?? "—"}
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* Preguntas: temas más consultados al chat */}
      <section className="mt-8">
        <div className="mb-1 text-lg font-black text-navy">❓ Preguntas</div>
        <div className="mb-4 text-sm font-bold text-[#7B8194]">
          Los estudiantes preguntan más sobre estos temas
        </div>
        {stats && stats.temas_mas_preguntados.length > 0 ? (
          <div className="overflow-hidden rounded-[16px] border border-[#E6E9F0] bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            {stats.temas_mas_preguntados.map((t) => (
              <div
                key={t.tema}
                className="flex items-center gap-4 border-b border-[#F4F6FA] px-5 py-4 last:border-0"
              >
                <div className="grid h-10 w-10 flex-none place-items-center rounded-full bg-[#EAF1FF] text-lg">
                  💬
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-extrabold text-navy">{t.tema}</div>
                  {t.ejemplo && (
                    <div className="truncate text-xs font-bold text-muted-foreground">
                      “{t.ejemplo}”
                    </div>
                  )}
                </div>
                <span className="flex-none rounded-full bg-[#F1F4FA] px-3 py-1.5 text-xs font-extrabold text-brand-blue">
                  {t.total} consulta{t.total === 1 ? "" : "s"}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-[16px] border border-dashed border-[#D8DEE9] bg-white px-6 py-8 text-center text-sm font-bold text-muted-foreground">
            Aún no hay preguntas registradas en el chat.
          </div>
        )}
      </section>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onSubido={() => {
            setShowUpload(false);
            setRefresh((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}

/* ---------------- Modal de subida ---------------- */
function UploadModal({ onClose, onSubido }: { onClose: () => void; onSubido: () => void }) {
  const [titulo, setTitulo] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);

  async function handleSubir(e: React.FormEvent) {
    e.preventDefault();
    if (!titulo.trim() || !file || subiendo) return;
    setSubiendo(true);
    try {
      const fd = new FormData();
      fd.append("titulo", titulo.trim());
      fd.append("asignatura_id", "1");
      fd.append("grado_id", "1");
      fd.append("archivo", file);
      await subirLibro(fd);
      toast.success("Libro subido. Procesando OCR…");
      onSubido();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo subir el libro");
      setSubiendo(false);
    }
  }

  return (
    <ModalShell onClose={subiendo ? undefined : onClose} titulo="Subir nuevo libro">
      <form onSubmit={handleSubir} className="flex flex-col gap-4">
        <Campo label="Título del libro">
          <input
            value={titulo}
            onChange={(ev) => setTitulo(ev.target.value)}
            placeholder="Ej: Ciencias Naturales 1ro"
            className="w-full rounded-xl border-2 border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy outline-none focus:border-brand-blue"
          />
        </Campo>
        <div className="grid grid-cols-2 gap-4">
          <Campo label="Asignatura">
            <select
              disabled
              className="w-full rounded-xl border-2 border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy outline-none"
            >
              <option>Ciencias Naturales</option>
            </select>
          </Campo>
          <Campo label="Grado">
            <select
              disabled
              className="w-full rounded-xl border-2 border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy outline-none"
            >
              <option>1ro Básico</option>
            </select>
          </Campo>
        </div>
        <Campo label="Archivo PDF">
          <input
            type="file"
            accept=".pdf"
            onChange={(ev) => setFile(ev.target.files?.[0] ?? null)}
            className="w-full rounded-xl border-2 border-dashed border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy file:mr-3 file:rounded-lg file:border-0 file:bg-brand-blue file:px-3 file:py-1.5 file:font-extrabold file:text-white"
          />
        </Campo>
        <div className="mt-2 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={subiendo}
            className="rounded-xl border-2 border-border bg-white px-5 py-2.5 text-sm font-extrabold text-[#5A6170] disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={!titulo.trim() || !file || subiendo}
            className="rounded-xl bg-brand-blue px-6 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_#1D4ED8] active:translate-y-px disabled:opacity-50"
          >
            {subiendo ? "Subiendo…" : "Subir"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

/* ---------------- Helpers de UI ---------------- */
function ModalShell({
  titulo,
  onClose,
  children,
}: {
  titulo: string;
  onClose?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[560px] max-h-[88vh] overflow-y-auto rounded-[20px] bg-white p-7 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <div className="text-xl font-black text-navy">{titulo}</div>
          {onClose && (
            <button
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-full bg-muted text-lg font-black text-muted-foreground hover:bg-muted/70"
            >
              ✕
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[13px] font-extrabold text-[#5A6170]">{label}</label>
      {children}
    </div>
  );
}
