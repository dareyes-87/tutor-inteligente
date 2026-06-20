"use client";

/**
 * Sidebar de navegación del estudiante — réplica de StudentNav del diseño.
 * Marca el item activo según la ruta y usa el contexto de auth para el usuario.
 */
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { STUDENT_NAV } from "@/lib/constants";

export function StudentNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const nombre = user ? `${user.nombre} ${user.apellido[0] ?? ""}.` : "Estudiante";
  const grado = "5to Primaria";

  return (
    <aside className="flex w-[248px] shrink-0 flex-col gap-1.5 self-stretch border-r border-border bg-white px-[18px] py-[26px]">
      {/* Logo */}
      <div className="flex items-center gap-3 px-2 pb-6 pt-0.5">
        <div
          className="grid h-12 w-[42px] flex-none place-items-center bg-navy"
          style={{
            clipPath: "polygon(0 0,100% 0,100% 68%,50% 100%,0 68%)",
            boxShadow: "inset 0 0 0 2px #F97316",
          }}
        >
          <span className="text-lg leading-none">📖</span>
        </div>
        <div className="leading-[1.05]">
          <div className="text-base font-black text-navy">Oasis</div>
          <div className="text-[10.5px] font-bold tracking-[0.04em] text-muted-foreground">
            CHRISTIAN SCHOOL
          </div>
        </div>
      </div>

      {/* Items */}
      {STUDENT_NAV.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.key}
            href={item.href}
            className={`flex items-center gap-[13px] rounded-2xl px-[15px] py-[13px] transition-colors ${
              active ? "bg-accent" : "hover:bg-muted/60"
            }`}
          >
            <span className="w-[22px] text-center text-[19px] leading-none">{item.icon}</span>
            <span
              className={`text-[15.5px] ${
                active ? "font-extrabold text-accent-foreground" : "font-semibold text-[#5A6170]"
              }`}
            >
              {item.label}
            </span>
          </Link>
        );
      })}

      {/* Usuario + salir */}
      <div className="mt-auto flex items-center gap-[11px] rounded-2xl bg-muted/70 p-3">
        <div className="h-[42px] w-[42px] flex-none overflow-hidden rounded-full bg-navy ring-2 ring-brand-orange">
          <Image
            src="/assets/mascota.png"
            alt=""
            width={42}
            height={42}
            className="h-full w-full object-cover"
          />
        </div>
        <div className="min-w-0 leading-[1.1]">
          <div className="truncate text-sm font-extrabold text-navy">{nombre}</div>
          <button
            onClick={logout}
            className="text-[11.5px] font-bold text-muted-foreground hover:text-brand-orange"
          >
            {grado} · Salir
          </button>
        </div>
      </div>
    </aside>
  );
}
