"use client";

/**
 * Barra de pestañas inferior — navegación del estudiante en móvil (<768px).
 * En md:+ se oculta y se usa StudentNav (sidebar). Replica las secciones
 * principales: Inicio, Mi Ruta, Progreso, Ranking y Chat.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/inicio", label: "Inicio", icon: "🏠" },
  { href: "/ruta", label: "Mi Ruta", icon: "📚" },
  { href: "/progreso", label: "Progreso", icon: "📊" },
  { href: "/ranking", label: "Ranking", icon: "🏆" },
  { href: "/chat", label: "Chat", icon: "💬" },
];

export function StudentTabBar() {
  const pathname = usePathname();

  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex h-16 items-stretch border-t border-border bg-white pb-[env(safe-area-inset-bottom)] md:hidden">
      {TABS.map((t) => {
        const active = pathname === t.href || pathname.startsWith(`${t.href}/`);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`flex flex-1 flex-col items-center justify-center gap-0.5 text-[10.5px] font-extrabold transition-colors ${
              active ? "text-brand-blue" : "text-[#9AA0AD]"
            }`}
          >
            <span className="text-[19px] leading-none">{t.icon}</span>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
