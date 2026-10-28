"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import {
  ApiError,
  obtenerDiagnostico,
  obtenerLibros,
  type DiagnosticoDocente,
  type LibroDocente,
  type NivelDiagnostico,
} from "@/lib/api";

/** Colores por nivel (verde / ámbar / rojo como "Mi progreso"), con texto oscuro
 * del mismo tono para que el número de la celda tenga contraste suficiente. */
const NIVEL: Record<NivelDiagnostico, { label: string; bg: string; color: string }> = {
  domina: { label: "Domina (≥ 80)", bg: "#4ADE80", color: "#14532D" },
  en_proceso: { label: "En proceso (50–79)", bg: "#FBBF24", color: "#78350F" },
  refuerzo: { label: "Necesita refuerzo (< 50)", bg: "#F87171", color: "#7F1D1D" },
  sin_datos: { label: "Sin datos", bg: "#EEF1F6", color: "#9AA0AD" },
};

export default function DiagnosticoPage() {
  const [libros, setLibros] = useState<LibroDocente[]>([]);
  const [asignatura, setAsignatura] = useState<string>("");
  const [libroId, setLibroId] = useState<number | null>(null);
  const [diag, setDiag] = useState<DiagnosticoDocente | null>(null);
  const [cargando, setCargando] = useState(true);

  // Libros del grado (solo los indexados tienen lecciones que diagnosticar).
  useEffect(() => {
    let activo = true;
    obtenerLibros()
      .then((ls) => {
        if (!activo) return;
        const completos = ls.filter((l) => l.estado === "completado" && l.total_lecciones > 0);
        setLibros(completos);
        if (completos.length > 0) {
          setAsignatura(completos[0].asignatura);
          setLibroId(completos[0].id);
        } else {
          setCargando(false);
        }
      })
      .catch((err) => {
        if (!activo) return;
        toast.error(err instanceof ApiError ? err.message : "No se pudieron cargar los libros");
        setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  useEffect(() => {
    if (libroId == null) return;
    let activo = true;
    obtenerDiagnostico(libroId)
      .then((d) => {
        if (activo) setDiag(d);
      })
      .catch((err) => {
        if (activo) toast.error(err instanceof ApiError ? err.message : "No se pudo cargar el diagnóstico");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [libroId]);

  const asignaturas = useMemo(() => [...new Set(libros.map((l) => l.asignatura))], [libros]);
  const librosDeAsignatura = libros.filter((l) => l.asignatura === asignatura);

  const cambiarAsignatura = (a: string) => {
    setAsignatura(a);
    const primero = libros.find((l) => l.asignatura === a);
    if (primero && primero.id !== libroId) {
      setCargando(true);
      setLibroId(primero.id);
    }
  };
  const cambiarLibro = (id: number) => {
    if (id === libroId) return;
    setCargando(true);
    setLibroId(id);
  };

  const selectCls =
    "rounded-[12px] border border-[#E6E9F0] bg-white px-3.5 py-2.5 text-sm font-bold text-navy shadow-[0_3px_10px_rgba(30,43,77,.04)]";

  return (
    <div className="px-9 py-8">
      <div className="mb-1 text-2xl font-black text-navy">🗺️ Diagnóstico</div>
      <div className="mb-6 text-sm font-bold text-[#7B8194]">
        Comprensión de cada estudiante en cada lección, según sus actividades de práctica
      </div>

      {libros.length > 0 && (
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[11px] font-extrabold uppercase tracking-wide text-muted-foreground">
            Asignatura
            <select className={selectCls} value={asignatura} onChange={(e) => cambiarAsignatura(e.target.value)}>
              {asignaturas.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[11px] font-extrabold uppercase tracking-wide text-muted-foreground">
            Libro
            <select
              className={selectCls}
              value={libroId ?? ""}
              onChange={(e) => cambiarLibro(Number(e.target.value))}
            >
              {librosDeAsignatura.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.titulo}
                </option>
              ))}
            </select>
          </label>
          <Leyenda />
        </div>
      )}

      {cargando ? (
        <div className="py-10 text-center text-sm font-bold text-muted-foreground">Cargando diagnóstico…</div>
      ) : libros.length === 0 ? (
        <Vacio texto="Aún no hay libros indexados con lecciones para tu grado." />
      ) : !diag || diag.estudiantes.length === 0 ? (
        <Vacio texto="No hay estudiantes activos en el grado de este libro." />
      ) : (
        <Matriz diag={diag} />
      )}
    </div>
  );
}

function Leyenda() {
  return (
    <div className="ml-auto flex flex-wrap items-center gap-3 pb-1">
      {(Object.keys(NIVEL) as NivelDiagnostico[]).map((n) => (
        <span key={n} className="flex items-center gap-1.5 text-[12px] font-bold text-[#5B6275]">
          <span className="h-3.5 w-3.5 rounded-[4px]" style={{ background: NIVEL[n].bg }} />
          {NIVEL[n].label}
        </span>
      ))}
    </div>
  );
}

function Vacio({ texto }: { texto: string }) {
  return (
    <div className="rounded-[16px] border border-dashed border-[#D8DEE9] bg-white px-6 py-8 text-center text-sm font-bold text-muted-foreground">
      {texto}
    </div>
  );
}

function Matriz({ diag }: { diag: DiagnosticoDocente }) {
  const conDatos = diag.estudiantes.some((e) => e.celdas.some((c) => c.nivel !== "sin_datos"));
  return (
    <div className="rounded-[18px] border border-[#E6E9F0] bg-white p-4 shadow-[0_5px_16px_rgba(30,43,77,.05)]">
      {!conDatos && (
        <div className="mb-3 text-[13px] font-bold text-muted-foreground">
          Todavía nadie ha practicado lecciones de este libro.
        </div>
      )}
      {/* Scroll horizontal solo dentro de la tarjeta si hay muchas lecciones. */}
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-white px-2 text-left text-[11px] font-extrabold uppercase tracking-wide text-muted-foreground">
                Estudiante
              </th>
              {diag.lecciones.map((l) => (
                <th
                  key={l.id}
                  scope="col"
                  title={`Lección ${l.orden}: ${l.nombre}${l.paginas ? ` (págs. ${l.paginas})` : ""}`}
                  className="w-10 min-w-10 cursor-help text-center text-[11px] font-extrabold text-[#7B8194]"
                >
                  L{l.orden}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {diag.estudiantes.map((e) => (
              <tr key={e.estudiante_id}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 max-w-[190px] truncate whitespace-nowrap bg-white px-2 text-left text-[13px] font-extrabold text-navy"
                >
                  {e.apellido}, {e.nombre}
                </th>
                {e.celdas.map((c, i) => {
                  const nv = NIVEL[c.nivel];
                  const leccion = diag.lecciones[i];
                  const detalle =
                    c.puntaje_promedio == null
                      ? "sin actividades"
                      : `${c.puntaje_promedio} puntos en ${c.total_actividades} ${c.total_actividades === 1 ? "actividad" : "actividades"}`;
                  return (
                    <td key={c.leccion_id} className="p-0">
                      <Link
                        href={`/docente/estudiantes/${e.estudiante_id}`}
                        title={`${e.nombre} ${e.apellido} · Lección ${leccion.orden}: ${leccion.nombre} · ${nv.label} · ${detalle}`}
                        aria-label={`${e.nombre} ${e.apellido}, lección ${leccion.orden}: ${nv.label}, ${detalle}`}
                        className="grid h-10 w-10 place-items-center rounded-[8px] text-[11px] font-black transition-transform hover:scale-110 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand-blue"
                        style={{ background: nv.bg, color: nv.color }}
                      >
                        {c.puntaje_promedio == null ? "·" : Math.round(c.puntaje_promedio)}
                      </Link>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
