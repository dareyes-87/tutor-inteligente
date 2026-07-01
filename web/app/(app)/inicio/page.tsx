"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import {
  obtenerMiLibro,
  obtenerRacha,
  obtenerRuta,
  type RachaResponse,
  type RutaAprendizaje,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ProgressRing } from "@/components/progress-ring";

export default function InicioPage() {
  const { user } = useAuth();
  const nombre = user?.nombre ?? "Sofía";

  const [racha, setRacha] = useState<RachaResponse | null>(null);
  const [ruta, setRuta] = useState<RutaAprendizaje | null>(null);

  useEffect(() => {
    let activo = true;
    Promise.all([
      obtenerRacha(),
      obtenerMiLibro().then((mi) => obtenerRuta(mi.libro_id)),
    ])
      .then(([rachaResp, rutaResp]) => {
        if (!activo) return;
        setRacha(rachaResp);
        setRuta(rutaResp);
      })
      .catch(() => {
        /* silencioso: el dashboard sigue mostrándose con lo demás */
      });
    return () => {
      activo = false;
    };
  }, []);

  const leccionActual = ruta
    ? Math.min(ruta.total_lecciones, ruta.lecciones_completadas + 1)
    : 0;

  return (
    <div className="px-4 py-6 sm:px-6 md:px-[38px] md:py-[34px]">
      {/* Saludo + CTA */}
      <div className="mb-[26px] flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
        <div className="flex items-center gap-4">
          <img
            src="/dash.png"
            alt="Tutor Tigre"
            className="h-16 w-16 flex-none object-contain"
          />
          <div>
            <div className="text-[28px] font-black leading-none text-navy">
              ¡Hola, {nombre}! 👋
            </div>
            <div className="mt-[5px] text-[15px] font-semibold text-muted-foreground">
              ¿Seguimos aprendiendo hoy?
            </div>
          </div>
        </div>
        <Link
          href="/chat"
          className="btn-relief flex w-full items-center justify-center gap-2.5 rounded-[18px] bg-brand-blue px-[26px] py-4 text-[17px] font-black text-white sm:w-auto"
          style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
        >
          💬 Pregúntale al tutor
        </Link>
      </div>

      {/* Racha (real) + Mi ruta (real) */}
      <div className="mb-7 flex flex-col gap-5 lg:flex-row">
        {/* Racha */}
        <div className="flex flex-1 items-center gap-[22px] rounded-[22px] bg-gradient-to-br from-[#FB923C] to-brand-orange px-[26px] py-6 text-white shadow-[0_10px_24px_rgba(249,115,22,.28)]">
          <div className="animate-flame text-[62px] leading-none">🔥</div>
          <div className="flex-1">
            <div className="text-[34px] font-black leading-none">
              {racha?.racha_actual ?? 0} {racha?.racha_actual === 1 ? "día" : "días"}
            </div>
            <div className="text-[15px] font-extrabold opacity-95">
              {racha?.activo_hoy
                ? "¡Ya practicaste hoy! 🎉"
                : "seguidos · ¡no rompas la racha!"}
            </div>
            <div className="mt-3.5 inline-flex items-center gap-2 rounded-full bg-white/20 px-3.5 py-1.5 text-[13px] font-extrabold">
              🏆 Mejor racha: {racha?.mejor_racha ?? 0}
            </div>
          </div>
        </div>

        {/* Mi ruta */}
        <div className="w-full flex-none rounded-[22px] border border-border bg-white px-6 py-[22px] shadow-[0_6px_20px_rgba(30,43,77,.05)] lg:w-[430px]">
          <div className="mb-1.5 flex items-center justify-between">
            <div className="text-base font-black text-navy">🗺️ Mi ruta</div>
            <Link href="/ruta" className="text-[13px] font-extrabold text-brand-blue">
              Continuar →
            </Link>
          </div>
          <div className="mb-3.5 text-sm font-bold text-muted-foreground">
            {ruta ? (
              <>
                Vas en la{" "}
                <span className="font-black text-brand-orange">
                  Lección {leccionActual} de {ruta.total_lecciones}
                </span>{" "}
                · {ruta.asignatura}
              </>
            ) : (
              "Cargando tu progreso…"
            )}
          </div>
          <div className="h-3.5 overflow-hidden rounded-full bg-[#ECE7DE]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-brand-orange to-[#FB923C]"
              style={{ width: `${ruta?.progreso_porcentaje ?? 0}%` }}
            />
          </div>
          <div className="mt-2.5 flex items-center justify-between text-[13px] font-extrabold">
            <span className="text-muted-foreground">
              {ruta?.lecciones_completadas ?? 0} de {ruta?.total_lecciones ?? 0} completadas
            </span>
            <span className="text-brand-orange">
              {Math.round(ruta?.progreso_porcentaje ?? 0)}%
            </span>
          </div>
        </div>
      </div>

      {/* Asignaturas (asignatura real del estudiante — desde la ruta del libro) */}
      <div className="mb-4 flex items-center justify-between">
        <div className="text-xl font-black text-navy">Mis asignaturas</div>
        <Link href="/progreso" className="text-[13px] font-extrabold text-brand-blue">
          Ver todas →
        </Link>
      </div>
      {ruta ? (
        <div className="grid grid-cols-1 gap-4 sm:gap-[18px] md:grid-cols-4">
          <div className="rounded-[22px] border border-border bg-white p-[22px] text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
            <div className="mx-auto mb-3.5 grid h-12 w-12 place-items-center rounded-[14px] bg-[#E9F9EF] text-2xl">
              📚
            </div>
            <div className="mx-auto mb-3.5 w-[108px] max-w-full">
              <ProgressRing pct={Math.round(ruta.progreso_porcentaje)} color="#22C55E">
                <span className="text-[22px] font-black text-navy">
                  {Math.round(ruta.progreso_porcentaje)}%
                </span>
              </ProgressRing>
            </div>
            <div className="text-[15px] font-extrabold leading-tight text-navy">
              {ruta.asignatura}
            </div>
            <div className="mt-1 text-xs font-bold text-muted-foreground">
              {ruta.lecciones_completadas} de {ruta.total_lecciones} lecciones
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-[22px] border border-border bg-white px-6 py-10 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="mb-2 text-4xl">📚</div>
          <div className="text-base font-black text-navy">
            Aún no tienes asignaturas asignadas
          </div>
          <div className="mt-1 text-sm font-bold text-muted-foreground">
            Tu maestro pronto subirá el material para empezar. 🌟
          </div>
        </div>
      )}
    </div>
  );
}
