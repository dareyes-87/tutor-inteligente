"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError, obtenerLibros, type LibroDocente } from "@/lib/api";
import { ESTADO_LIBRO } from "@/lib/docente";
import { UploadModal } from "@/components/teacher/upload-modal";

export default function LibrosPage() {
  const [libros, setLibros] = useState<LibroDocente[]>([]);
  const [cargando, setCargando] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let activo = true;
    obtenerLibros()
      .then((l) => {
        if (activo) setLibros(l);
      })
      .catch((err) => {
        if (activo) toast.error(err instanceof ApiError ? err.message : "No se pudieron cargar los libros");
      })
      .finally(() => {
        if (activo) setCargando(false);
      });
    return () => {
      activo = false;
    };
  }, [refresh]);

  // Auto-poll cada 5s mientras algún libro esté procesándose.
  const hayProcesando = useMemo(
    () => libros.some((l) => l.estado === "procesando" || l.estado === "pendiente"),
    [libros],
  );
  useEffect(() => {
    if (!hayProcesando) return;
    const id = setInterval(() => setRefresh((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, [hayProcesando]);

  return (
    <div className="px-9 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="text-2xl font-black text-navy">📚 Mis libros</div>
          <div className="mt-1 text-sm font-bold text-[#7B8194]">
            Sube los libros de texto que el tutor usará para responder y generar actividades.
          </div>
          {hayProcesando && (
            <div className="mt-2 inline-block rounded-lg bg-[#FEF6E7] px-3 py-1.5 text-xs font-extrabold text-[#D97706]">
              ⏳ Espera a que el libro actual termine de procesarse antes de subir otro.
            </div>
          )}
        </div>
        <button
          onClick={() => setShowUpload(true)}
          disabled={hayProcesando}
          title={
            hayProcesando ? "Espera a que el libro actual termine de procesarse" : undefined
          }
          className="rounded-xl bg-brand-blue px-5 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_#1D4ED8] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none disabled:active:translate-y-0"
        >
          + Subir nuevo libro
        </button>
      </div>

      {cargando ? (
        <div className="py-10 text-center text-sm font-bold text-muted-foreground">Cargando libros…</div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {libros.length === 0 && (
            <div className="col-span-2 rounded-[16px] border border-dashed border-[#D8DEE9] bg-white px-6 py-8 text-center text-sm font-bold text-muted-foreground">
              Aún no hay libros. Sube el primero con “Subir nuevo libro”.
            </div>
          )}
          {libros.map((l) => {
            const est = ESTADO_LIBRO[l.estado] ?? ESTADO_LIBRO.pendiente;
            return (
              <div
                key={l.id}
                className="flex items-center gap-4 rounded-[16px] border border-[#E6E9F0] bg-white px-5 py-4 shadow-[0_5px_16px_rgba(30,43,77,.05)]"
              >
                <div className="grid h-12 w-10 flex-none place-items-center rounded-md bg-navy text-lg">
                  📕
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[15px] font-extrabold text-navy">{l.titulo}</div>
                  <div className="text-xs font-bold text-muted-foreground">
                    {l.asignatura} · {l.grado}
                  </div>
                  <div className="mt-1 text-[11.5px] font-bold text-[#9AA0AD]">
                    {l.total_fragmentos} fragmentos · {l.total_lecciones} lecciones
                  </div>
                </div>
                <span
                  className="flex-none rounded-full px-3 py-1.5 text-[11.5px] font-extrabold"
                  style={{ background: est.bg, color: est.color }}
                >
                  {l.estado === "procesando" && (
                    <span className="mr-1 inline-block animate-spin">⏳</span>
                  )}
                  {est.label}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onSubido={() => {
            setShowUpload(false);
            setRefresh((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}
