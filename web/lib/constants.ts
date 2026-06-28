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

/** Sidebar del administrador — gestión de la estructura del colegio. */
export const ADMIN_NAV: NavItem[] = [
  { href: "/admin", key: "dashboard", label: "Dashboard", icon: "📊" },
  { href: "/admin/docentes", key: "docentes", label: "Docentes", icon: "👨‍🏫" },
  { href: "/admin/estudiantes", key: "estudiantes", label: "Estudiantes", icon: "👩‍🎓" },
  { href: "/admin/grados", key: "grados", label: "Grados", icon: "🏫" },
  { href: "/admin/asignaturas", key: "asignaturas", label: "Asignaturas", icon: "📚" },
];

/** Ruta de inicio según el rol del usuario. */
export function homeForRole(rol: Rol): string {
  if (rol === "estudiante") return "/inicio";
  if (rol === "administrador") return "/admin";
  return "/docente";
}
