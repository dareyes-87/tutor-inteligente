"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { ApiError, getPerfil, type NivelComprension, type PerfilTema } from "@/lib/api";
import { NIVEL_META } from "@/lib/mock";
import { Mascota } from "@/components/mascota";

/** El backend usa `en_proceso`; los tokens visuales del diseño usan `proceso`. */
const nivelMeta = (n: NivelComprension) =>
  n === "en_proceso" ? NIVEL_META.proceso : NIVEL_META[n];

export default function ProgresoPage() {
  const [perfil, setPerfil] = useState<PerfilTema[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);
  const [intento, setIntento] = useState(0); // dispara la recarga

  // El effect solo hace setState dentro de los callbacks de la promesa.
  useEffect(() => {
    let activo = true;
    getPerfil()
      .then((data) => {
        if (!activo) return;
        setPerfil(data);
        setError(false);
      })
      .catch((err) => {
        if (!activo) return;
        setError(true);
        const msg = err instanceof ApiError ? err.message : "No se pudo conectar con el servidor";
        toast.error(msg);
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [intento]);

  // El botón de reintento (no es un effect) resetea el estado y vuelve a disparar.
  const reintentar = () => {
    setCargando(true);
    setError(false);
    setIntento((n) => n + 1);
  };

  // --- Cargando ---
  if (cargando) {
    return (
      <div className="px-4 py-6 sm:px-6 md:px-[38px] md:py-[34px]">
        <div className="text-2xl font-black text-navy">Mi progreso</div>
        <div className="mt-10 text-center text-sm font-bold text-muted-foreground">
          Cargando tu progreso…
        </div>
      </div>
    );
  }

  // --- Error ---
  if (error) {
    return (
      <div className="px-4 py-6 sm:px-6 md:px-[38px] md:py-[34px]">
        <div className="text-2xl font-black text-navy">Mi progreso</div>
        <div className="mx-auto mt-10 max-w-[420px] rounded-[22px] border border-border bg-white p-8 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="text-base font-extrabold text-navy">No se pudo cargar tu progreso.</div>
          <button
            onClick={reintentar}
            className="btn-relief mt-4 rounded-[14px] bg-brand-blue px-6 py-3 text-sm font-extrabold text-white"
            style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  const items = perfil ?? [];

  // --- Estado vacío ---
  if (items.length === 0) {
    return (
      <div className="px-4 py-6 sm:px-6 md:px-[38px] md:py-[34px]">
        <div className="text-2xl font-black text-navy">Mi progreso</div>
        <div className="mx-auto mt-10 max-w-[480px] rounded-[24px] border border-border bg-white p-10 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="mx-auto mb-4 h-[84px] w-[84px] animate-floaty overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange">
            <Mascota size={84} />
          </div>
          <div className="text-lg font-black text-navy">
            Aún no has completado actividades. ¡Empieza a practicar!
          </div>
          <div className="mt-2 text-[13.5px] font-bold text-muted-foreground">
            Resuelve actividades y aquí verás tu comprensión tema por tema.
          </div>
          <Link
            href="/actividades"
            className="btn-relief mt-6 inline-block rounded-[16px] bg-brand-orange px-8 py-3.5 text-base font-black text-white"
          >
            Ir a practicar 🎯
          </Link>
        </div>
      </div>
    );
  }

  // --- Con datos ---
  const totalActividades = items.reduce((s, p) => s + p.total_actividades, 0);
  // Promedio ponderado por nº de actividades: temas con más práctica pesan más,
  // dando un avance más representativo que un promedio simple de promedios.
  const avanceTotal =
    totalActividades === 0
      ? 0
      : Math.round(
          items.reduce((s, p) => s + p.puntaje_promedio * p.total_actividades, 0) /
            totalActividades,
        );

  return (
    <div className="px-4 py-6 sm:px-6 md:px-[38px] md:py-[34px]">
      {/* Cabecera + stats */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-2xl font-black text-navy">Mi progreso</div>
          <div className="mt-[3px] text-sm font-bold text-muted-foreground">
            Tu comprensión tema por tema
          </div>
        </div>
        <div className="flex gap-3.5">
          <div className="rounded-2xl border border-border bg-white px-5 py-3 text-center shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            <div className="text-2xl font-black text-brand-green">{totalActividades}</div>
            <div className="text-[11px] font-extrabold text-muted-foreground">ACTIVIDADES</div>
          </div>
          <div className="rounded-2xl border border-border bg-white px-5 py-3 text-center shadow-[0_5px_16px_rgba(30,43,77,.05)]">
            <div className="text-2xl font-black text-brand-orange">{avanceTotal}%</div>
            <div className="text-[11px] font-extrabold text-muted-foreground">AVANCE TOTAL</div>
          </div>
        </div>
      </div>

      {/* Temas */}
      <div className="flex flex-col gap-3.5">
        {items.map((p, i) => {
          const nv = nivelMeta(p.nivel);
          const pct = Math.round(p.puntaje_promedio);
          return (
            <div
              key={`${p.asignatura}·${p.tema}`}
              className="flex items-center gap-3 rounded-[20px] border border-border bg-white px-4 py-4 shadow-[0_5px_16px_rgba(30,43,77,.05)] sm:gap-[22px] sm:px-6 sm:py-5"
            >
              <div
                className="grid h-[46px] w-[46px] flex-none place-items-center rounded-[14px] text-lg font-black"
                style={{ background: nv.chipBg, color: nv.chipColor }}
              >
                {i + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-2.5 flex items-center justify-between gap-4">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-[16.5px] font-extrabold text-navy">
                      {p.tema}
                    </span>
                    <span className="mr-2 flex-none rounded-full bg-muted px-2 py-0.5 text-[11px] font-extrabold text-muted-foreground">
                      {p.asignatura}
                    </span>
                  </div>
                  <div className="flex-none text-[12.5px] font-extrabold text-muted-foreground">
                    {p.total_actividades} {p.total_actividades === 1 ? "actividad" : "actividades"}
                  </div>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-[#ECE7DE]">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${pct}%`, background: nv.bar }}
                  />
                </div>
              </div>
              <div className="w-auto flex-none text-right sm:w-[180px]">
                <span
                  className="inline-block rounded-full px-4 py-2 text-[13px] font-extrabold"
                  style={{ background: nv.chipBg, color: nv.chipColor }}
                >
                  {nv.chip}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
