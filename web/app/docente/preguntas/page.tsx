"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError, obtenerEstadisticas, type EstadisticasDocente } from "@/lib/api";

export default function PreguntasPage() {
  const [stats, setStats] = useState<EstadisticasDocente | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let activo = true;
    obtenerEstadisticas()
      .then((s) => {
        if (activo) setStats(s);
      })
      .catch((err) => {
        if (activo) toast.error(err instanceof ApiError ? err.message : "No se pudieron cargar las preguntas");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  const totalConsultas = (stats?.temas_mas_preguntados ?? []).reduce((s, t) => s + t.total, 0);
  const preguntas = stats?.preguntas_frecuentes ?? [];

  return (
    <div className="px-9 py-8">
      <div className="mb-1 text-2xl font-black text-navy">❓ Preguntas</div>
      <div className="mb-6 text-sm font-bold text-[#7B8194]">
        Los estudiantes preguntan más sobre estos temas
      </div>

      {cargando ? (
        <div className="py-10 text-center text-sm font-bold text-muted-foreground">Cargando preguntas…</div>
      ) : (
        <>
          {/* Resumen por asignatura (total de consultas reales del chat). */}
          {stats && stats.temas_mas_preguntados.length > 0 && (
            <div className="mb-6 flex flex-wrap gap-3">
              <div className="rounded-[14px] border border-[#E6E9F0] bg-white px-5 py-3 shadow-[0_3px_10px_rgba(30,43,77,.04)]">
                <div className="text-2xl font-black text-navy">{totalConsultas}</div>
                <div className="text-[11px] font-extrabold uppercase tracking-wide text-muted-foreground">
                  consultas en total
                </div>
              </div>
              {stats.temas_mas_preguntados.map((t) => (
                <div
                  key={t.tema}
                  className="rounded-[14px] border border-[#E6E9F0] bg-white px-5 py-3 shadow-[0_3px_10px_rgba(30,43,77,.04)]"
                >
                  <div className="text-2xl font-black text-brand-blue">{t.total}</div>
                  <div className="text-[11px] font-extrabold uppercase tracking-wide text-muted-foreground">
                    {t.tema}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Desglose por pregunta concreta. */}
          <div className="mb-3 text-lg font-black text-navy">Preguntas más frecuentes</div>
          {preguntas.length === 0 ? (
            <div className="rounded-[16px] border border-dashed border-[#D8DEE9] bg-white px-6 py-8 text-center text-sm font-bold text-muted-foreground">
              Aún no hay preguntas registradas en el chat.
            </div>
          ) : (
            <div className="overflow-hidden rounded-[16px] border border-[#E6E9F0] bg-white shadow-[0_5px_16px_rgba(30,43,77,.05)]">
              {preguntas.map((p, i) => (
                <div
                  key={`${p.pregunta}·${i}`}
                  className="flex items-center gap-4 border-b border-[#F4F6FA] px-5 py-4 last:border-0"
                >
                  <div className="grid h-10 w-10 flex-none place-items-center rounded-full bg-[#EAF1FF] text-lg">
                    💬
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-extrabold text-navy">“{p.pregunta}”</div>
                    <div className="text-xs font-bold text-muted-foreground">{p.asignatura}</div>
                  </div>
                  <span className="flex-none rounded-full bg-[#F1F4FA] px-3 py-1.5 text-xs font-extrabold text-brand-blue">
                    {p.total} {p.total === 1 ? "vez" : "veces"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
