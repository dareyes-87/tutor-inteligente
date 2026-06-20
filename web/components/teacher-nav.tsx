"use client";

/**
 * Sidebar del docente — versión sobria (navy) de la navegación.
 * Single-page por ahora: "Resumen" queda activo.
 */
import { useAuth } from "@/lib/auth";
import { TEACHER_NAV } from "@/lib/constants";

export function TeacherNav() {
  const { user, logout } = useAuth();

  const nombre = user ? `Prof. ${user.apellido || user.nombre}` : "Docente";
  const iniciales = user
    ? `${user.nombre[0] ?? ""}${user.apellido[0] ?? ""}`.toUpperCase()
    : "PR";

  return (
    <div className="flex w-[248px] flex-none flex-col gap-1.5 self-stretch bg-navy px-[18px] py-[26px]">
      {/* Logo */}
      <div className="flex items-center gap-3 px-2 pb-6 pt-0.5">
        <div
          className="grid h-12 w-[42px] flex-none place-items-center bg-white"
          style={{ clipPath: "polygon(0 0,100% 0,100% 68%,50% 100%,0 68%)" }}
        >
          <span className="text-lg">📖</span>
        </div>
        <div className="leading-[1.05]">
          <div className="text-base font-black text-white">Oasis</div>
          <div className="text-[10.5px] font-bold tracking-[0.04em] text-[#8E97AD]">
            PANEL DOCENTE
          </div>
        </div>
      </div>

      {/* Items */}
      {TEACHER_NAV.map((n, i) => {
        const active = i === 0;
        return (
          <div
            key={n.key}
            className={`flex items-center gap-[13px] rounded-xl px-[15px] py-[13px] ${
              active ? "bg-brand-blue" : ""
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
          </div>
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
          <div className="text-[11px] font-bold text-[#8E97AD]">5to Primaria · Salir</div>
        </div>
      </button>
    </div>
  );
}
