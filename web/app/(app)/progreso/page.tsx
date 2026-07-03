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

  // Dominio = promedio ponderado del puntaje por nº de actividades (temas con más
  // práctica pesan más). Se reutiliza para el total y para cada asignatura.
  const dominioDe = (temas: PerfilTema[]) => {
    const tot = temas.reduce((s, p) => s + p.total_actividades, 0);
    return tot === 0
      ? 0
      : Math.round(
          temas.reduce((s, p) => s + p.puntaje_promedio * p.total_actividades, 0) / tot,
        );
  };
  const avanceTotal = dominioDe(items);

  // Agrupar temas por asignatura, preservando el orden de aparición.
  const grupos: { asignatura: string; temas: PerfilTema[] }[] = [];
  for (const p of items) {
    let g = grupos.find((x) => x.asignatura === p.asignatura);
    if (!g) {
      g = { asignatura: p.asignatura, temas: [] };
      grupos.push(g);
    }
    g.temas.push(p);
  }
  // Con una sola asignatura no se agrupa (evita ruido visual); con varias, cada
  // asignatura tiene su encabezado y su propio % de DOMINIO.
  const multiples = grupos.length > 1;

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
            <div className="text-[11px] font-extrabold text-muted-foreground">
              {multiples ? "DOMINIO GENERAL" : "DOMINIO"}
            </div>
          </div>
        </div>
      </div>

      {multiples ? (
        /* Desglose por asignatura */
        <div className="flex flex-col gap-7">
          {grupos.map((g) => (
            <div key={g.asignatura}>
              <div className="mb-3 flex items-center justify-between gap-3 px-1">
                <div className="flex items-center gap-2.5">
                  <span className="text-[17px] font-black text-navy">{g.asignatura}</span>
                  <span className="rounded-full bg-muted px-2.5 py-0.5 text-[12px] font-extrabold text-muted-foreground">
                    {g.temas.length} {g.temas.length === 1 ? "tema" : "temas"}
                  </span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-black text-brand-orange">{dominioDe(g.temas)}%</span>
                  <span className="text-[11px] font-extrabold text-muted-foreground">DOMINIO</span>
                </div>
              </div>
              <div className="flex flex-col gap-3.5">
                {g.temas.map((p, i) => (
                  <TemaRow
                    key={`${p.asignatura}·${p.tema}`}
                    p={p}
                    numero={i + 1}
                    mostrarAsignatura={false}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Una sola asignatura: lista plana */
        <div className="flex flex-col gap-3.5">
          {items.map((p, i) => (
            <TemaRow
              key={`${p.asignatura}·${p.tema}`}
              p={p}
              numero={i + 1}
              mostrarAsignatura
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Fila de un tema en Mi Progreso. `mostrarAsignatura` se apaga cuando ya hay un
 * encabezado de asignatura (desglose), para no repetir el badge. */
function TemaRow({
  p,
  numero,
  mostrarAsignatura,
}: {
  p: PerfilTema;
  numero: number;
  mostrarAsignatura: boolean;
}) {
  const nv = nivelMeta(p.nivel);
  const pct = Math.round(p.puntaje_promedio);
  return (
    <div className="flex items-center gap-3 rounded-[20px] border border-border bg-white px-4 py-4 shadow-[0_5px_16px_rgba(30,43,77,.05)] sm:gap-[22px] sm:px-6 sm:py-5">
      <div
        className="grid h-[46px] w-[46px] flex-none place-items-center rounded-[14px] text-lg font-black"
        style={{ background: nv.chipBg, color: nv.chipColor }}
      >
        {numero}
      </div>
      <div className="min-w-0 flex-1">
        {/* Nombre del tema arriba (prominente), asignatura debajo como metadata
            secundaria: evita el truncado "La ..." y que el badge tape el nombre. */}
        <div className="mb-1 flex items-start justify-between gap-3">
          <span className="text-[16.5px] font-extrabold leading-tight text-navy">{p.tema}</span>
          <span className="flex-none whitespace-nowrap text-[12.5px] font-extrabold text-muted-foreground">
            {p.total_actividades} {p.total_actividades === 1 ? "actividad" : "actividades"}
          </span>
        </div>
        {mostrarAsignatura && (
          <div className="mb-2.5">
            <span className="inline-block rounded-full bg-muted px-2 py-0.5 text-[11px] font-extrabold text-muted-foreground">
              {p.asignatura}
            </span>
          </div>
        )}
        <div className={`${mostrarAsignatura ? "" : "mt-2 "}h-3 overflow-hidden rounded-full bg-[#ECE7DE]`}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: nv.bar }} />
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
}
