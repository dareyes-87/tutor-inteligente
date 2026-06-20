/**
 * Datos de ejemplo (placeholder) para las pantallas que aún no tienen endpoint
 * en el backend: racha, ranking, progreso por capítulo y panel docente.
 *
 * ⚠️ TEMPORAL: cuando existan los endpoints reales, reemplazar estos datos por
 * llamadas a `lib/api.ts`. Tomados tal cual de la guía de diseño.
 */

export type Nivel = "domina" | "proceso" | "refuerzo";

export const NIVEL_META: Record<
  Nivel,
  { chip: string; chipBg: string; chipColor: string; bar: string; dot: string }
> = {
  domina: { chip: "Domina ✅", chipBg: "#E9F9EF", chipColor: "#16A34A", bar: "#22C55E", dot: "#22C55E" },
  proceso: { chip: "En proceso 🟡", chipBg: "#FEF6E7", chipColor: "#D97706", bar: "#F59E0B", dot: "#F59E0B" },
  refuerzo: { chip: "Necesita refuerzo 🔴", chipBg: "#FDECEC", chipColor: "#DC2626", bar: "#EF4444", dot: "#EF4444" },
};

// ---- Dashboard ----

export interface DiaRacha {
  label: string;
  done: boolean;
}
export const SEMANA_RACHA: DiaRacha[] = [
  { label: "L", done: true },
  { label: "M", done: true },
  { label: "M", done: true },
  { label: "J", done: true },
  { label: "V", done: true },
  { label: "S", done: false },
  { label: "D", done: false },
];
export const RACHA_DIAS = SEMANA_RACHA.filter((d) => d.done).length;

export interface Asignatura {
  name: string;
  pct: number;
  color: string;
  soft: string;
  icon: string;
  meta: string;
}
export const ASIGNATURAS_PROGRESO: Asignatura[] = [
  { name: "Ciencias Naturales", pct: 72, color: "#22C55E", soft: "#E9F9EF", icon: "🌱", meta: "18 de 25 temas" },
  { name: "Matemáticas", pct: 45, color: "#2563EB", soft: "#EAF1FF", icon: "➗", meta: "9 de 20 temas" },
  { name: "Lenguaje", pct: 88, color: "#F97316", soft: "#FFF1E7", icon: "📖", meta: "22 de 25 temas" },
  { name: "Estudios Sociales", pct: 33, color: "#8B5CF6", soft: "#F1ECFE", icon: "🌎", meta: "5 de 15 temas" },
];

// ---- Chat (mensajes de ejemplo para el estado inicial) ----

export interface ChatEjemplo {
  who: "tutor" | "me";
  text: string;
  page?: string;
}
export const CHAT_DEMO: ChatEjemplo[] = [
  { who: "tutor", text: "¡Hola, Sofía! 🐯 Soy tu tutor. ¿Qué tema de Ciencias Naturales quieres repasar hoy?" },
  { who: "me", text: "¿Por qué llueve?" },
  {
    who: "tutor",
    text: "¡Excelente pregunta! La lluvia es parte del ciclo del agua: el sol calienta el agua de ríos y mares, se evapora y sube al cielo formando nubes. Cuando las gotitas se juntan y pesan mucho… ¡caen como lluvia! 🌧️",
    page: "📖 Página 48 del libro",
  },
  { who: "me", text: "¿Y a dónde va el agua después?" },
  {
    who: "tutor",
    text: "Vuelve a los ríos, lagos y mares, y el ciclo empieza otra vez. ¡Por eso el agua nunca se acaba! 💧",
    page: "📖 Página 49 del libro",
  },
];

// ---- Actividades ----

export interface ActividadItem {
  type: string;
  icon: string;
  color: string;
  soft: string;
  theme: string;
  meta: string;
}
export const ACTIVIDADES: ActividadItem[] = [
  { type: "Opción múltiple", icon: "☑️", color: "#2563EB", soft: "#EAF1FF", theme: "El ciclo del agua", meta: "10 preguntas · 5 min" },
  { type: "Verdadero / Falso", icon: "⚖️", color: "#8B5CF6", soft: "#F1ECFE", theme: "Los estados de la materia", meta: "8 preguntas · 4 min" },
  { type: "Completar", icon: "✏️", color: "#F97316", soft: "#FFF1E7", theme: "Partes de la planta", meta: "6 preguntas · 5 min" },
  { type: "Ordenar", icon: "🔢", color: "#22C55E", soft: "#E9F9EF", theme: "Etapas del ciclo de vida", meta: "5 preguntas · 3 min" },
  { type: "Respuesta corta", icon: "💬", color: "#EC4899", soft: "#FCE9F2", theme: "¿Por qué llueve?", meta: "3 preguntas · 6 min" },
];

// ---- Progreso por capítulo ----

