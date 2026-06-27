"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import {
  ApiError,
  obtenerEstadisticas,
  obtenerEstudiantes,
  type EstudianteResumen,
} from "@/lib/api";
import { colorProgreso } from "@/lib/docente";

export default function EstudiantesPage() {
  const [estudiantes, setEstudiantes] = useState<EstudianteResumen[]>([]);
  const [totalLecciones, setTotalLecciones] = useState(0);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    Promise.all([obtenerEstudiantes(), obtenerEstadisticas()])
      .then(([e, s]) => {
        if (!activo) return;
        setEstudiantes(e);
        setTotalLecciones(s.total_lecciones);
      })
      .catch((err) => {
        if (activo) toast.error(err instanceof ApiError ? err.message : "No se pudieron cargar los estudiantes");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  const pctEstudiante = (e: EstudianteResumen) =>
    totalLecciones > 0 ? Math.round((e.lecciones_completadas / totalLecciones) * 100) : 0;

  return (
    <div className="px-9 py-8">
      <div className="mb-1 text-2xl font-black text-navy">👩‍🎓 Mis estudiantes</div>
      <div className="mb-6 text-sm font-bold text-[#7B8194]">
        Toca un estudiante para ver su ruta nivel por nivel y su comprensión por tema.
      </div>

      <div className="overflow-hidden rounded-[16px] border border-[#E6E9F0] bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
        <div className="flex items-center border-b border-[#EEF1F6] px-5 py-3 text-[11px] font-extrabold uppercase tracking-wide text-muted-foreground">
          <div className="flex-1">Estudiante</div>
          <div className="w-[200px]">Progreso</div>
          <div className="w-[90px] text-center">Puntos</div>
          <div className="w-[80px] text-center">Racha</div>
          <div className="w-[120px] text-right">Última act.</div>
        </div>

        {cargando && (
          <div className="px-5 py-8 text-center text-sm font-bold text-muted-foreground">
            Cargando estudiantes…
          </div>
        )}
        {!cargando && estudiantes.length === 0 && (
          <div className="px-5 py-8 text-center text-sm font-bold text-muted-foreground">
            No hay estudiantes registrados.
          </div>
        )}
        {!cargando &&
          estudiantes.map((e) => {
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
    </div>
  );
}
