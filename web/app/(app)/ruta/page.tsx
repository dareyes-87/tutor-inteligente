"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  ApiError,
  iniciarLeccion,
  obtenerMisLibros,
  obtenerRacha,
  obtenerRanking,
  obtenerRuta,
  type EstadoLeccion,
  type LeccionEnRuta,
  type LibroDisponible,
  type RutaAprendizaje,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Mascota } from "@/components/mascota";

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
  const [libros, setLibros] = useState<LibroDisponible[] | null>(null);
  const [selectedLibroId, setSelectedLibroId] = useState<number | null>(null);
  const [ruta, setRuta] = useState<RutaAprendizaje | null>(null);
  const [racha, setRacha] = useState(0);
  const [puntos, setPuntos] = useState(0);
  const [cargando, setCargando] = useState(true); // carga inicial (libros + primera ruta)
  const [cambiando, setCambiando] = useState(false); // cambio de pestaña de asignatura
  const [error, setError] = useState(false);
  const [actuando, setActuando] = useState(false);
  const [intento, setIntento] = useState(0); // dispara la (re)carga

  // 1) Libros disponibles del grado + gamificación. Elige el primero por defecto.
  // `cargando` ya arranca en true (y `recargar` lo re-activa), así que no se toca aquí.
  useEffect(() => {
    let activo = true;
    Promise.all([obtenerMisLibros(), obtenerRacha(), obtenerRanking()])
      .then(([librosResp, rachaResp, rankingResp]) => {
        if (!activo) return;
        setLibros(librosResp);
        setRacha(rachaResp.racha_actual);
        const yo = rankingResp.ranking.find((e) => e.posicion === rankingResp.mi_posicion);
        setPuntos(yo?.puntos_totales ?? 0);
        setSelectedLibroId(librosResp.length > 0 ? librosResp[0].libro_id : null);
        setError(false);
        // Sin libros no habrá ruta que cargar: cerrar el loading aquí.
        if (librosResp.length === 0) setCargando(false);
      })
      .catch((err) => {
        if (!activo) return;
        setError(true);
        setCargando(false);
        toast.error(err instanceof ApiError ? err.message : "No se pudo cargar tu ruta");
      });
    return () => {
      activo = false;
    };
  }, [intento]);

  // 2) Ruta del libro seleccionado. `cambiando` (fijado en el click de pestaña)
  // distingue un cambio de asignatura de la carga inicial.
  useEffect(() => {
    if (selectedLibroId == null) return;
    let activo = true;
    obtenerRuta(selectedLibroId)
      .then((r) => {
        if (!activo) return;
        setRuta(r);
        setError(false);
      })
      .catch((err) => {
        if (!activo) return;
        setError(true);
        toast.error(err instanceof ApiError ? err.message : "No se pudo cargar tu ruta");
      })
      .finally(() => {
        if (!activo) return;
        setCargando(false);
        setCambiando(false);
      });
    return () => {
      activo = false;
    };
  }, [selectedLibroId, intento]);

  // Cambiar de asignatura: muestra un estado sutil sin recargar toda la página.
  const seleccionarAsignatura = (libroId: number) => {
    if (libroId === selectedLibroId || cambiando) return;
    setCambiando(true);
    setSelectedLibroId(libroId);
  };

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
  // Sin libros disponibles para el grado (aún no se han subido/indexado).
  if (libros && libros.length === 0) {
    return (
      <div className="px-4 py-9 sm:px-6 md:px-[42px]">
        <div className="mx-auto max-w-[460px] rounded-[24px] border border-border bg-white p-10 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
          <div className="mx-auto mb-4 h-[84px] w-[84px] animate-floaty overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange">
            <Mascota size={84} />
          </div>
          <div className="text-lg font-black text-navy">
            Aún no hay libros disponibles para tu grado.
          </div>
          <div className="mt-2 text-[13.5px] font-bold text-muted-foreground">
            Cuando tu maestra suba un libro, tu ruta de aprendizaje aparecerá aquí.
          </div>
        </div>
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
    <div className="max-w-[1192px] px-4 py-6 sm:px-6 md:px-[42px] md:py-9">
      {/* === SELECTOR DE ASIGNATURA (solo si el grado tiene más de un libro) === */}
      {libros && libros.length > 1 && (
        <div className="mb-6 flex flex-wrap gap-2.5">
          {libros.map((lb) => {
            const activo = lb.libro_id === selectedLibroId;
            return (
              <button
                key={lb.libro_id}
                onClick={() => seleccionarAsignatura(lb.libro_id)}
                disabled={cambiando}
                className={`rounded-[14px] border-2 px-4 py-2.5 text-sm font-extrabold transition disabled:opacity-60 ${
                  activo
                    ? "border-brand-blue bg-brand-blue text-white"
                    : "border-border bg-white text-[#5A6170] hover:bg-muted/60"
                }`}
              >
                📚 {lb.asignatura_nombre}
              </button>
            );
          })}
        </div>
      )}

      {/* Contenido de la ruta; se atenúa mientras se cambia de asignatura. */}
      <div className={cambiando ? "opacity-50 transition-opacity" : "transition-opacity"}>
      {/* === HERO === */}
      <div
        className="relative mb-8 flex flex-col gap-4 overflow-hidden rounded-[24px] px-5 py-6 md:flex-row md:items-center md:gap-6 md:px-[34px] md:py-7"
        style={{ background: "linear-gradient(135deg,#1E2B4D 0%,#2D3F6B 100%)" }}
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage: "radial-gradient(rgba(255,255,255,.06) 1.5px,transparent 1.5px)",
            backgroundSize: "22px 22px",
          }}
        />
        <div className="animate-floaty relative h-[100px] w-[100px] flex-none overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange shadow-[0_8px_28px_rgba(0,0,0,.3)]">
          <Mascota size={100} />
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
        <div className="relative flex w-full flex-row gap-2.5 md:w-auto md:flex-col">
          {[
            { icon: "⭐", val: puntos, label: "puntos" },
            { icon: "🔥", val: racha, label: "racha" },
          ].map((s) => (
            <div
              key={s.label}
              className="flex flex-1 items-center gap-2 rounded-[14px] bg-white/10 px-4 py-2.5 backdrop-blur-sm md:flex-none"
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
      <div className="mb-[22px] flex flex-wrap items-center gap-x-5 gap-y-2 px-1">
        <div className="text-lg font-black text-navy">Tu ruta de aprendizaje</div>
        <div className="hidden flex-1 sm:block" />
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
        <div className="h-14 w-14 flex-none overflow-hidden rounded-full bg-navy ring-[3px] ring-brand-orange">
          <Mascota size={56} />
        </div>
        <div className="text-base font-extrabold text-navy">
          ¡Completa todas las lecciones y desbloquea tu certificado de {ruta.asignatura}! 🏅
        </div>
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
        className="flex flex-1 flex-wrap items-center gap-x-[18px] gap-y-3 rounded-[22px] px-4 py-4 sm:flex-nowrap sm:px-[22px] sm:py-5"
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
          {/* Estrellas de nivel (sistema de 3 niveles) */}
          <div className="mt-1 text-[13px] tracking-wide" title={`Nivel ${l.nivel_completado} de 3`}>
            {l.tiene_corona
              ? "👑 ⭐⭐⭐"
              : "⭐".repeat(l.nivel_completado) + "☆".repeat(3 - l.nivel_completado)}
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
            className="btn-relief w-full flex-none rounded-[14px] bg-brand-orange px-6 py-3 text-[14.5px] font-black text-white disabled:opacity-60 sm:w-auto"
          >
            Empezar 🚀
          </button>
        )}
        {l.estado === "en_progreso" && (
          <div className="flex w-full flex-none flex-col gap-2 sm:w-auto">
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
