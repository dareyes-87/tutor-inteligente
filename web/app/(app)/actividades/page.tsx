"use client";

import { useState } from "react";
import { toast } from "sonner";

import {
  ApiError,
  generarActividad,
  responderActividad,
  type ActividadResponse,
  type ResultadoResponse,
  type TipoActividad,
} from "@/lib/api";
import { ASIGNATURAS } from "@/lib/constants";
import { Mascota } from "@/components/mascota";

/** Configuración visual de los 5 tipos de actividad del backend. */
const TIPOS: {
  key: TipoActividad;
  label: string;
  icon: string;
  color: string;
  soft: string;
}[] = [
  { key: "opcion_multiple", label: "Opción múltiple", icon: "☑️", color: "#2563EB", soft: "#EAF1FF" },
  { key: "verdadero_falso", label: "Verdadero / Falso", icon: "⚖️", color: "#8B5CF6", soft: "#F1ECFE" },
  { key: "completar", label: "Completar", icon: "✏️", color: "#F97316", soft: "#FFF1E7" },
  { key: "ordenar", label: "Ordenar", icon: "🔢", color: "#22C55E", soft: "#E9F9EF" },
  { key: "respuesta_corta", label: "Respuesta corta", icon: "💬", color: "#EC4899", soft: "#FCE9F2" },
];

const tipoMeta = (t: TipoActividad) => TIPOS.find((x) => x.key === t)!;

type Fase = "seleccion" | "generando" | "respondiendo" | "resultado";

