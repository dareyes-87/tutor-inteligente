"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  ApiError,
  iniciarLeccion,
  obtenerRacha,
  obtenerRanking,
  obtenerRuta,
  type EstadoLeccion,
  type LeccionEnRuta,
  type RutaAprendizaje,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Mascota } from "@/components/mascota";

const LIBRO_ID = 1; // único libro por ahora

// Iconos kid-friendly por lección (el backend no guarda emoji): se ciclan por orden.
const ICONOS = ["🌿", "💧", "🧪", "⚡", "🪐", "🌻", "🦎", "🫀", "🔬", "🌎", "🧬", "🍎"];
const iconoLeccion = (orden: number) => ICONOS[(orden - 1) % ICONOS.length];

interface EstiloEstado {
  glyph: string;
  glyphColor: string;
  circuloBg: string;
  pulse: boolean;
  sparkle: boolean;
  cardBg: string;
  cardBorder: string;
  cardShadow: string;
  opacity: string;
  iconBg: string;
  nameColor: string;
  descColor: string;
  chip: string;
  chipColor: string;
  chipBg: string;
  barColor: string;
}

function estiloDe(estado: EstadoLeccion): EstiloEstado {
  switch (estado) {
    case "completada":
      return {
        glyph: "⭐", glyphColor: "#fff", circuloBg: "#22C55E", pulse: false, sparkle: true,
        cardBg: "#FFFFFF", cardBorder: "1px solid #BBF7D0",
        cardShadow: "0 5px 16px rgba(34,197,94,.08)", opacity: "1", iconBg: "#E9F9EF",
        nameColor: "#1E2B4D", descColor: "#8A8F9C",
        chip: "✅ Completada", chipColor: "#16A34A", chipBg: "#E9F9EF", barColor: "#22C55E",
      };
    case "en_progreso":
      return {
        glyph: "📖", glyphColor: "#fff", circuloBg: "#F97316", pulse: false, sparkle: false,
        cardBg: "#FFFFFF", cardBorder: "2px solid #F97316",
        cardShadow: "0 8px 28px rgba(249,115,22,.14)", opacity: "1", iconBg: "#FFF1E7",
        nameColor: "#1E2B4D", descColor: "#8A8F9C",
        chip: "📖 En progreso", chipColor: "#EA580C", chipBg: "#FFF1E7", barColor: "#F97316",
      };
    case "disponible":
      return {
        glyph: "▶", glyphColor: "#fff", circuloBg: "#2563EB", pulse: true, sparkle: false,
        cardBg: "#FFFFFF", cardBorder: "2px solid #2563EB",
        cardShadow: "0 8px 28px rgba(37,99,235,.12)", opacity: "1", iconBg: "#EAF1FF",
        nameColor: "#1E2B4D", descColor: "#8A8F9C",
        chip: "🔵 Disponible", chipColor: "#2563EB", chipBg: "#EAF1FF", barColor: "#2563EB",
      };
    default: // bloqueada
      return {
        glyph: "🔒", glyphColor: "#A8A29E", circuloBg: "#E8E4DB", pulse: false, sparkle: false,
        cardBg: "#FAFAF8", cardBorder: "1px solid #E8E4DB",
        cardShadow: "0 2px 8px rgba(30,43,77,.03)", opacity: "0.7", iconBg: "#F1EDE5",
        nameColor: "#A8A29E", descColor: "#C4BFB6",
        chip: "", chipColor: "", chipBg: "", barColor: "#CBD5E1",
      };
  }
}

