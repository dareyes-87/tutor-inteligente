"use client";

import { useEffect, useState } from "react";

import { ApiError, obtenerRanking, type RankingResponse } from "@/lib/api";
import { toast } from "sonner";

// Colores de avatar ciclados por posición (kid-friendly).
const AVATAR_COLORS = ["#F59E0B", "#2563EB", "#F97316", "#8B5CF6", "#EC4899", "#22C55E", "#06B6D4", "#EF4444"];
const MEDALLAS: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export default function RankingPage() {
  const [data, setData] = useState<RankingResponse | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let activo = true;
    obtenerRanking()
      .then((d) => {
        if (!activo) return;
        setData(d);
        setError(false);
      })
      .catch((err) => {
        if (!activo) return;
        setError(true);
        toast.error(err instanceof ApiError ? err.message : "No se pudo cargar el ranking");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [intento]);

  const recargar = () => {
    setCargando(true);
    setError(false);
    setIntento((n) => n + 1);
  };

  return (
    <div className="px-[38px] py-[34px]">
      <div className="mb-[22px] text-2xl font-black text-navy">Tabla de posiciones 🏆</div>

      {cargando && (
        <div className="mt-10 text-center text-sm font-bold text-muted-foreground">
          Cargando ranking…
        </div>
      )}

      {!cargando && error && (
        <div className="mx-auto mt-10 max-w-[420px] rounded-[22px] border border-border bg-white p-8 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="text-base font-extrabold text-navy">No se pudo cargar el ranking.</div>
          <button
            onClick={recargar}
            className="btn-relief mt-4 rounded-[14px] bg-brand-blue px-6 py-3 text-sm font-extrabold text-white"
            style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
          >
            Reintentar
          </button>
        </div>
      )}

      {!cargando && !error && data && data.ranking.length === 0 && (
        <div className="mx-auto mt-10 max-w-[460px] rounded-[24px] border border-border bg-white p-10 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="text-lg font-black text-navy">Aún no hay posiciones</div>
          <div className="mt-2 text-[13.5px] font-bold text-muted-foreground">
            Completa lecciones y gana puntos para aparecer en la tabla.
          </div>
        </div>
      )}

      {!cargando && !error && data && data.ranking.length > 0 && (
        <div className="flex flex-col gap-2.5">
          {data.ranking.map((r) => {
            const yo = r.posicion === data.mi_posicion;
            return (
              <div
                key={r.posicion}
                className="flex items-center gap-[18px] rounded-2xl border px-[22px] py-3.5 shadow-[0_4px_12px_rgba(30,43,77,.04)]"
                style={{
                  background: yo ? "#FFF1E7" : "#fff",
                  borderColor: yo ? "#F97316" : "var(--border)",
                }}
              >
                <div className="w-[34px] text-center text-[17px] font-black text-muted-foreground">
                  {MEDALLAS[r.posicion] ?? r.posicion}
                </div>
                <div
                  className="grid h-[42px] w-[42px] flex-none place-items-center rounded-full text-base font-black text-white"
                  style={{ background: AVATAR_COLORS[(r.posicion - 1) % AVATAR_COLORS.length] }}
                >
                  {r.nombre[0]}
                  {r.apellido[0]}
                </div>
                <div className="flex-1">
                  <div className="text-base font-extrabold text-navy">
                    {r.nombre} {r.apellido}
                    {yo && (
                      <span className="ml-2 rounded-full bg-brand-orange px-2 py-0.5 text-[11px] font-extrabold text-white">
                        Tú
                      </span>
                    )}
                  </div>
                  <div className="text-xs font-bold text-muted-foreground">
                    {r.lecciones_completadas}{" "}
                    {r.lecciones_completadas === 1 ? "lección" : "lecciones"} · 🔥 {r.racha_actual}
                  </div>
                </div>
                <div className="w-[110px] text-right text-base font-black text-navy">
                  {r.puntos_totales} <span className="text-xs text-muted-foreground">pts</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