export default function ActividadesPage() {
  const asignaturaId = ASIGNATURAS[0].id;

  const [fase, setFase] = useState<Fase>("seleccion");
  const [tema, setTema] = useState("");
  const [actividad, setActividad] = useState<ActividadResponse | null>(null);
  const [resultado, setResultado] = useState<ResultadoResponse | null>(null);

  // Respuestas del estudiante (según el tipo)
  const [seleccion, setSeleccion] = useState(""); // opción / V-F / completar / corta
  const [orden, setOrden] = useState<string[]>([]); // ordenar
  const [enviando, setEnviando] = useState(false);

  async function generar(tipo: TipoActividad) {
    setFase("generando");
    setActividad(null);
    setResultado(null);
    setSeleccion("");
    setOrden([]);
    try {
      const act = await generarActividad(asignaturaId, tipo, tema.trim() || null);
      setActividad(act);
      if (tipo === "ordenar") {
        const c = act.contenido as Record<string, unknown>;
        setOrden(((c.elementos_desordenados as string[]) ?? []).slice());
      }
      setFase("respondiendo");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "No se pudo conectar con el servidor";
      toast.error(msg);
      setFase("seleccion");
    }
  }

  function buildRespuesta(tipo: TipoActividad): Record<string, unknown> {
    switch (tipo) {
      case "verdadero_falso":
        return { respuesta: seleccion === "true" };
      case "ordenar":
        return { orden };
      default:
        return { respuesta: seleccion };
    }
  }

  const respuestaLista = (() => {
    if (!actividad) return false;
    if (actividad.tipo === "ordenar") return orden.length > 0;
    return seleccion.trim() !== "";
  })();

  async function enviar() {
    if (!actividad || !respuestaLista || enviando) return;
    setEnviando(true);
    try {
      const res = await responderActividad(actividad.id, buildRespuesta(actividad.tipo));
      setResultado(res);
      setFase("resultado");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "No se pudo conectar con el servidor";
      toast.error(msg);
    } finally {
      setEnviando(false);
    }
  }

  function reiniciar() {
    setFase("seleccion");
    setActividad(null);
    setResultado(null);
    setSeleccion("");
    setOrden([]);
  }

  function mover(i: number, dir: -1 | 1) {
    setOrden((prev) => {
      const next = prev.slice();
      const j = i + dir;
      if (j < 0 || j >= next.length) return prev;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  return (
    <div className="px-[38px] py-[34px]">
      <div className="mb-1 text-2xl font-black text-navy">Actividades de hoy</div>
      <div className="mb-[22px] text-sm font-bold text-muted-foreground">
        Practica y gana estrellas ⭐ · {ASIGNATURAS[0].nombre}
      </div>

      {fase === "seleccion" && (
        <Seleccion tema={tema} setTema={setTema} onGenerar={generar} />
      )}

      {fase === "generando" && <Generando />}

      {fase === "respondiendo" && actividad && (
        <Pregunta
          actividad={actividad}
          seleccion={seleccion}
          setSeleccion={setSeleccion}
          orden={orden}
          mover={mover}
          enviando={enviando}
          puedeEnviar={respuestaLista}
          onEnviar={enviar}
          onCancelar={reiniciar}
        />
      )}

      {fase === "resultado" && actividad && resultado && (
        <Resultado actividad={actividad} resultado={resultado} onReiniciar={reiniciar} />
      )}
    </div>
  );
}

/* ---------------- Selección ---------------- */

function Seleccion({
  tema,
  setTema,
  onGenerar,
}: {
  tema: string;
  setTema: (v: string) => void;
  onGenerar: (t: TipoActividad) => void;
}) {
  return (
    <div className="flex items-start gap-[26px]">
      <div className="flex-1">
        <label className="mb-[7px] block text-[13px] font-extrabold text-[#5A6170]">
          Tema (opcional)
        </label>
        <input
          value={tema}
          onChange={(e) => setTema(e.target.value)}
          placeholder="Ej: el ciclo del agua, las plantas…"
          className="mb-6 w-full rounded-2xl border-2 border-border bg-muted/50 px-4 py-[14px] text-[15px] font-semibold text-navy outline-none placeholder:text-[#B6BBC6] focus:border-brand-orange"
        />
        <div className="flex flex-col gap-3.5">
          {TIPOS.map((a) => (
            <div
              key={a.key}
              className="flex items-center gap-[18px] rounded-[20px] border border-border bg-white px-[22px] py-[18px] shadow-[0_5px_16px_rgba(30,43,77,.05)]"
            >
              <div
                className="grid h-14 w-14 flex-none place-items-center rounded-2xl text-[26px]"
                style={{ background: a.soft }}
              >
                {a.icon}
              </div>
              <div className="min-w-0 flex-1">
                <div
                  className="mb-1.5 inline-block rounded-full px-2.5 py-[3px] text-[11.5px] font-extrabold"
                  style={{ color: a.color, background: a.soft }}
                >
                  {a.label}
                </div>
                <div className="text-[15px] font-bold text-muted-foreground">
                  El tutor genera la pregunta desde tu libro.
                </div>
              </div>
              <button
                onClick={() => onGenerar(a.key)}
                className="btn-relief rounded-[14px] bg-brand-blue px-6 py-3 text-sm font-extrabold text-white"
                style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
              >
                Practicar
              </button>
            </div>
          ))}
        </div>
      </div>

      <aside className="w-[300px] flex-none rounded-[22px] border border-border bg-white p-6 text-center shadow-[0_6px_20px_rgba(30,43,77,.05)]">
        <div className="mx-auto mb-3 h-[74px] w-[74px] overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange">
          <Mascota size={74} />
        </div>
        <div className="text-lg font-black text-navy">¡A practicar!</div>
        <div className="mt-1.5 text-[13.5px] font-bold text-muted-foreground">
          Elige un tipo de actividad. Si quieres, escribe un tema y el tutor creará una pregunta
          basada en tu libro.
        </div>
      </aside>
    </div>
  );
}

/* ---------------- Generando ---------------- */

function Generando() {
  return (
    <div className="mx-auto max-w-[640px] rounded-[24px] border border-border bg-white px-8 py-14 text-center shadow-[0_8px_22px_rgba(30,43,77,.06)]">
      <div className="mx-auto mb-4 h-[84px] w-[84px] animate-floaty overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange">
        <Mascota size={84} />
      </div>
      <div className="text-xl font-black text-navy">Generando tu actividad…</div>
      <div className="mt-2 text-sm font-bold text-muted-foreground">
        El tutor está preparando una pregunta desde tu libro. Esto puede tardar unos segundos.
      </div>
    </div>
  );
}

/* ---------------- Pregunta ---------------- */

function Pregunta({
  actividad,
  seleccion,
  setSeleccion,
  orden,
  mover,
  enviando,
  puedeEnviar,
  onEnviar,
  onCancelar,
}: {
  actividad: ActividadResponse;
  seleccion: string;
  setSeleccion: (v: string) => void;
  orden: string[];
  mover: (i: number, dir: -1 | 1) => void;
  enviando: boolean;
  puedeEnviar: boolean;
  onEnviar: () => void;
  onCancelar: () => void;
}) {
  const meta = tipoMeta(actividad.tipo);
  const c = actividad.contenido as Record<string, unknown>;
  const str = (k: string) => String(c[k] ?? "");

  return (
    <div className="mx-auto max-w-[720px] rounded-[24px] border border-border bg-white p-8 shadow-[0_8px_22px_rgba(30,43,77,.06)]">
      <div
        className="mb-4 inline-block rounded-full px-3 py-1 text-[11.5px] font-extrabold"
        style={{ color: meta.color, background: meta.soft }}
      >
        {meta.icon} {meta.label}
        {actividad.tema ? ` · ${actividad.tema}` : ""}
      </div>

      {/* Opción múltiple */}
      {actividad.tipo === "opcion_multiple" && (
        <>
          <div className="mb-5 text-xl font-extrabold text-navy">{str("pregunta")}</div>
          <div className="flex flex-col gap-3">
            {((c.opciones as string[]) ?? []).map((op) => {
              const activa = seleccion === op;
              return (
                <button
                  key={op}
                  onClick={() => setSeleccion(op)}
                  className={`rounded-2xl border-2 px-5 py-4 text-left text-[15px] font-bold transition-colors ${
                    activa
                      ? "border-brand-blue bg-[#EAF1FF] text-[#1E3A8A]"
                      : "border-border bg-muted/40 text-navy hover:border-brand-blue/40"
                  }`}
                >
                  {op}
                </button>
              );
            })}
          </div>
        </>
      )}

      {/* Verdadero / Falso */}
      {actividad.tipo === "verdadero_falso" && (
        <>
          <div className="mb-5 text-xl font-extrabold text-navy">{str("afirmacion")}</div>
          <div className="flex gap-4">
            {[
              { val: "true", label: "Verdadero", icon: "✓", color: "#22C55E", soft: "#E9F9EF" },
              { val: "false", label: "Falso", icon: "✗", color: "#EF4444", soft: "#FDECEC" },
            ].map((o) => {
              const activa = seleccion === o.val;
              return (
                <button
                  key={o.val}
                  onClick={() => setSeleccion(o.val)}
                  className="flex-1 rounded-2xl border-2 px-5 py-6 text-lg font-black transition-colors"
                  style={{
                    borderColor: activa ? o.color : "var(--border)",
                    background: activa ? o.soft : "transparent",
                    color: activa ? o.color : "#1E2B4D",
                  }}
                >
                  {o.icon} {o.label}
                </button>
              );
            })}
          </div>
        </>
      )}

      {/* Completar */}
      {actividad.tipo === "completar" && (
        <>
          <div className="mb-4 text-xl font-extrabold leading-relaxed text-navy">
            {str("oracion")}
          </div>
          <input
            value={seleccion}
            onChange={(e) => setSeleccion(e.target.value)}
            placeholder="Escribe la palabra que falta…"
            className="w-full rounded-2xl border-2 border-border bg-muted/50 px-4 py-[14px] text-[15px] font-semibold text-navy outline-none placeholder:text-[#B6BBC6] focus:border-brand-orange"
          />
          {str("pista") && (
            <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-accent px-[13px] py-[7px] text-[12.5px] font-extrabold text-accent-foreground">
              💡 Pista: {str("pista")}
            </div>
          )}
        </>
      )}

      {/* Ordenar */}
      {actividad.tipo === "ordenar" && (
        <>
          <div className="mb-5 text-xl font-extrabold text-navy">{str("instruccion")}</div>
          <div className="flex flex-col gap-2.5">
            {orden.map((el, i) => (
              <div
                key={el}
                className="flex items-center gap-3 rounded-2xl border-2 border-border bg-muted/40 px-4 py-3.5"
              >
                <div className="grid h-7 w-7 flex-none place-items-center rounded-full bg-brand-green text-sm font-black text-white">
                  {i + 1}
                </div>
                <div className="flex-1 text-[15px] font-bold text-navy">{el}</div>
                <div className="flex flex-none gap-1">
                  <button
                    onClick={() => mover(i, -1)}
                    disabled={i === 0}
                    className="grid h-8 w-8 place-items-center rounded-lg border border-border bg-white text-navy disabled:opacity-30"
                    aria-label="Subir"
                  >
                    ↑
                  </button>
                  <button
                    onClick={() => mover(i, 1)}
                    disabled={i === orden.length - 1}
                    className="grid h-8 w-8 place-items-center rounded-lg border border-border bg-white text-navy disabled:opacity-30"
                    aria-label="Bajar"
                  >
                    ↓
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Respuesta corta */}
      {actividad.tipo === "respuesta_corta" && (
        <>
          <div className="mb-4 text-xl font-extrabold text-navy">{str("pregunta")}</div>
          <textarea
            value={seleccion}
            onChange={(e) => setSeleccion(e.target.value)}
            placeholder="Escribe tu respuesta…"
            rows={4}
            className="w-full resize-none rounded-2xl border-2 border-border bg-muted/50 px-4 py-3.5 text-[15px] font-semibold text-navy outline-none placeholder:text-[#B6BBC6] focus:border-brand-orange"
          />
        </>
      )}

      <div className="mt-7 flex items-center justify-between gap-3">
        <button
          onClick={onCancelar}
          className="rounded-[14px] border-2 border-border bg-white px-5 py-3 text-sm font-extrabold text-[#5A6170] hover:bg-muted/60"
        >
          ← Cambiar actividad
        </button>
        <button
          onClick={onEnviar}
          disabled={!puedeEnviar || enviando}
          className="btn-relief rounded-[16px] bg-brand-orange px-8 py-3.5 text-base font-black text-white disabled:opacity-50"
        >
          {enviando ? "Revisando…" : "Enviar respuesta"}
        </button>
      </div>
    </div>
  );
}

/* ---------------- Resultado ---------------- */

function Resultado({
  actividad,
  resultado,
  onReiniciar,
}: {
  actividad: ActividadResponse;
  resultado: ResultadoResponse;
  onReiniciar: () => void;
}) {
  const aprobado = resultado.puntaje >= 60;
  const rc = resultado.respuesta_correcta as Record<string, unknown>;

  const correctaTexto = (() => {
    switch (actividad.tipo) {
      case "ordenar":
        return ((rc.orden_correcto as string[]) ?? []).join("  →  ");
      case "verdadero_falso":
        return rc.respuesta_correcta ? "Verdadero" : "Falso";
      default:
        return String(rc.respuesta_correcta ?? "");
    }
  })();

  return (
    <div
      className="mx-auto max-w-[640px] rounded-[24px] border-2 bg-white p-8 text-center"
      style={{
        borderColor: aprobado ? "#BBF7D0" : "#FECACA",
        boxShadow: aprobado
          ? "0 8px 22px rgba(34,197,94,.12)"
          : "0 8px 22px rgba(239,68,68,.1)",
      }}
    >
      <div
        className="mx-auto mb-3 h-[84px] w-[84px] overflow-hidden rounded-full bg-navy"
        style={{ boxShadow: `0 0 0 4px ${aprobado ? "#22C55E" : "#EF4444"}` }}
      >
        <Mascota size={84} />
      </div>

      <div
        className="text-[24px] font-black"
        style={{ color: aprobado ? "#16A34A" : "#DC2626" }}
      >
        {aprobado ? "¡Bien hecho! 🎉" : "¡Casi! Inténtalo otra vez 💪"}
      </div>

      <div
        className="mt-3 inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-base font-black"
        style={{
          background: aprobado ? "#E9F9EF" : "#FDECEC",
          color: aprobado ? "#16A34A" : "#DC2626",
        }}
      >
        {Math.round(resultado.puntaje)} / 100 ⭐
      </div>

      <div className="mx-auto mt-5 max-w-[520px] text-[15px] font-semibold leading-relaxed text-[#5A6170]">
        {resultado.retroalimentacion}
      </div>

      {correctaTexto && (
        <div className="mx-auto mt-4 max-w-[520px] rounded-2xl bg-muted/50 px-4 py-3 text-sm font-bold text-navy">
          Respuesta correcta: <span className="text-brand-green">{correctaTexto}</span>
        </div>
      )}

      <button
        onClick={onReiniciar}
        className="btn-relief mt-7 rounded-[16px] bg-brand-blue px-8 py-3.5 text-base font-black text-white"
        style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
      >
        Otra actividad →
      </button>
    </div>
  );
}
