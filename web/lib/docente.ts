/** Helpers visuales compartidos por las páginas del panel docente. */

/** Color por % de progreso (verde ≥80 / naranja 50–79 / rojo <50). */
export function colorProgreso(pct: number): string {
  if (pct >= 80) return "#22C55E";
  if (pct >= 50) return "#F97316";
  return "#EF4444";
}

/** Estilos del badge de estado de indexación de un libro. */
export const ESTADO_LIBRO: Record<string, { bg: string; color: string; label: string }> = {
  completado: { bg: "#E9F9EF", color: "#16A34A", label: "Completado" },
  procesando: { bg: "#FEF6E7", color: "#D97706", label: "Procesando…" },
  pendiente: { bg: "#F1EDE5", color: "#8A8F9C", label: "Pendiente" },
  error: { bg: "#FDECEC", color: "#DC2626", label: "Error" },
};
