import type { Rol } from "@/lib/api";

/**
 * Asignaturas hardcodeadas (Fase 1).
 * En una fase futura se cargarán desde un endpoint GET /asignaturas del backend.
 */
export const ASIGNATURAS: { id: number; nombre: string }[] = [
  { id: 1, nombre: "Ciencias Naturales" },
];

/** Item de navegación del estudiante (sidebar). */
export interface NavItem {
  href: string;
  /** clave usada para marcar el item activo */
  key: string;
  label: string;
  icon: string;
}

/** Sidebar del estudiante — réplica de StudentNav del diseño. */
export const STUDENT_NAV: NavItem[] = [
  { href: "/ruta", key: "ruta", label: "Mi Ruta", icon: "🗺️" },
  { href: "/inicio", key: "inicio", label: "Inicio", icon: "🏠" },
  { href: "/chat", key: "chat", label: "Chat", icon: "💬" },
  { href: "/actividades", key: "actividades", label: "Actividades", icon: "🎯" },
  { href: "/progreso", key: "progreso", label: "Mi progreso", icon: "📈" },
  { href: "/ranking", key: "ranking", label: "Ranking", icon: "🏆" },
];

/** Sidebar del docente — más sobrio, misma paleta. Cada item navega a su página. */
export const TEACHER_NAV: NavItem[] = [
  { href: "/docente", key: "resumen", label: "Resumen", icon: "📊" },
  { href: "/docente/libros", key: "libros", label: "Libros", icon: "📚" },
  { href: "/docente/estudiantes", key: "estudiantes", label: "Estudiantes", icon: "👩‍🎓" },
  { href: "/docente/preguntas", key: "preguntas", label: "Preguntas", icon: "❓" },
];

/** Ruta de inicio según el rol del usuario. */
export function homeForRole(rol: Rol): string {
  return rol === "estudiante" ? "/inicio" : "/docente";
}
