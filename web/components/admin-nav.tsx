"use client";

/**
 * Sidebar del administrador. Paleta slate/gris oscuro para diferenciarlo del
 * panel docente (navy/azul). Cada item navega a su página.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { ADMIN_NAV } from "@/lib/constants";

export function AdminNav() {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  const nombre = user ? `${user.nombre} ${user.apellido}` : "Administrador";
  const iniciales = user
    ? `${user.nombre[0] ?? ""}${user.apellido[0] ?? ""}`.toUpperCase()
    : "AD";

  return (
    <div className="flex w-[248px] flex-none flex-col gap-1.5 self-stretch bg-slate-900 px-[18px] py-[26px]">
      {/* Logo */}
      <div className="flex items-center gap-3 px-2 pb-6 pt-0.5">
        <div className="grid h-12 w-[42px] flex-none place-items-center rounded-md bg-slate-700 text-lg">
          ⚙️
        </div>
        <div className="leading-[1.05]">
          <div className="text-base font-black text-white">Oasis</div>
          <div className="text-[10.5px] font-bold tracking-[0.06em] text-slate-400">
            ADMINISTRACIÓN
          </div>
        </div>
      </div>

      {/* Items */}
      {ADMIN_NAV.map((n) => {
        const active =
          n.href === "/admin"
            ? pathname === "/admin"
            : pathname === n.href || pathname.startsWith(`${n.href}/`);
        return (
          <Link
            key={n.key}
            href={n.href}
            className={`flex items-center gap-[13px] rounded-xl px-[15px] py-[13px] transition-colors ${
              active ? "bg-slate-700" : "hover:bg-white/[0.06]"
            }`}
          >
            <span className="text-lg">{n.icon}</span>
            <span
              className={`text-[14.5px] ${
                active ? "font-extrabold text-white" : "font-semibold text-slate-300"
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
        <div className="grid h-10 w-10 flex-none place-items-center rounded-full bg-slate-600 font-black text-white">
          {iniciales}
        </div>
        <div className="min-w-0 leading-[1.1]">
          <div className="truncate text-[13.5px] font-extrabold text-white">{nombre}</div>
          <div className="text-[11px] font-bold text-slate-400">Administrador · Salir</div>
        </div>
      </button>
    </div>
  );
}
