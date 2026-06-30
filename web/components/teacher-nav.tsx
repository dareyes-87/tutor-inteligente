"use client";

/**
 * Sidebar del docente — versión sobria (navy) de la navegación.
 * Cada item navega a su página; el activo se resalta según la ruta actual.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { obtenerMiGrado } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { TEACHER_NAV } from "@/lib/constants";

export function TeacherNav() {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  // Grado real del docente (el backend resuelve el nombre desde su grado_id).
  const [grado, setGrado] = useState<string | null>(null);
  useEffect(() => {
    let activo = true;
    obtenerMiGrado()
      .then((g) => {
        if (activo) setGrado(g.nombre);
      })
      .catch(() => {
        /* silencioso: si falla, el sidebar solo muestra "Salir" */
      });
    return () => {
      activo = false;
    };
  }, []);

  const nombre = user ? `Docente ${user.apellido || user.nombre}` : "Docente";
  const iniciales = user
    ? `${user.nombre[0] ?? ""}${user.apellido[0] ?? ""}`.toUpperCase()
    : "PR";

  return (
    <div className="flex w-[248px] flex-none flex-col gap-1.5 self-stretch bg-navy px-[18px] py-[26px]">
      {/* Logo */}
      <div className="flex items-center gap-3 px-2 pb-6 pt-0.5">
        <img
          src="/logo_colegio.png"
          alt="Oasis Christian School"
          className="h-14 w-14 flex-none object-contain"
        />
        <div className="leading-[1.05]">
          <div className="text-base font-black text-white">Oasis</div>
          <div className="text-[10.5px] font-bold tracking-[0.04em] text-[#8E97AD]">
            PANEL DOCENTE
          </div>
        </div>
      </div>

      {/* Items */}
      {TEACHER_NAV.map((n) => {
        // "/docente" (Resumen) sólo se marca activo en la ruta exacta; el resto
        // también con sub-rutas (p. ej. /docente/estudiantes/3).
        const active =
          n.href === "/docente"
            ? pathname === "/docente"
            : pathname === n.href || pathname.startsWith(`${n.href}/`);
        return (
          <Link
            key={n.key}
            href={n.href}
            className={`flex items-center gap-[13px] rounded-xl px-[15px] py-[13px] transition-colors ${
              active ? "bg-brand-blue" : "hover:bg-white/[0.06]"
            }`}
          >
            <span className="text-lg">{n.icon}</span>
            <span
              className={`text-[14.5px] ${
                active ? "font-extrabold text-white" : "font-semibold text-[#B6C0D6]"
              }`}
            >
              {n.label}
            </span>
          </Link>
        );
      })}

      {/* Usuario + salir */}
      <button
        onClick={logout}
        className="mt-auto flex items-center gap-[11px] rounded-xl bg-white/[0.06] p-3 text-left transition-colors hover:bg-white/10"
      >
        <div className="grid h-10 w-10 flex-none place-items-center rounded-full bg-brand-blue font-black text-white">
          {iniciales}
        </div>
        <div className="leading-[1.1]">
          <div className="text-[13.5px] font-extrabold text-white">{nombre}</div>
          <div className="text-[11px] font-bold text-[#8E97AD]">
            {grado ? `${grado} · Salir` : "Salir"}
          </div>
        </div>
      </button>
    </div>
  );
}
