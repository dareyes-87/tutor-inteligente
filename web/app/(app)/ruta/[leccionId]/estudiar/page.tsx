"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  obtenerMicroLeccion,
  preguntar,
  type MicroLeccion,
  type TarjetaEducativa,
} from "@/lib/api";
import { ASIGNATURAS } from "@/lib/constants";
import { Mascota } from "@/components/mascota";

const ASIGNATURA_ID = ASIGNATURAS[0].id;

interface MiniMsg {
  rol: "usuario" | "asistente";
  contenido: string;
}

export default function EstudiarPage() {
  const router = useRouter();
  const params = useParams<{ leccionId: string }>();
  const leccionId = Number(params.leccionId);

  const [micro, setMicro] = useState<MicroLeccion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(false);

  // Navegación de tarjetas
  const [idx, setIdx] = useState(0);
  // Fase de la tarjeta de concepto: false = explicación, true = pregunta revelada
  const [mostrarPregunta, setMostrarPregunta] = useState(false);
  const [seleccion, setSeleccion] = useState<string | null>(null);

  // Mini-chat modal (recurso secundario)
  const [chatAbierto, setChatAbierto] = useState(false);

  useEffect(() => {
    let activo = true;
    (async () => {
      try {
        const m = await obtenerMicroLeccion(leccionId);
        if (!activo) return;
        setMicro(m);
        setError(false);
      } catch (err) {
        if (!activo) return;
        setError(true);
        toast.error(err instanceof Error ? err.message : "No se pudo preparar tu lección");
      } finally {
        if (activo) setCargando(false);
      }
    })();
    return () => {
      activo = false;
    };
  }, [leccionId]);

  // Al cambiar de tarjeta, reinicia el estado de la pregunta.
  useEffect(() => {
    setMostrarPregunta(false);
    setSeleccion(null);
  }, [idx]);

  const tarjetas = micro?.tarjetas ?? [];
  const total = tarjetas.length;
  const tarjeta = tarjetas[idx] as TarjetaEducativa | undefined;
  const esUltima = idx >= total - 1;

  function avanzar() {
    if (esUltima) {
      router.push(`/ruta/${leccionId}/practicar`);
      return;
    }
    setIdx((i) => i + 1);
  }

  // ----------------------- Estados de carga / error -----------------------

  if (cargando) {
    return (
      <div className="fixed inset-0 z-50 grid place-items-center bg-navy px-6">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="h-20 w-20 overflow-hidden rounded-full bg-navy ring-4 ring-brand-orange">
            <Mascota size={80} />
          </div>
          <div className="text-lg font-black text-white">🐯 Preparando tu lección…</div>
          <div className="h-2 w-40 overflow-hidden rounded-full bg-white/15">
            <div className="h-full w-1/2 animate-pulse rounded-full bg-brand-orange" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !micro || total === 0) {
    return (
      <div className="fixed inset-0 z-50 grid place-items-center bg-navy px-6">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="text-5xl">😕</div>
          <div className="max-w-xs text-base font-bold text-white">
            No pudimos preparar esta lección. Intenta de nuevo en un momento.
          </div>
          <button
            onClick={() => router.push("/ruta")}
            className="btn-relief rounded-2xl bg-brand-blue px-6 py-3 font-black text-white"
            style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
          >
            Volver a la ruta
          </button>
        </div>
      </div>
    );
  }

  // ----------------------- Render principal -----------------------

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-navy">
      {/* Header con progreso */}
      <header className="flex items-center gap-3 px-5 py-4">
        <button
          onClick={() => router.push("/ruta")}
          className="grid h-9 w-9 flex-none place-items-center rounded-full bg-white/10 text-lg font-black text-white/80 hover:bg-white/20"
          aria-label="Cerrar"
        >
          ✕
        </button>
        <div className="flex-1">
          <div className="mb-1.5 truncate text-[13px] font-black text-white">
            📖 {micro.titulo}
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-white/12">
            <div
              className="h-full rounded-full bg-brand-green transition-all duration-300"
              style={{ width: `${((idx + 1) / total) * 100}%` }}
            />
          </div>
        </div>
        <div className="flex-none text-[12px] font-extrabold text-white/70">
          {idx + 1}/{total}
        </div>
      </header>

      {/* Tarjeta */}
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-5 py-4">
        <div
          key={idx}
          className="animate-[fadeSlide_.35s_ease] w-full max-w-xl rounded-[26px] border border-border bg-cream p-7 shadow-[0_18px_50px_rgba(0,0,0,.35)]"
        >
          <Tarjeta
            tarjeta={tarjeta!}
            esUltima={esUltima}
            mostrarPregunta={mostrarPregunta}
            seleccion={seleccion}
            onMostrarPregunta={() => setMostrarPregunta(true)}
            onSeleccionar={(op) => setSeleccion(op)}
            onAvanzar={avanzar}
            onPreguntarTutor={() => setChatAbierto(true)}
          />
        </div>
      </div>

      {chatAbierto && (
        <MiniChat
          contexto={tarjeta?.titulo_concepto ?? micro.titulo}
          onCerrar={() => setChatAbierto(false)}
        />
      )}

      <style jsx global>{`
        @keyframes fadeSlide {
          from {
            opacity: 0;
            transform: translateY(14px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}

// ----------------------- Tarjeta -----------------------

function Tarjeta({
  tarjeta,
  esUltima,
  mostrarPregunta,
  seleccion,
  onMostrarPregunta,
  onSeleccionar,
  onAvanzar,
  onPreguntarTutor,
}: {
  tarjeta: TarjetaEducativa;
  esUltima: boolean;
  mostrarPregunta: boolean;
  seleccion: string | null;
  onMostrarPregunta: () => void;
  onSeleccionar: (op: string) => void;
  onAvanzar: () => void;
  onPreguntarTutor: () => void;
}) {
  const esConcepto = tarjeta.tipo === "concepto";
  const tienePregunta = esConcepto && tarjeta.pregunta != null;
  const respondida = seleccion != null;
  const correcta = respondida && seleccion === tarjeta.pregunta?.respuesta_correcta;

  return (
    <div className="flex flex-col items-center text-center">
      <div className="mb-3 text-[56px] leading-none">{tarjeta.emoji}</div>

      {tarjeta.tipo === "introduccion" && (
        <h2 className="mb-3 text-xl font-black text-navy">¡Empecemos!</h2>
      )}
      {esConcepto && tarjeta.titulo_concepto && (
        <h2 className="mb-3 text-xl font-black text-navy">{tarjeta.titulo_concepto}</h2>
      )}
      {tarjeta.tipo === "resumen" && (
        <h2 className="mb-3 text-xl font-black text-navy">¡Lo lograste!</h2>
      )}

      <p className="text-[16px] font-semibold leading-relaxed text-[#3B4252]">
        {tarjeta.contenido}
      </p>

      {tarjeta.dato_curioso && (
        <div className="mt-4 w-full rounded-2xl bg-accent/60 px-4 py-3 text-left text-[14px] font-bold text-accent-foreground">
          💡 {tarjeta.dato_curioso}
        </div>
      )}

      {/* Pregunta de comprensión (concepto) */}
      {tienePregunta && mostrarPregunta && tarjeta.pregunta && (
        <div className="mt-6 w-full text-left">
          <div className="mb-3 text-[15px] font-black text-navy">{tarjeta.pregunta.texto}</div>
          <div className={tarjeta.pregunta.opciones.length > 2 ? "grid grid-cols-1 gap-2.5 sm:grid-cols-2" : "flex flex-col gap-2.5"}>
            {tarjeta.pregunta.opciones.map((op) => {
              const esEsta = seleccion === op;
              const esCorrecta = op === tarjeta.pregunta!.respuesta_correcta;
              let cls = "border-border bg-white text-navy hover:border-brand-blue";
              if (respondida) {
                if (esCorrecta) cls = "border-brand-green bg-brand-green/15 text-brand-green";
                else if (esEsta) cls = "border-red-400 bg-red-50 text-red-600";
                else cls = "border-border bg-white text-muted-foreground opacity-70";
              }
              return (
                <button
                  key={op}
                  disabled={respondida}
                  onClick={() => onSeleccionar(op)}
                  className={`rounded-2xl border-2 px-4 py-3.5 text-[15px] font-bold transition-colors ${cls}`}
                >
                  {op}
                </button>
              );
            })}
          </div>

          {respondida && (
            <div
              className={`mt-3 rounded-2xl px-4 py-3 text-[14px] font-bold ${
                correcta ? "bg-brand-green/15 text-brand-green" : "bg-red-50 text-red-600"
              }`}
            >
              {correcta ? "✅ ¡Correcto! " : "❌ Casi… "}
              {tarjeta.pregunta.explicacion}
            </div>
          )}
        </div>
      )}

      {/* Botón "Preguntar al tutor" (solo conceptos) */}
      {esConcepto && (
        <button
          onClick={onPreguntarTutor}
          className="mt-5 text-[13px] font-extrabold text-brand-blue hover:underline"
        >
          💬 Preguntar al tutor
        </button>
      )}

      {/* Acción principal */}
      <div className="mt-6 w-full">
        {tarjeta.tipo === "introduccion" && (
          <BotonPrincipal label="Empecemos →" color="blue" onClick={onAvanzar} />
        )}
        {esConcepto && !tienePregunta && (
          <BotonPrincipal label="Continuar →" color="blue" onClick={onAvanzar} />
        )}
        {esConcepto && tienePregunta && !mostrarPregunta && (
          <BotonPrincipal label="Continuar →" color="blue" onClick={onMostrarPregunta} />
        )}
        {esConcepto && tienePregunta && mostrarPregunta && (
          <BotonPrincipal
            label="Siguiente →"
            color="blue"
            disabled={!respondida}
            onClick={onAvanzar}
          />
        )}
        {tarjeta.tipo === "resumen" && (
          <BotonPrincipal label="Ir a Practicar 🎯" color="green" onClick={onAvanzar} />
        )}
      </div>
    </div>
  );
}

function BotonPrincipal({
  label,
  color,
  disabled,
  onClick,
}: {
  label: string;
  color: "blue" | "green";
  disabled?: boolean;
  onClick: () => void;
}) {
  const bg = color === "green" ? "bg-brand-green" : "bg-brand-blue";
  const relief = color === "green" ? "#15803D" : "var(--brand-blue-dark)";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`btn-relief w-full rounded-[16px] ${bg} py-3.5 text-center text-base font-black text-white disabled:opacity-50`}
      style={{ ["--btn-relief-color" as string]: relief }}
    >
      {label}
    </button>
  );
}

// ----------------------- Mini-chat modal -----------------------

function MiniChat({ contexto, onCerrar }: { contexto: string; onCerrar: () => void }) {
  const [mensajes, setMensajes] = useState<MiniMsg[]>([]);
  const [conversacionId, setConversacionId] = useState<number | null>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [mensajes, enviando]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    const t = texto.trim();
    if (!t || enviando) return;
    setMensajes((prev) => [...prev, { rol: "usuario", contenido: t }]);
    setTexto("");
    setEnviando(true);
    try {
      const res = await preguntar(t, ASIGNATURA_ID, conversacionId);
      setConversacionId(res.conversacion_id);
      setMensajes((prev) => [...prev, { rol: "asistente", contenido: res.respuesta }]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo enviar tu pregunta");
      setMensajes((prev) => prev.slice(0, -1));
      setTexto(t);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 sm:items-center">
      <div className="flex h-[80vh] w-full max-w-lg flex-col rounded-t-[24px] bg-cream sm:h-[70vh] sm:rounded-[24px]">
        <header className="flex items-center gap-3 rounded-t-[24px] bg-navy px-5 py-4">
          <div className="h-9 w-9 flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
            <Mascota size={36} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-black text-white">💬 Tutor Tigre</div>
            <div className="truncate text-[11px] font-bold text-[#94A3B8]">Sobre: {contexto}</div>
          </div>
          <button
            onClick={onCerrar}
            className="grid h-8 w-8 flex-none place-items-center rounded-full bg-white/10 font-black text-white/80 hover:bg-white/20"
            aria-label="Cerrar chat"
          >
            ✕
          </button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
          {mensajes.length === 0 && !enviando && (
            <div className="mt-6 text-center text-[14px] font-semibold text-muted-foreground">
              Escríbeme una duda sobre <b>{contexto}</b> 🐯
            </div>
          )}
          <div className="flex flex-col gap-3">
            {mensajes.map((m, i) => {
              const tutor = m.rol === "asistente";
              return (
                <div key={i} className={`flex ${tutor ? "justify-start" : "justify-end"}`}>
                  <div
                    className={`max-w-[80%] whitespace-pre-wrap px-4 py-2.5 text-[14.5px] font-semibold leading-relaxed ${
                      tutor
                        ? "rounded-[6px_16px_16px_16px] border border-border bg-white text-[#1F2433]"
                        : "rounded-[16px_16px_6px_16px] bg-[#E0ECFF] text-[#1E3A8A]"
                    }`}
                  >
                    {m.contenido}
                  </div>
                </div>
              );
            })}
            {enviando && (
              <div className="flex justify-start">
                <div className="rounded-[6px_16px_16px_16px] border border-border bg-white px-4 py-2.5 text-[14.5px] font-semibold text-muted-foreground">
                  El tutor está escribiendo…
                </div>
              </div>
            )}
          </div>
        </div>

        <form onSubmit={enviar} className="flex items-center gap-2.5 border-t border-border bg-white px-4 py-3">
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Escribe tu duda…"
            disabled={enviando}
            autoComplete="off"
            className="flex-1 rounded-[16px] border-2 border-border bg-muted/50 px-4 py-3 text-[15px] font-semibold text-navy outline-none placeholder:text-[#B6BBC6] focus:border-brand-blue"
          />
          <button
            type="submit"
            disabled={enviando || !texto.trim()}
            className="btn-relief grid h-[48px] w-[48px] flex-none place-items-center rounded-2xl bg-brand-blue text-[20px] text-white disabled:opacity-50"
            style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
            aria-label="Enviar"
          >
            ➤
          </button>
        </form>
      </div>
    </div>
  );
}
