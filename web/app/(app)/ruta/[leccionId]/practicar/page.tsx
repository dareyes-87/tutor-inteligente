"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  generarActividad,
  iniciarLeccion,
  obtenerMiLibro,
  obtenerRuta,
  responderActividad,
  type ActividadResponse,
  type ResultadoResponse,
  type TipoActividad,
} from "@/lib/api";
import { ASIGNATURAS } from "@/lib/constants";
import { Mascota } from "@/components/mascota";

const ASIGNATURA_ID = ASIGNATURAS[0].id; // Ciencias Naturales
const TIPOS: TipoActividad[] = [
  "opcion_multiple",
  "verdadero_falso",
  "completar",
  "ordenar",
  "respuesta_corta",
];

type Fase = "cargando" | "error" | "ejercicio" | "resultado";

interface Respuesta {
  seleccion: string;
  orden: string[];
}

function initRespuesta(act: ActividadResponse): Respuesta {
  const c = act.contenido as Record<string, unknown>;
  return {
    seleccion: "",
    orden: act.tipo === "ordenar" ? [...((c.elementos_desordenados as string[]) ?? [])] : [],
  };
}

export default function PracticarPage() {
  const router = useRouter();
  const params = useParams<{ leccionId: string }>();
  const leccionId = Number(params.leccionId);

  const [fase, setFase] = useState<Fase>("cargando");
  const [acts, setActs] = useState<ActividadResponse[]>([]);
  const [idx, setIdx] = useState(0);
  const [resp, setResp] = useState<Respuesta>({ seleccion: "", orden: [] });
  const [feedback, setFeedback] = useState<ResultadoResponse | null>(null);
  const [resultados, setResultados] = useState<ResultadoResponse[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [inicio, setInicio] = useState(0);
  const [duracion, setDuracion] = useState(0); // segundos, fijado al terminar
  const [desbloqueo, setDesbloqueo] = useState(false);
  const [intento, setIntento] = useState(0);

  // Carga: asegura en_progreso y genera las 5 actividades.
  useEffect(() => {
    let activo = true;
    (async () => {
      try {
        const mi = await obtenerMiLibro();
        const ruta = await obtenerRuta(mi.libro_id);
        const leccion = ruta.lecciones.find((l) => l.id === leccionId);
        if (!leccion) throw new Error("Lección no encontrada");
        if (leccion.estado === "bloqueada") throw new Error("Esta lección está bloqueada");
        if (leccion.estado === "disponible") {
          await iniciarLeccion(leccionId); // queda en_progreso → el backend cuenta los puntajes
        }
        const tema = leccion.tema_clave || leccion.nombre;
        const settled = await Promise.allSettled(
          TIPOS.map((t) => generarActividad(ASIGNATURA_ID, t, tema)),
        );
        if (!activo) return;
        const generadas = settled
          .filter((s): s is PromiseFulfilledResult<ActividadResponse> => s.status === "fulfilled")
          .map((s) => s.value);
        if (generadas.length === 0) {
          setFase("error");
          return;
        }
        setActs(generadas);
        setResp(initRespuesta(generadas[0]));
        setInicio(Date.now());
        setFase("ejercicio");
      } catch (err) {
        if (!activo) return;
        toast.error(err instanceof Error ? err.message : "No se pudo preparar la práctica");
        setFase("error");
      }
    })();
    return () => {
      activo = false;
    };
  }, [leccionId, intento]);

  const act = acts[idx];

  function respuestaLista(): boolean {
    if (!act) return false;
    if (act.tipo === "ordenar") return resp.orden.length > 0;
    return resp.seleccion.trim() !== "";
  }

  function buildRespuesta(): Record<string, unknown> {
    if (act.tipo === "verdadero_falso") return { respuesta: resp.seleccion === "true" };
    if (act.tipo === "ordenar") return { orden: resp.orden };
    return { respuesta: resp.seleccion };
  }

  async function enviar() {
    if (!act || !respuestaLista() || enviando) return;
    setEnviando(true);
    try {
      const res = await responderActividad(act.id, buildRespuesta());
      setFeedback(res);
      setResultados((prev) => [...prev, res]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo enviar tu respuesta");
    } finally {
      setEnviando(false);
    }
  }

  async function continuar() {
    setFeedback(null);
    if (idx < acts.length - 1) {
      const next = idx + 1;
      setIdx(next);
      setResp(initRespuesta(acts[next]));
      return;
    }
    // Terminó: fija la duración y re-consulta la ruta por el desbloqueo.
    setDuracion(Math.round((Date.now() - inicio) / 1000));
    try {
      const mi = await obtenerMiLibro();
      const ruta = await obtenerRuta(mi.libro_id);
      const leccion = ruta.lecciones.find((l) => l.id === leccionId);
      if (leccion?.estado === "completada") {
        const siguiente = ruta.lecciones.find((l) => l.orden === leccion.orden + 1);
        if (siguiente && siguiente.estado === "disponible") setDesbloqueo(true);
      }
    } catch {
      /* el resumen se muestra igual */
    }
    setFase("resultado");
  }

  function abandonar() {
    if (window.confirm("¿Seguro que quieres salir? Perderás el avance de esta práctica.")) {
      router.push("/ruta");
    }
  }

  // ---------- Render ----------

  if (fase === "cargando") {
    return (
      <Overlay>
        <div className="flex flex-1 flex-col items-center justify-center gap-5 text-center">
          <div className="animate-floaty h-[110px] w-[110px] overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange">
            <Mascota size={110} />
          </div>
          <div className="text-2xl font-black text-white">🐯 Preparando tu práctica…</div>
          <div className="text-sm font-bold text-white/60">Generando ejercicios desde tu libro</div>
        </div>
      </Overlay>
    );
  }

  if (fase === "error") {
    return (
      <Overlay>
        <div className="flex flex-1 flex-col items-center justify-center gap-5 text-center">
          <div className="text-2xl font-black text-white">No se pudo preparar la práctica 😕</div>
          <div className="max-w-md text-sm font-bold text-white/60">
            No se generaron ejercicios para este tema. Intenta de nuevo.
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => {
                setFase("cargando");
                setIntento((n) => n + 1);
              }}
              className="btn-relief rounded-2xl bg-brand-orange px-7 py-3.5 text-base font-black text-white"
            >
              Reintentar
            </button>
            <button
              onClick={() => router.push("/ruta")}
              className="rounded-2xl border-2 border-white/20 px-7 py-3.5 text-base font-extrabold text-white"
            >
              Volver
            </button>
          </div>
        </div>
      </Overlay>
    );
  }

  if (fase === "resultado") {
    const total = resultados.length;
    const aciertos = resultados.filter((r) => r.puntaje >= 70).length;
    const promedio = total ? Math.round(resultados.reduce((s, r) => s + r.puntaje, 0) / total) : 0;
    const perfecta = total > 0 && resultados.every((r) => r.puntaje === 100);
    const tiempo = `${Math.floor(duracion / 60)}:${String(duracion % 60).padStart(2, "0")}`;
    return (
      <Overlay>
        {/* confetti */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          {Array.from({ length: 16 }).map((_, i) => (
            <span
              key={i}
              className="animate-confetti absolute text-2xl"
              style={{
                left: `${(i * 6.5 + 4) % 100}%`,
                animationDuration: `${2.5 + (i % 4) * 0.6}s`,
                animationDelay: `${(i % 5) * 0.25}s`,
              }}
            >
              {["⭐", "🎉", "✨", "🏆"][i % 4]}
            </span>
          ))}
        </div>

        <div className="animate-pop-in relative z-10 flex flex-1 flex-col items-center justify-center gap-4 text-center">
          <div className="h-[130px] w-[130px] overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange">
            <Mascota size={130} />
          </div>
          <div className="text-[34px] font-black text-white">
            {perfecta ? "¡Lección perfecta! 🌟" : "¡Práctica completada! 🎉"}
          </div>

          <div className="mt-2 flex gap-4">
            {[
              { v: `${aciertos}/${total}`, l: "correctas", c: "#22C55E" },
              { v: `${promedio}`, l: "promedio", c: "#F97316" },
              { v: tiempo, l: "tiempo", c: "#2563EB" },
            ].map((s) => (
              <div key={s.l} className="rounded-2xl bg-white/10 px-7 py-4 backdrop-blur-sm">
                <div className="text-[28px] font-black" style={{ color: s.c }}>
                  {s.v}
                </div>
                <div className="text-[11px] font-extrabold text-white/60">{s.l}</div>
              </div>
            ))}
          </div>

          {desbloqueo && (
            <div className="mt-3 rounded-full bg-brand-green/20 px-6 py-3 text-base font-black text-brand-green">
              🎉 ¡Desbloqueaste la siguiente lección!
            </div>
          )}

          <button
            onClick={() => router.push("/ruta")}
            className="btn-relief mt-6 rounded-2xl bg-brand-orange px-10 py-4 text-lg font-black text-white"
          >
            Volver a Mi Ruta
          </button>
        </div>
      </Overlay>
    );
  }

  // fase === "ejercicio"
  const pasoActual = idx + 1;
  return (
    <Overlay>
      {/* header: X + barra de progreso con bolitas */}
      <div className="mb-8 flex items-center gap-4">
        <button
          onClick={abandonar}
          className="grid h-10 w-10 flex-none place-items-center rounded-full bg-white/10 text-xl font-black text-white/80 hover:bg-white/20"
          aria-label="Salir"
        >
          ✕
        </button>
        <div className="flex flex-1 items-center gap-2">
          {acts.map((_, i) => (
            <div
              key={i}
              className="h-2.5 flex-1 rounded-full transition-colors"
              style={{ background: i <= idx ? "#F97316" : "rgba(255,255,255,.15)" }}
            />
          ))}
        </div>
        <div className="flex-none text-sm font-extrabold text-white/70">
          {pasoActual}/{acts.length}
        </div>
      </div>

      <div className="animate-pop-in mx-auto flex w-full max-w-[640px] flex-1 flex-col">
        <Ejercicio act={act} resp={resp} setResp={setResp} disabled={!!feedback} />
      </div>

      {/* footer: enviar o feedback */}
      {feedback ? (
        <FeedbackPanel act={act} feedback={feedback} onContinuar={continuar} />
      ) : (
        <div className="mx-auto w-full max-w-[640px] pt-6">
          <button
            onClick={enviar}
            disabled={!respuestaLista() || enviando}
            className="btn-relief w-full rounded-2xl bg-brand-orange py-4 text-lg font-black text-white disabled:opacity-40"
          >
            {enviando ? "Revisando…" : "Comprobar"}
          </button>
        </div>
      )}
    </Overlay>
  );
}

/* ---------------- Overlay fullscreen (cubre el sidebar) ---------------- */
function Overlay({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-[#1E2B4D] px-6 py-7 md:px-10">
      {children}
    </div>
  );
}

/* ---------------- Render del ejercicio según el tipo ---------------- */
function Ejercicio({
  act,
  resp,
  setResp,
  disabled,
}: {
  act: ActividadResponse;
  resp: Respuesta;
  setResp: (r: Respuesta) => void;
  disabled: boolean;
}) {
  const c = act.contenido as Record<string, unknown>;
  const str = (k: string) => String(c[k] ?? "");
  const set = (patch: Partial<Respuesta>) => setResp({ ...resp, ...patch });

  function mover(i: number, dir: -1 | 1) {
    const next = resp.orden.slice();
    const j = i + dir;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    set({ orden: next });
  }

  const pregunta =
    act.tipo === "verdadero_falso"
      ? str("afirmacion")
      : act.tipo === "completar"
        ? str("oracion")
        : act.tipo === "ordenar"
          ? str("instruccion")
          : str("pregunta");

  return (
    <div className="flex flex-1 flex-col">
      <div className="mb-1 text-xs font-extrabold uppercase tracking-wider text-brand-orange">
        {act.tipo.replace("_", " ")}
      </div>
      <div className="mb-7 text-[24px] font-black leading-snug text-white">{pregunta}</div>

      {act.tipo === "opcion_multiple" && (
        <div className="flex flex-col gap-3">
          {((c.opciones as string[]) ?? []).map((op) => {
            const on = resp.seleccion === op;
            return (
              <button
                key={op}
                disabled={disabled}
                onClick={() => set({ seleccion: op })}
                className="rounded-2xl border-2 px-5 py-4 text-left text-base font-bold transition-colors"
                style={{
                  borderColor: on ? "#F97316" : "rgba(255,255,255,.18)",
                  background: on ? "rgba(249,115,22,.18)" : "rgba(255,255,255,.06)",
                  color: "#fff",
                }}
              >
                {op}
              </button>
            );
          })}
        </div>
      )}

      {act.tipo === "verdadero_falso" && (
        <div className="flex gap-4">
          {[
            { val: "true", label: "Verdadero ✓", color: "#22C55E" },
            { val: "false", label: "Falso ✗", color: "#EF4444" },
          ].map((o) => {
            const on = resp.seleccion === o.val;
            return (
              <button
                key={o.val}
                disabled={disabled}
                onClick={() => set({ seleccion: o.val })}
                className="flex-1 rounded-2xl border-2 py-7 text-lg font-black transition-colors"
                style={{
                  borderColor: on ? o.color : "rgba(255,255,255,.18)",
                  background: on ? `${o.color}28` : "rgba(255,255,255,.06)",
                  color: "#fff",
                }}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      )}

      {act.tipo === "completar" && (
        <div>
          <input
            disabled={disabled}
            value={resp.seleccion}
            onChange={(e) => set({ seleccion: e.target.value })}
            placeholder="Escribe la palabra que falta…"
            className="w-full rounded-2xl border-2 border-white/20 bg-white/10 px-5 py-4 text-base font-semibold text-white outline-none placeholder:text-white/40 focus:border-brand-orange"
          />
          {str("pista") && (
            <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-[13px] font-extrabold text-white/80">
              💡 Pista: {str("pista")}
            </div>
          )}
        </div>
      )}

      {act.tipo === "ordenar" && (
        <div className="flex flex-col gap-2.5">
          {resp.orden.map((el, i) => (
            <div
              key={el}
              className="flex items-center gap-3 rounded-2xl border-2 border-white/15 bg-white/[0.06] px-4 py-3.5"
            >
              <div className="grid h-7 w-7 flex-none place-items-center rounded-full bg-brand-orange text-sm font-black text-white">
                {i + 1}
              </div>
              <div className="flex-1 text-base font-bold text-white">{el}</div>
              <div className="flex flex-none gap-1">
                <button
                  disabled={disabled || i === 0}
                  onClick={() => mover(i, -1)}
                  className="grid h-8 w-8 place-items-center rounded-lg bg-white/10 text-white disabled:opacity-30"
                >
                  ↑
                </button>
                <button
                  disabled={disabled || i === resp.orden.length - 1}
                  onClick={() => mover(i, 1)}
                  className="grid h-8 w-8 place-items-center rounded-lg bg-white/10 text-white disabled:opacity-30"
                >
                  ↓
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {act.tipo === "respuesta_corta" && (
        <textarea
          disabled={disabled}
          value={resp.seleccion}
          onChange={(e) => set({ seleccion: e.target.value })}
          placeholder="Escribe tu respuesta…"
          rows={4}
          className="w-full resize-none rounded-2xl border-2 border-white/20 bg-white/10 px-5 py-4 text-base font-semibold text-white outline-none placeholder:text-white/40 focus:border-brand-orange"
        />
      )}
    </div>
  );
}

/* ---------------- Panel de feedback (bottom sheet) ---------------- */
function FeedbackPanel({
  act,
  feedback,
  onContinuar,
}: {
  act: ActividadResponse;
  feedback: ResultadoResponse;
  onContinuar: () => void;
}) {
  const p = feedback.puntaje;
  const tono =
    p === 100
      ? { bg: "#DCFCE7", border: "#22C55E", color: "#15803D", title: "¡Excelente! 🌟" }
      : p >= 60
        ? { bg: "#FEF9C3", border: "#F59E0B", color: "#B45309", title: "¡Casi! 💪" }
        : { bg: "#FEE2E2", border: "#EF4444", color: "#B91C1C", title: "Incorrecto" };

  const rc = feedback.respuesta_correcta as Record<string, unknown>;
  const correcta =
    act.tipo === "ordenar"
      ? ((rc.orden_correcto as string[]) ?? []).join(" → ")
      : act.tipo === "verdadero_falso"
        ? rc.respuesta_correcta
          ? "Verdadero"
          : "Falso"
        : String(rc.respuesta_correcta ?? "");

  return (
    <div
      className="animate-pop-in fixed inset-x-0 bottom-0 z-[60] border-t-4 px-6 py-6 md:px-10"
      style={{ background: tono.bg, borderColor: tono.border }}
    >
      <div className="mx-auto flex max-w-[640px] items-center gap-4">
        <div className="flex-1">
          <div className="text-xl font-black" style={{ color: tono.color }}>
            {tono.title}
          </div>
          {p < 100 && correcta && (
            <div className="mt-1 text-sm font-extrabold" style={{ color: tono.color }}>
              Respuesta correcta: {correcta}
            </div>
          )}
          <div className="mt-1 text-[13.5px] font-semibold text-[#3f3f46]">
            {feedback.retroalimentacion}
          </div>
        </div>
        <button
          onClick={onContinuar}
          className="btn-relief flex-none rounded-2xl px-8 py-3.5 text-base font-black text-white"
          style={{ background: tono.border, ["--btn-relief-color" as string]: tono.color }}
        >
          Continuar
        </button>
      </div>
    </div>
  );
}
