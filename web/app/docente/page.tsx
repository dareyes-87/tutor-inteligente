"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import {
  ApiError,
  obtenerEstadisticas,
  obtenerEstudiantes,
  obtenerLibros,
  type EstadisticasDocente,
  type EstudianteResumen,
  type LibroDocente,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { colorProgreso, ESTADO_LIBRO } from "@/lib/docente";

export default function DocentePage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<EstadisticasDocente | null>(null);
  const [libros, setLibros] = useState<LibroDocente[]>([]);
  const [estudiantes, setEstudiantes] = useState<EstudianteResumen[]>([]);
  const [refresh, setRefresh] = useState(0);

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

  // Auto-poll cada 5s mientras algún libro esté procesándose (para reflejar el avance).
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

  // Últimos 3 estudiantes activos (por fecha de última actividad; nulos al final).
  const recientes = useMemo(() => {
    return [...estudiantes]
      .sort((a, b) => (b.ultima_actividad ?? "").localeCompare(a.ultima_actividad ?? ""))
      .slice(0, 3);
  }, [estudiantes]);

  const ultimoLibro = libros[0]; // listar_libros viene ordenado por fecha_subida desc

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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Estudiantes activos recientes */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-lg font-black text-navy">👩‍🎓 Actividad reciente</div>
            <Link href="/docente/estudiantes" className="text-[13px] font-extrabold text-brand-blue hover:underline">
              Ver todos →
            </Link>
          </div>
          <div className="overflow-hidden rounded-[16px] border border-[#E6E9F0] bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            {recientes.length === 0 && (
              <div className="px-5 py-8 text-center text-sm font-bold text-muted-foreground">
                No hay estudiantes registrados.
              </div>
            )}
            {recientes.map((e) => {
              const pct = pctEstudiante(e);
              return (
                <Link
                  key={e.id}
                  href={`/docente/estudiantes/${e.id}`}
                  className="flex items-center gap-3 border-b border-[#F4F6FA] px-5 py-3.5 transition-colors last:border-0 hover:bg-[#F7F9FC]"
                >
                  <div className="grid h-9 w-9 flex-none place-items-center rounded-full bg-navy text-sm font-black text-white">
                    {e.nombre[0]}
                    {e.apellido[0]}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-extrabold text-navy">
                      {e.nombre} {e.apellido}
                    </div>
                    <div className="text-xs font-bold text-muted-foreground">
                      {e.ultima_actividad ?? "Sin actividad"} · 🔥 {e.racha_actual}
                    </div>
                  </div>
                  <span className="flex-none text-sm font-black" style={{ color: colorProgreso(pct) }}>
                    {pct}%
                  </span>
                </Link>
              );
            })}
          </div>
        </section>

        {/* Último libro subido */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-lg font-black text-navy">📚 Último libro</div>
            <Link href="/docente/libros" className="text-[13px] font-extrabold text-brand-blue hover:underline">
              Ver libros →
            </Link>
          </div>
          {ultimoLibro ? (
            <div className="flex items-center gap-4 rounded-[16px] border border-[#E6E9F0] bg-white px-5 py-4 shadow-[0_5px_16px_rgba(30,43,77,.05)]">
              <div className="grid h-12 w-10 flex-none place-items-center rounded-md bg-navy text-lg">
                📕
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[15px] font-extrabold text-navy">{ultimoLibro.titulo}</div>
                <div className="text-xs font-bold text-muted-foreground">
                  {ultimoLibro.asignatura} · {ultimoLibro.grado}
                </div>
                <div className="mt-1 text-[11.5px] font-bold text-[#9AA0AD]">
                  {ultimoLibro.total_fragmentos} fragmentos · {ultimoLibro.total_lecciones} lecciones
                </div>
              </div>
              {(() => {
                const est = ESTADO_LIBRO[ultimoLibro.estado] ?? ESTADO_LIBRO.pendiente;
                return (
                  <span
                    className="flex-none rounded-full px-3 py-1.5 text-[11.5px] font-extrabold"
                    style={{ background: est.bg, color: est.color }}
                  >
                    {ultimoLibro.estado === "procesando" && (
                      <span className="mr-1 inline-block animate-spin">⏳</span>
                    )}
                    {est.label}
                  </span>
                );
              })()}
            </div>
          ) : (
            <Link
              href="/docente/libros"
              className="block rounded-[16px] border border-dashed border-[#D8DEE9] bg-white px-6 py-8 text-center text-sm font-bold text-muted-foreground hover:bg-[#F7F9FC]"
            >
              Aún no hay libros. Sube el primero →
            </Link>
          )}
        </section>
      </div>
    </div>
  );
}
