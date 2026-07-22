"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";

import { preguntar, ApiError, type ReferenciaFragment } from "@/lib/api";
import { ASIGNATURAS } from "@/lib/constants";
import { Mascota } from "@/components/mascota";

interface ChatMessage {
  rol: "usuario" | "asistente";
  contenido: string;
  referencias?: ReferenciaFragment[];
}

// Estilos del markdown del tutor. Tailwind resetea listas (sin viñetas/números)
// y márgenes, así que hay que declararlos aquí para que se vean dentro de la
// burbuja. `last:mb-0` evita un margen extra al final del mensaje.
const mdComponents = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-2 last:mb-0">{children}</p>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-black text-navy">{children}</strong>
  ),
  em: ({ children }: { children?: React.ReactNode }) => (
    <em className="italic">{children}</em>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="leading-relaxed">{children}</li>
  ),
};

function Referencias({ refs }: { refs: ReferenciaFragment[] }) {
  const conPagina = refs.filter((r) => r.page_num != null);
  if (conPagina.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {conPagina.map((r, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1.5 rounded-full bg-accent px-[13px] py-[7px] text-[12.5px] font-extrabold text-accent-foreground"
        >
          📖 Página {r.page_num}
          {r.libro_id != null ? ` · libro ${r.libro_id}` : ""}
        </span>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const [asignaturaId, setAsignaturaId] = useState<number>(ASIGNATURAS[0].id);
  const [conversacionId, setConversacionId] = useState<number | null>(null);
  const [mensajes, setMensajes] = useState<ChatMessage[]>([]);
  const [pregunta, setPregunta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [tardando, setTardando] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const tardandoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Autoscroll al último mensaje.
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
    setTardando(false);
    // Si la respuesta tarda más de lo normal (p. ej. el modelo fine-tuned
    // "despertando" tras estar inactivo), se avisa en vez de parecer colgado.
    tardandoTimer.current = setTimeout(() => setTardando(true), 10_000);

    try {
      const res = await preguntar(texto, asignaturaId, conversacionId);
      setConversacionId(res.conversacion_id);
      setMensajes((prev) => [
        ...prev,
        { rol: "asistente", contenido: res.respuesta, referencias: res.referencias },
      ]);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "No se pudo conectar con el servidor";
      toast.error(msg);
      // Devolver la pregunta al input para reintentar.
      setMensajes((prev) => prev.slice(0, -1));
      setPregunta(texto);
    } finally {
      if (tardandoTimer.current) clearTimeout(tardandoTimer.current);
      setEnviando(false);
      setTardando(false);
    }
  }

  function nuevaConversacion() {
    setConversacionId(null);
    setMensajes([]);
  }

  const asignatura = ASIGNATURAS.find((a) => a.id === asignaturaId);

  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col md:h-screen">
      {/* Cabecera */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-white px-4 py-4 sm:px-8 sm:py-[22px]">
        <div className="flex items-center gap-[13px]">
          <div className="h-14 w-14 overflow-hidden rounded-full bg-navy ring-[3px] ring-brand-orange">
            <Mascota size={56} />
          </div>
          <div>
            <div className="text-lg font-black text-navy">Tutor Tigre</div>
            <div className="flex items-center gap-1.5 text-[12.5px] font-extrabold text-brand-green">
              <span className="inline-block h-2 w-2 rounded-full bg-brand-green" />
              En línea
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5 rounded-[14px] border-2 border-border bg-muted/50 px-4 py-[11px]">
            <span>🌱</span>
            <select
              value={asignaturaId}
              onChange={(e) => setAsignaturaId(Number(e.target.value))}
              className="cursor-pointer bg-transparent text-sm font-extrabold text-navy outline-none"
            >
              {ASIGNATURAS.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.nombre}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={nuevaConversacion}
            className="rounded-[14px] border-2 border-border bg-white px-4 py-[11px] text-sm font-extrabold text-[#5A6170] hover:bg-muted/60"
          >
            Nueva
          </button>
        </div>
      </header>

      {/* Mensajes */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-5 sm:px-8 sm:py-7"
        style={{
          backgroundImage: "radial-gradient(#F3E9DA 1.4px,transparent 1.4px)",
          backgroundSize: "24px 24px",
        }}
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-[18px]">
          {/* Bienvenida cuando no hay mensajes aún */}
          {mensajes.length === 0 && (
            <div className="flex items-end gap-[11px]">
              <div className="h-12 w-12 flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
                <Mascota size={48} />
              </div>
              <div className="max-w-[85%] rounded-[6px_18px_18px_18px] border border-border bg-white px-[18px] py-3.5 text-[15.5px] font-semibold leading-relaxed text-[#1F2433] shadow-[0_3px_10px_rgba(30,43,77,.06)] sm:max-w-[60%]">
                ¡Hola! 🐯 Soy tu tutor. Pregúntame lo que quieras sobre{" "}
                {asignatura?.nombre ?? "tu libro"} y te responderé con la página del libro.
              </div>
            </div>
          )}

          {mensajes.map((m, i) => {
            const tutor = m.rol === "asistente";
            return (
              <div
                key={i}
                className={`flex items-end gap-[11px] ${tutor ? "justify-start" : "justify-end"}`}
              >
                {tutor && (
                  <div className="h-12 w-12 flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
                    <Mascota size={48} />
                  </div>
                )}
                <div className="max-w-[85%] sm:max-w-[60%]">
                  <div
                    className={`px-[18px] py-3.5 text-[15.5px] font-semibold leading-relaxed shadow-[0_3px_10px_rgba(30,43,77,.06)] ${
                      tutor
                        ? "rounded-[6px_18px_18px_18px] border border-border bg-white text-[#1F2433]"
                        : "whitespace-pre-wrap rounded-[18px_18px_6px_18px] bg-[#E0ECFF] text-[#1E3A8A]"
                    }`}
                  >
                    {tutor ? (
                      <ReactMarkdown components={mdComponents}>
                        {m.contenido}
                      </ReactMarkdown>
                    ) : (
                      m.contenido
                    )}
                  </div>
                  {tutor && m.referencias && <Referencias refs={m.referencias} />}
                </div>
              </div>
            );
          })}

          {enviando && (
            <div className="flex items-end gap-[11px] justify-start">
              <div className="h-12 w-12 flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
                <Mascota size={48} />
              </div>
              <div className="rounded-[6px_18px_18px_18px] border border-border bg-white px-[18px] py-3.5 text-[15.5px] font-semibold text-muted-foreground shadow-[0_3px_10px_rgba(30,43,77,.06)]">
                {tardando ? "El tutor está despertando, espera un momento…" : "El tutor está pensando…"}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <form
        onSubmit={enviar}
        className="flex items-center gap-3 border-t border-border bg-white px-4 py-3 sm:px-8 sm:py-[18px]"
      >
        <input
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          placeholder="Escribe tu pregunta al tutor…"
          disabled={enviando}
          autoComplete="off"
          className="flex-1 rounded-[18px] border-2 border-border bg-muted/50 px-5 py-[15px] text-[15px] font-semibold text-navy outline-none placeholder:text-[#B6BBC6] focus:border-brand-blue"
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