export interface Capitulo {
  name: string;
  pct: number;
  nivel: Nivel;
  done: string;
}
export const CAPITULOS: Capitulo[] = [
  { name: "Capítulo 1 · Los seres vivos", pct: 100, nivel: "domina", done: "8/8" },
  { name: "Capítulo 2 · El ciclo del agua", pct: 70, nivel: "proceso", done: "6/8" },
  { name: "Capítulo 3 · La materia y sus cambios", pct: 40, nivel: "proceso", done: "3/8" },
  { name: "Capítulo 4 · La energía", pct: 20, nivel: "refuerzo", done: "2/8" },
  { name: "Capítulo 5 · El sistema solar", pct: 0, nivel: "refuerzo", done: "0/8" },
];

// ---- Ranking ----

export interface Alumno {
  name: string;
  pts: number;
  streak: number;
  av: string;
  me?: boolean;
}
export const SALON: Alumno[] = [
  { name: "Mariana G.", pts: 2840, streak: 12, av: "#F59E0B" },
  { name: "Diego R.", pts: 2610, streak: 8, av: "#2563EB" },
  { name: "Sofía M.", pts: 2480, streak: 5, av: "#F97316", me: true },
  { name: "Lucas P.", pts: 2150, streak: 6, av: "#8B5CF6" },
  { name: "Valentina C.", pts: 1980, streak: 3, av: "#EC4899" },
  { name: "Mateo H.", pts: 1760, streak: 4, av: "#22C55E" },
  { name: "Camila R.", pts: 1540, streak: 2, av: "#06B6D4" },
  { name: "Andrés T.", pts: 1320, streak: 1, av: "#EF4444" },
];

export const inicial = (n: string) => n.trim()[0];
export const fmtPts = (n: number) => n.toLocaleString("es");

export interface PodioPuesto {
  medal: string;
  ring: string;
  bg: string;
  tall: string;
  h: string;
  pos: number;
  name: string;
  pts: string;
  initial: string;
}
const PODIO_DEF = [
  { idx: 1, medal: "🥈", ring: "#CBD5E1", bg: "#E2E8F0", tall: "120px", h: "92px" },
  { idx: 0, medal: "🥇", ring: "#FBBF24", bg: "#FEF3C7", tall: "160px", h: "120px" },
  { idx: 2, medal: "🥉", ring: "#FB923C", bg: "#FFEDD5", tall: "96px", h: "74px" },
];
export const PODIO: PodioPuesto[] = PODIO_DEF.map((p) => {
  const s = SALON[p.idx];
  return {
    medal: p.medal,
    ring: p.ring,
    bg: p.bg,
    tall: p.tall,
    h: p.h,
    pos: p.idx + 1,
    name: s.me ? "Tú" : s.name,
    pts: fmtPts(s.pts),
    initial: s.me ? "🐯" : inicial(s.name),
  };
});
export const RANKING_RESTO = SALON.slice(3).map((s, i) => ({
  pos: i + 4,
  name: s.name,
  streak: s.streak,
  pts: fmtPts(s.pts),
  initial: inicial(s.name),
  avBg: s.av,
}));

// ---- Docente ----

export interface LibroDocente {
  title: string;
  pages: number;
  status: string;
  statBg: string;
  statColor: string;
  statDot: string;
  spine: string;
}
export const LIBROS_DOCENTE: LibroDocente[] = [
  { title: "Ciencias Naturales 5", pages: 212, status: "Indexado", statBg: "#E9F9EF", statColor: "#16A34A", statDot: "✓", spine: "#22C55E" },
  { title: "Matemáticas 5", pages: 188, status: "Indexado", statBg: "#E9F9EF", statColor: "#16A34A", statDot: "✓", spine: "#2563EB" },
  { title: "Estudios Sociales 5", pages: 164, status: "Procesando", statBg: "#FEF6E7", statColor: "#D97706", statDot: "⏳", spine: "#8B5CF6" },
];

export interface EstudianteDocente {
  name: string;
  av: string;
  niveles: [Nivel, Nivel, Nivel]; // Ciencias, Matemáticas, Lenguaje
}
export const ESTUDIANTES_DOCENTE: EstudianteDocente[] = [
  { name: "Mariana G.", av: "#F59E0B", niveles: ["domina", "domina", "proceso"] },
  { name: "Diego R.", av: "#2563EB", niveles: ["domina", "proceso", "domina"] },
  { name: "Sofía M.", av: "#F97316", niveles: ["proceso", "domina", "domina"] },
  { name: "Lucas P.", av: "#8B5CF6", niveles: ["proceso", "refuerzo", "proceso"] },
  { name: "Valentina C.", av: "#EC4899", niveles: ["domina", "domina", "domina"] },
  { name: "Mateo H.", av: "#22C55E", niveles: ["refuerzo", "proceso", "refuerzo"] },
];

export interface Faq {
  q: string;
  count: number;
  topic: string;
  accent: string;
}
export const FAQS: Faq[] = [
  { q: "¿Por qué llueve?", count: 18, topic: "El ciclo del agua", accent: "#2563EB" },
  { q: "¿Qué es la fotosíntesis?", count: 14, topic: "Las plantas", accent: "#22C55E" },
  { q: "¿Cuántos planetas hay?", count: 11, topic: "El sistema solar", accent: "#F97316" },
  { q: "¿Por qué flotan los barcos?", count: 9, topic: "La materia", accent: "#8B5CF6" },
];
