"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  ApiError,
  obtenerDetalleEstudiante,
  type EstudianteDetalle,
  type LeccionEnRuta,
} from "@/lib/api";

const NIVEL_COLOR: Record<string, string> = {
  domina: "#22C55E",
  en_proceso: "#F59E0B",
  refuerzo: "#EF4444",
};

// Estrellas del sistema de 3 niveles (igual criterio que la ruta del estudiante).
function estrellasNivel(l: LeccionEnRuta): string {
  if (l.tiene_corona) return "👑 ⭐⭐⭐";
  return "⭐".repeat(l.nivel_completado) + "☆".repeat(3 - l.nivel_completado);
}

export default function DetalleEstudiantePage() {
  const params = useParams<{ id: string }>();
  const estudianteId = Number(params.id);

  const [detalle, setDetalle] = useState<EstudianteDetalle | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    obtenerDetalleEstudiante(estudianteId)
      .then((d) => {
        if (activo) setDetalle(d);
      })
      .catch((err) => {
        if (activo) setError(err instanceof ApiError ? err.message : "No se pudo cargar el detalle.");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [estudianteId]);

  return (
    <div className="px-9 py-8">
      <Link
        href="/docente"
        className="mb-5 inline-flex items-center gap-1.5 text-sm font-extrabold text-brand-blue hover:underline"
      >
        ← Volver al panel
      </Link>

      {cargando && (
        <div className="py-10 text-center text-sm font-bold text-muted-foreground">Cargando…</div>
      )}

      {error && !cargando && (
        <div className="rounded-[16px] border border-[#E6E9F0] bg-white px-6 py-8 text-center text-sm font-bold text-destructive">
          {error}
        </div>
      )}

      {detalle && (
        <>
          {/* Cabecera */}
          <div className="mb-6 flex items-center gap-4">
            <div className="grid h-14 w-14 flex-none place-items-center rounded-full bg-navy text-lg font-black text-white">
              {detalle.nombre[0]}
              {detalle.apellido[0]}
            </div>
            <div>
              <div className="text-2xl font-black text-navy">
                {detalle.nombre} {detalle.apellido}
              </div>
              <div className="text-sm font-bold text-[#7B8194]">{detalle.grado ?? "Sin grado"}</div>
            </div>
          </div>

          {/* Indicadores */}
          <div className="mb-8 flex flex-wrap gap-3 text-sm font-extrabold">
            <span className="rounded-full bg-[#FFF1E7] px-4 py-2 text-brand-orange">
              🔥 Racha {detalle.racha_actual}
            </span>
            <span className="rounded-full bg-[#EAF1FF] px-4 py-2 text-brand-blue">
              ⭐ {detalle.puntos_totales} pts
            </span>
            {detalle.ruta && (
              <span className="rounded-full bg-[#E9F9EF] px-4 py-2 text-[#16A34A]">
                📚 {detalle.ruta.lecciones_completadas}/{detalle.ruta.total_lecciones} lecciones
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1.4fr_1fr]">
            {/* Ruta de aprendizaje */}
            <section>
              <div className="mb-4 text-lg font-black text-navy">🗺️ Ruta de aprendizaje</div>
              <div className="flex flex-col gap-2">
                {(detalle.ruta?.lecciones ?? []).map((l) => (
                  <div
                    key={l.id}
                    className="flex items-center gap-3 rounded-[14px] border border-[#E6E9F0] bg-white px-4 py-3 shadow-[0_3px_10px_rgba(30,43,77,.04)]"
                  >
                    <span className="grid h-8 w-8 flex-none place-items-center rounded-full bg-[#F1F4FA] text-xs font-black text-[#7B8194]">
                      {l.orden}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-extrabold text-navy">{l.nombre}</div>
                      <div
                        className="text-[13px] tracking-wide"
                        title={`Nivel ${l.nivel_completado} de 3`}
                      >
                        {estrellasNivel(l)}
                      </div>
                    </div>
                    <span className="flex-none text-xs font-bold text-muted-foreground">
                      {l.actividades_completadas}/{l.actividades_requeridas}
                    </span>
                  </div>
                ))}
                {(!detalle.ruta || detalle.ruta.lecciones.length === 0) && (
                  <div className="rounded-[14px] border border-dashed border-[#D8DEE9] bg-white px-4 py-6 text-center text-sm font-bold text-muted-foreground">
                    Sin ruta asignada todavía.
                  </div>
                )}
              </div>
            </section>

            {/* Perfil de comprensión */}
            <section>
              <div className="mb-4 text-lg font-black text-navy">📊 Puntaje por tema</div>
              <div className="flex flex-col gap-2.5">
                {detalle.perfil.map((p) => (
                  <div
                    key={`${p.asignatura}·${p.tema}`}
                    className="rounded-[14px] border border-[#E6E9F0] bg-white px-4 py-3 shadow-[0_3px_10px_rgba(30,43,77,.04)]"
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 flex-none rounded-full"
                        style={{ background: NIVEL_COLOR[p.nivel] ?? "#9AA0AD" }}
                      />
                      <span className="min-w-0 flex-1 truncate text-sm font-extrabold text-navy">
                        {p.tema}
                      </span>
                      <span className="flex-none text-sm font-black text-navy">
                        {Math.round(p.puntaje_promedio)}
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[#ECE7DE]">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, Math.round(p.puntaje_promedio))}%`,
                          background: NIVEL_COLOR[p.nivel] ?? "#9AA0AD",
                        }}
                      />
                    </div>
                    <div className="mt-1.5 text-[11.5px] font-bold text-muted-foreground">
                      {p.total_actividades} actividad{p.total_actividades === 1 ? "" : "es"}
                    </div>
                  </div>
                ))}
                {detalle.perfil.length === 0 && (
                  <div className="rounded-[14px] border border-dashed border-[#D8DEE9] bg-white px-4 py-6 text-center text-sm font-bold text-muted-foreground">
                    Aún no ha resuelto actividades.
                  </div>
                )}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
