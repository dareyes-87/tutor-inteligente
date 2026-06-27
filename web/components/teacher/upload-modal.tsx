"use client";

/**
 * Modal para subir un nuevo libro (PDF) — compartido por el panel docente.
 * La asignatura/grado están fijos en Fase 1 (un solo libro de Ciencias 1ro).
 */
import { useState } from "react";
import { toast } from "sonner";

import { ApiError, subirLibro } from "@/lib/api";

export function UploadModal({ onClose, onSubido }: { onClose: () => void; onSubido: () => void }) {
  const [titulo, setTitulo] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);

  async function handleSubir(e: React.FormEvent) {
    e.preventDefault();
    if (!titulo.trim() || !file || subiendo) return;
    setSubiendo(true);
    try {
      const fd = new FormData();
      fd.append("titulo", titulo.trim());
      fd.append("asignatura_id", "1");
      fd.append("grado_id", "1");
      fd.append("archivo", file);
      await subirLibro(fd);
      toast.success("Libro subido. Procesando OCR…");
      onSubido();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "No se pudo subir el libro");
      setSubiendo(false);
    }
  }

  return (
    <ModalShell onClose={subiendo ? undefined : onClose} titulo="Subir nuevo libro">
      <form onSubmit={handleSubir} className="flex flex-col gap-4">
        <Campo label="Título del libro">
          <input
            value={titulo}
            onChange={(ev) => setTitulo(ev.target.value)}
            placeholder="Ej: Ciencias Naturales 1ro"
            className="w-full rounded-xl border-2 border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy outline-none focus:border-brand-blue"
          />
        </Campo>
        <div className="grid grid-cols-2 gap-4">
          <Campo label="Asignatura">
            <select
              disabled
              className="w-full rounded-xl border-2 border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy outline-none"
            >
              <option>Ciencias Naturales</option>
            </select>
          </Campo>
          <Campo label="Grado">
            <select
              disabled
              className="w-full rounded-xl border-2 border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy outline-none"
            >
              <option>1ro Básico</option>
            </select>
          </Campo>
        </div>
        <Campo label="Archivo PDF">
          <input
            type="file"
            accept=".pdf"
            onChange={(ev) => setFile(ev.target.files?.[0] ?? null)}
            className="w-full rounded-xl border-2 border-dashed border-border bg-muted/40 px-4 py-3 text-sm font-semibold text-navy file:mr-3 file:rounded-lg file:border-0 file:bg-brand-blue file:px-3 file:py-1.5 file:font-extrabold file:text-white"
          />
        </Campo>
        <div className="mt-2 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={subiendo}
            className="rounded-xl border-2 border-border bg-white px-5 py-2.5 text-sm font-extrabold text-[#5A6170] disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={!titulo.trim() || !file || subiendo}
            className="rounded-xl bg-brand-blue px-6 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_#1D4ED8] active:translate-y-px disabled:opacity-50"
          >
            {subiendo ? "Subiendo…" : "Subir"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function ModalShell({
  titulo,
  onClose,
  children,
}: {
  titulo: string;
  onClose?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="max-h-[88vh] w-full max-w-[560px] overflow-y-auto rounded-[20px] bg-white p-7 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <div className="text-xl font-black text-navy">{titulo}</div>
          {onClose && (
            <button
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-full bg-muted text-lg font-black text-muted-foreground hover:bg-muted/70"
            >
              ✕
            </button>
          )}
        </div>
        {children}
      </div>
    </div>
  );
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[13px] font-extrabold text-[#5A6170]">{label}</label>
      {children}
    </div>
  );
}
