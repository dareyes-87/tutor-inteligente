"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth";
import { Mascota } from "@/components/mascota";
import { ProgressRing } from "@/components/progress-ring";
import {
  ASIGNATURAS_PROGRESO,
  PODIO,
  RACHA_DIAS,
  SEMANA_RACHA,
} from "@/lib/mock";

export default function InicioPage() {
  const { user } = useAuth();
  const nombre = user?.nombre ?? "Sofía";

  return (
    <div className="px-[38px] py-[34px]">
      {/* Saludo + CTA */}
      <div className="mb-[26px] flex items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="h-[62px] w-[62px] flex-none overflow-hidden rounded-full bg-navy ring-[3px] ring-brand-orange">
            <Mascota size={62} />
          </div>
          <div>
            <div className="text-[28px] font-black leading-none text-navy">
              ¡Hola, {nombre}! 👋
            </div>
            <div className="mt-[5px] text-[15px] font-semibold text-muted-foreground">
              ¿List{user?.rol === "estudiante" ? "a" : "@"} para seguir aprendiendo hoy?
            </div>
          </div>
        </div>
        <Link
          href="/chat"
          className="btn-relief flex items-center gap-2.5 rounded-[18px] bg-brand-blue px-[26px] py-4 text-[17px] font-black text-white"
          style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
        >
          💬 Pregúntale al tutor
        </Link>
      </div>

      {/* Racha + ranking */}
      <div className="mb-7 flex gap-5">
        {/* Racha */}
        <div className="flex flex-1 items-center gap-[22px] rounded-[22px] bg-gradient-to-br from-[#FB923C] to-brand-orange px-[26px] py-6 text-white shadow-[0_10px_24px_rgba(249,115,22,.28)]">
          <div className="animate-flame text-[62px] leading-none">🔥</div>
          <div className="flex-1">
            <div className="text-[34px] font-black leading-none">{RACHA_DIAS} días</div>
            <div className="text-[15px] font-extrabold opacity-95">
              seguidos · ¡no rompas la racha!
            </div>
            <div className="mt-3.5 flex gap-[7px]">
              {SEMANA_RACHA.map((d, i) => (
                <div key={i} className="flex-1 text-center">
                  <div
                    className="mx-auto grid h-[30px] w-[30px] place-items-center rounded-full text-sm"
                    style={{ background: d.done ? "rgba(255,255,255,.35)" : "rgba(255,255,255,.12)" }}
                  >
                    {d.done ? "🔥" : ""}
                  </div>
                  <div className="mt-1 text-[10px] font-extrabold opacity-90">{d.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Mini ranking */}
        <div className="w-[430px] flex-none rounded-[22px] border border-border bg-white px-6 py-[22px] shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="mb-1.5 flex items-center justify-between">
            <div className="text-base font-black text-navy">🏆 Tu salón</div>
            <Link href="/ranking" className="text-[13px] font-extrabold text-brand-blue">
              Ver ranking →
            </Link>
          </div>
          <div className="mb-3.5 text-sm font-bold text-muted-foreground">
            Vas en el <span className="font-black text-brand-orange">Puesto #3</span>
          </div>
          <div className="flex h-[120px] items-end justify-center gap-3">
            {PODIO.map((p) => (
              <div key={p.pos} className="w-24 text-center">
                <div className="text-[22px]">{p.medal}</div>
                <div
                  className="mx-auto mb-1.5 mt-1 grid h-[46px] w-[46px] place-items-center overflow-hidden rounded-full bg-[#EDE7DD] text-base font-black text-navy"
                  style={{ boxShadow: `0 0 0 3px ${p.ring}` }}
                >
                  {p.initial}
                </div>
                <div
                  className="grid place-items-start justify-center rounded-t-xl pt-2 text-[15px] font-black text-navy"
                  style={{ background: p.bg, height: p.h }}
                >
                  {p.pos}
                </div>
                <div className="mt-[5px] text-[11px] font-extrabold text-[#5A6170]">{p.name}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Asignaturas */}
      <div className="mb-4 flex items-center justify-between">
        <div className="text-xl font-black text-navy">Mis asignaturas</div>
        <Link href="/progreso" className="text-[13px] font-extrabold text-brand-blue">
          Ver todas →
        </Link>
      </div>
      <div className="grid grid-cols-4 gap-[18px]">
        {ASIGNATURAS_PROGRESO.map((s) => (
          <div
            key={s.name}
            className="rounded-[22px] border border-border bg-white p-[22px] text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]"
          >
            <div
              className="mx-auto mb-3.5 grid h-12 w-12 place-items-center rounded-[14px] text-2xl"
              style={{ background: s.soft }}
            >
              {s.icon}
            </div>
            <div className="mx-auto mb-3.5 w-fit">
              <ProgressRing pct={s.pct} color={s.color}>
                <span className="text-[22px] font-black text-navy">{s.pct}%</span>
              </ProgressRing>
            </div>
            <div className="text-[15px] font-extrabold leading-tight text-navy">{s.name}</div>
            <div className="mt-1 text-xs font-bold text-muted-foreground">{s.meta}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