export default function RutaPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [ruta, setRuta] = useState<RutaAprendizaje | null>(null);
  const [racha, setRacha] = useState(0);
  const [puntos, setPuntos] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);
  const [actuando, setActuando] = useState(false);
  const [intento, setIntento] = useState(0); // dispara la (re)carga

  // El effect solo hace setState dentro de los callbacks de la promesa.
  useEffect(() => {
    let activo = true;
    Promise.all([obtenerRuta(LIBRO_ID), obtenerRacha(), obtenerRanking()])
      .then(([r, rachaResp, rankingResp]) => {
        if (!activo) return;
        setRuta(r);
        setRacha(rachaResp.racha_actual);
        const yo = rankingResp.ranking.find((e) => e.posicion === rankingResp.mi_posicion);
        setPuntos(yo?.puntos_totales ?? 0);
        setError(false);
      })
      .catch((err) => {
        if (!activo) return;
        setError(true);
        toast.error(err instanceof ApiError ? err.message : "No se pudo cargar tu ruta");
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

  async function empezar(leccionId: number) {
    if (actuando) return;
    setActuando(true);
    try {
      await iniciarLeccion(leccionId);
      router.push(`/ruta/${leccionId}/estudiar`); // tras iniciar, va a estudiar
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo empezar la lección");
      setActuando(false);
    }
  }

  if (cargando) {
    return (
      <div className="px-[42px] py-9 text-center text-sm font-bold text-muted-foreground">
        Cargando tu ruta…
      </div>
    );
  }
  if (error || !ruta) {
    return (
      <div className="px-[42px] py-9">
        <div className="mx-auto max-w-[420px] rounded-[22px] border border-border bg-white p-8 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="text-base font-extrabold text-navy">No se pudo cargar tu ruta.</div>
          <button
            onClick={recargar}
            className="btn-relief mt-4 rounded-[14px] bg-brand-blue px-6 py-3 text-sm font-extrabold text-white"
            style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  const leccionActual = Math.min(ruta.total_lecciones, ruta.lecciones_completadas + 1);
  const nombre = user?.nombre ?? "estudiante";

  return (
    <div className="max-w-[1192px] px-[42px] py-9">
      {/* === HERO === */}
      <div
        className="relative mb-8 flex items-center gap-6 overflow-hidden rounded-[24px] px-[34px] py-7"
        style={{ background: "linear-gradient(135deg,#1E2B4D 0%,#2D3F6B 100%)" }}
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage: "radial-gradient(rgba(255,255,255,.06) 1.5px,transparent 1.5px)",
            backgroundSize: "22px 22px",
          }}
        />
        <div className="animate-floaty relative h-[90px] w-[90px] flex-none overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange shadow-[0_8px_28px_rgba(0,0,0,.3)]">
          <Mascota size={90} />
        </div>
        <div className="relative flex-1">
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-brand-orange/20 px-3.5 py-[5px] text-[12.5px] font-extrabold text-[#FED7AA]">
            🐯 ¡Tú puedes, {nombre}!
          </div>
          <div className="text-[28px] font-black leading-tight text-white">
            Lección {leccionActual} de {ruta.total_lecciones}
          </div>
          <div className="mt-[5px] text-[15px] font-bold text-[#CBD5E1]">
            {ruta.asignatura} · 5to Primaria
          </div>
          <div className="mt-4 flex items-center gap-3.5">
            <div className="h-3.5 flex-1 overflow-hidden rounded-full bg-white/[0.12]">
              <div
                className="animate-shimmer h-full rounded-full"
                style={{
                  width: `${ruta.progreso_porcentaje}%`,
                  background: "linear-gradient(90deg,#F97316,#FB923C)",
                }}
              />
            </div>
            <div className="text-[15px] font-black text-brand-orange">
              {Math.round(ruta.progreso_porcentaje)}%
            </div>
          </div>
        </div>
        <div className="relative flex flex-col gap-2.5">
          {[
            { icon: "⭐", val: puntos, label: "puntos" },
            { icon: "🔥", val: racha, label: "racha" },
          ].map((s) => (
            <div
              key={s.label}
              className="flex items-center gap-2 rounded-[14px] bg-white/10 px-4 py-2.5 backdrop-blur-sm"
            >
              <span className="text-xl">{s.icon}</span>
              <div>
                <div className="text-lg font-black leading-none text-white">{s.val}</div>
                <div className="text-[10.5px] font-extrabold text-[#94A3B8]">{s.label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* === LEYENDA === */}
      <div className="mb-[22px] flex items-center gap-5 px-1">
        <div className="text-lg font-black text-navy">Tu ruta de aprendizaje</div>
        <div className="flex-1" />
        <div className="flex gap-4 text-xs font-extrabold text-muted-foreground">
          {[
            { c: "#22C55E", t: "Completada" },
            { c: "#2563EB", t: "Disponible" },
            { c: "#CBD5E1", t: "Bloqueada" },
          ].map((l) => (
            <div key={l.t} className="flex items-center gap-1.5">
              <div className="h-3.5 w-3.5 rounded-full" style={{ background: l.c }} />
              {l.t}
            </div>
          ))}
        </div>
      </div>

      {/* === LISTA DE LECCIONES === */}
      <div className="relative flex flex-col">
        {/* línea conectora punteada detrás */}
        <div
          className="absolute left-12 top-9 bottom-9 z-0 w-1 rounded-sm"
          style={{
            background:
              "repeating-linear-gradient(180deg,#E2DED5 0px,#E2DED5 8px,transparent 8px,transparent 16px)",
          }}
        />
        {ruta.lecciones.map((l) => (
          <LeccionFila key={l.id} leccion={l} onEmpezar={empezar} actuando={actuando} />
        ))}
      </div>

      {/* === FOOTER MOTIVACIONAL === */}
      <div className="mt-3 flex items-center justify-center gap-4 rounded-[20px] border border-border bg-white p-[22px] shadow-[0_5px_16px_rgba(30,43,77,.05)]">
        <div className="h-[52px] w-[52px] flex-none overflow-hidden rounded-full bg-navy ring-[3px] ring-brand-orange">
          <Mascota size={52} />
        </div>
        <div className="text-base font-extrabold text-navy">
          ¡Completa todas las lecciones y desbloquea tu certificado de {ruta.asignatura}! 🏅
        </div>
      </div>
    </div>
  );
}

function LeccionFila({
  leccion: l,
  onEmpezar,
  actuando,
}: {
  leccion: LeccionEnRuta;
  onEmpezar: (id: number) => void;
  actuando: boolean;
}) {
  const s = estiloDe(l.estado);
  const pct =
    l.actividades_requeridas > 0
      ? Math.round((l.actividades_completadas / l.actividades_requeridas) * 100)
      : 0;
  const mostrarBarra = l.estado === "completada" || l.estado === "en_progreso";

  return (
    <div className="relative z-[1] mb-4 flex items-stretch gap-[22px]">
      {/* columna del icono de estado */}
      <div className="flex w-14 flex-none justify-center pt-7">
        <div
          className={`grid h-12 w-12 place-items-center rounded-full ${s.pulse ? "animate-pulse-ring" : ""}`}
          style={{ background: s.circuloBg }}
        >
          <span
            className={`text-[20px] ${s.sparkle ? "animate-sparkle" : ""}`}
            style={{ color: s.glyphColor }}
          >
            {s.glyph}
          </span>
        </div>
      </div>

      {/* tarjeta */}
      <div
        className="flex flex-1 items-center gap-[18px] rounded-[22px] px-[22px] py-5"
        style={{
          background: s.cardBg,
          border: s.cardBorder,
          boxShadow: s.cardShadow,
          opacity: s.opacity,
        }}
      >
        <div
          className="grid h-14 w-14 flex-none place-items-center rounded-2xl text-[28px]"
          style={{ background: s.iconBg }}
        >
          {iconoLeccion(l.orden)}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="rounded-full px-2.5 py-[3px] text-[11.5px] font-extrabold"
              style={{ color: s.descColor, background: s.iconBg }}
            >
              Lección {l.orden}
            </span>
            {s.chip && (
              <span
                className="rounded-full px-2.5 py-[3px] text-[11px] font-extrabold"
                style={{ color: s.chipColor, background: s.chipBg }}
              >
                {s.chip}
              </span>
            )}
          </div>
          <div
            className="mt-1.5 text-[17px] font-black leading-tight"
            style={{ color: s.nameColor }}
          >
            {l.nombre}
          </div>
          {l.descripcion && (
            <div className="mt-1 text-[13px] font-bold" style={{ color: s.descColor }}>
              {l.descripcion}
            </div>
          )}
          {mostrarBarra && (
            <div className="mt-2.5 flex items-center gap-2.5">
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-[#ECE7DE]">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${pct}%`, background: s.barColor }}
                />
              </div>
              <span className="text-xs font-black" style={{ color: s.barColor }}>
                {l.actividades_completadas}/{l.actividades_requeridas}
              </span>
            </div>
          )}
        </div>

        {/* botones / puntaje según estado */}
        {l.estado === "disponible" && (
          <button
            onClick={() => onEmpezar(l.id)}
            disabled={actuando}
            className="btn-relief flex-none rounded-[14px] bg-brand-orange px-6 py-3 text-[14.5px] font-black text-white disabled:opacity-60"
          >
            Empezar 🚀
          </button>
        )}
        {l.estado === "en_progreso" && (
          <div className="flex flex-none flex-col gap-2">
            <Link
              href={`/ruta/${l.id}/estudiar`}
              className="btn-relief rounded-[14px] bg-brand-orange px-6 py-3 text-center text-[14.5px] font-black text-white"
            >
              Estudiar 📖
            </Link>
            <Link
              href={`/ruta/${l.id}/practicar`}
              className="btn-relief rounded-[14px] bg-brand-blue px-6 py-2.5 text-center text-[13px] font-extrabold text-white"
              style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
            >
              Practicar 🎯
            </Link>
          </div>
        )}
        {l.estado === "completada" && (
          <div className="flex flex-none flex-col items-center gap-0.5 pr-2">
            <div className="text-[22px] font-black text-brand-green">
              {Math.round(l.puntaje_promedio)}
            </div>
            <div className="text-[11px] font-extrabold text-muted-foreground">puntos</div>
          </div>
        )}
      </div>
    </div>
  );
}
