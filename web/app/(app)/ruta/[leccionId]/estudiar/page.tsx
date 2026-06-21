"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  obtenerRuta,
  preguntar,
  type LeccionEnRuta,
  type ReferenciaFragment,
} from "@/lib/api";
import { ASIGNATURAS } from "@/lib/constants";
import { Mascota } from "@/components/mascota";

const ASIGNATURA_ID = ASIGNATURAS[0].id;

interface Msg {
  rol: "usuario" | "asistente";
  contenido: string;
  referencias?: ReferenciaFragment[];
}

export default function EstudiarPage() {
  const router = useRouter();
  const params = useParams<{ leccionId: string }>();
  const leccionId = Number(params.leccionId);

  const [leccion, setLeccion] = useState<LeccionEnRuta | null>(null);
  const [mensajes, setMensajes] = useState<Msg[]>([]);
  const [conversacionId, setConversacionId] = useState<number | null>(null);
  const [pregunta, setPregunta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Carga: obtiene la lección y dispara el mensaje de bienvenida del tutor.
  useEffect(() => {
    let activo = true;
    (async () => {
      try {
        const ruta = await obtenerRuta(1);
        const l = ruta.lecciones.find((x) => x.id === leccionId) ?? null;
        if (!activo) return;
        setLeccion(l);
        if (!l) return;
        setEnviando(true);
        const tema = l.tema_clave || l.nombre;
        const intro =
          `Preséntate como tutor y da una introducción breve y amigable sobre el tema: ${tema}. ` +
          `Menciona los puntos principales que vamos a aprender.`;
        const res = await preguntar(intro, ASIGNATURA_ID, null);
        if (!activo) return;
        setConversacionId(res.conversacion_id);
        setMensajes([{ rol: "asistente", contenido: res.respuesta, referencias: res.referencias }]);
      } catch {
        if (activo)
          setMensajes([
            {
              rol: "asistente",
              contenido: "¡Hola! 🐯 Soy tu tutor. Pregúntame lo que quieras sobre esta lección.",
            },
          ]);
      } finally {
        if (activo) setEnviando(false);
      }
    })();
    return () => {
      activo = false;
    };
  }, [leccionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [mensajes, enviando]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    const texto = pregunta.trim();
    if (!texto || enviando) return;
    setMensajes((prev) => [...prev, { rol: "usuario", contenido: texto }]);
    setPregunta("");
    setEnviando(true);
    try {
      const res = await preguntar(texto, ASIGNATURA_ID, conversacionId);
      setConversacionId(res.conversacion_id);
      setMensajes((prev) => [
        ...prev,
        { rol: "asistente", contenido: res.respuesta, referencias: res.referencias },
      ]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo enviar tu pregunta");
      setMensajes((prev) => prev.slice(0, -1));
      setPregunta(texto);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-cream">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-border bg-navy px-6 py-4">
        <button
          onClick={() => router.push("/ruta")}
          className="grid h-9 w-9 flex-none place-items-center rounded-full bg-white/10 text-lg font-black text-white/80 hover:bg-white/20"
          aria-label="Volver"
        >
          ✕
        </button>
        <div className="h-10 w-10 flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
          <Mascota size={40} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[15px] font-black text-white">
            📖 Lección: {leccion?.nombre ?? "…"}
          </div>
          <div className="text-[11.5px] font-bold text-[#94A3B8]">Tutor Tigre · en línea</div>
        </div>
      </header>

      {/* Mensajes */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 py-7"
        style={{
          backgroundImage: "radial-gradient(#F3E9DA 1.4px,transparent 1.4px)",
          backgroundSize: "24px 24px",
        }}
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-[18px]">
          {mensajes.map((m, i) => {
            const tutor = m.rol === "asistente";
            return (
              <div
                key={i}
                className={`flex items-end gap-[11px] ${tutor ? "justify-start" : "justify-end"}`}
              >
                {tutor && (
                  <div className="h-10 w-10 flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
                    <Mascota size={40} />
                  </div>
                )}
                <div className="max-w-[68%]">
                  <div
                    className={`whitespace-pre-wrap px-[18px] py-3.5 text-[15.5px] font-semibold leading-relaxed shadow-[0_3px_10px_rgba(30,43,77,.06)] ${
                      tutor
                        ? "rounded-[6px_18px_18px_18px] border border-border bg-white text-[#1F2433]"
                        : "rounded-[18px_18px_6px_18px] bg-[#E0ECFF] text-[#1E3A8A]"
                    }`}
                  >
                    {m.contenido}
                  </div>
                  {tutor && m.referencias && m.referencias.filter((r) => r.page_num != null).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {m.referencias
                        .filter((r) => r.page_num != null)
                        .map((r, j) => (
                          <span
                            key={j}
                            className="inline-flex items-center gap-1.5 rounded-full bg-accent px-[13px] py-[7px] text-[12.5px] font-extrabold text-accent-foreground"
                          >
                            📖 Página {r.page_num}
                          </span>
                        ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {enviando && (
            <div className="flex items-end gap-[11px] justify-start">
              <div className="h-10 w-10 flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
                <Mascota size={40} />
              </div>
              <div className="rounded-[6px_18px_18px_18px] border border-border bg-white px-[18px] py-3.5 text-[15.5px] font-semibold text-muted-foreground shadow-[0_3px_10px_rgba(30,43,77,.06)]">
                El tutor está escribiendo…
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Ir a practicar */}
      <div className="border-t border-border bg-white px-6 pt-3">
        <button
          onClick={() => router.push(`/ruta/${leccionId}/practicar`)}
          className="btn-relief mx-auto block w-full max-w-3xl rounded-[16px] bg-brand-green py-3 text-center text-base font-black text-white"
          style={{ ["--btn-relief-color" as string]: "#15803D" }}
        >
          Ir a Practicar 🎯
        </button>
      </div>

      {/* Input */}
      <form onSubmit={enviar} className="flex items-center gap-3 bg-white px-6 pb-5 pt-3">
        <input
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          placeholder="Escribe tu pregunta al tutor…"
          disabled={enviando}
          autoComplete="off"
          className="mx-auto flex-1 rounded-[18px] border-2 border-border bg-muted/50 px-5 py-[15px] text-[15px] font-semibold text-navy outline-none placeholder:text-[#B6BBC6] focus:border-brand-blue"
        />
        <button
          type="submit"
          disabled={enviando || !pregunta.trim()}
          className="btn-relief grid h-[54px] w-[54px] flex-none place-items-center rounded-2xl bg-brand-blue text-[22px] text-white disabled:opacity-50"
          style={{ ["--btn-relief-color" as string]: "var(--brand-blue-dark)" }}
          aria-label="Enviar"
        >
          ➤
        </button>
      </form>
    </div>
  );
}
