"use client";

/** Componentes de UI compartidos por las páginas del panel admin. */
import { useState } from "react";

export function ModalShell({
  titulo,
  onClose,
  children,
  ancho = "max-w-[520px]",
}: {
  titulo: string;
  onClose?: () => void;
  children: React.ReactNode;
  ancho?: string;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div
        className={`max-h-[88vh] w-full ${ancho} overflow-y-auto rounded-[20px] bg-white p-7 shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <div className="text-xl font-black text-slate-900">{titulo}</div>
          {onClose && (
            <button
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-full bg-slate-100 text-lg font-black text-slate-500 hover:bg-slate-200"
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

export function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[13px] font-extrabold text-slate-600">{label}</label>
      {children}
    </div>
  );
}

export const inputCls =
  "w-full rounded-xl border-2 border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-900 outline-none focus:border-slate-500";

export function BotonPrimario({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="rounded-xl bg-slate-800 px-6 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_#0f172a] active:translate-y-px disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function BotonSecundario({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="rounded-xl border-2 border-slate-200 bg-white px-5 py-2.5 text-sm font-extrabold text-slate-600 disabled:opacity-50"
    >
      {children}
    </button>
  );
}

/** Badge de estado activo/inactivo. */
export function EstadoBadge({ activo }: { activo: boolean }) {
  return (
    <span
      className="rounded-full px-3 py-1 text-[11.5px] font-extrabold"
      style={
        activo
          ? { background: "#E9F9EF", color: "#16A34A" }
          : { background: "#F1F1F4", color: "#8A8F9C" }
      }
    >
      {activo ? "Activo" : "Inactivo"}
    </span>
  );
}

/** Modal para resetear contraseña: pide una nueva y la confirma. */
export function ResetPasswordModal({
  nombre,
  onClose,
  onConfirm,
}: {
  nombre: string;
  onClose: () => void;
  onConfirm: (nueva: string) => Promise<void>;
}) {
  const [pass, setPass] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pass.trim().length < 3 || guardando) return;
    setGuardando(true);
    try {
      await onConfirm(pass.trim());
    } finally {
      setGuardando(false);
    }
  }

  return (
    <ModalShell titulo={`Resetear contraseña · ${nombre}`} onClose={guardando ? undefined : onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Campo label="Nueva contraseña">
          <input
            value={pass}
            onChange={(e) => setPass(e.target.value)}
            placeholder="Mínimo 3 caracteres"
            className={inputCls}
            autoFocus
          />
        </Campo>
        <div className="flex justify-end gap-3">
          <BotonSecundario type="button" onClick={onClose} disabled={guardando}>
            Cancelar
          </BotonSecundario>
          <BotonPrimario type="submit" disabled={pass.trim().length < 3 || guardando}>
            {guardando ? "Guardando…" : "Resetear"}
          </BotonPrimario>
        </div>
      </form>
    </ModalShell>
  );
}
