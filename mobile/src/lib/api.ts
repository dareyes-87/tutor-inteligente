/**
 * Cliente API del móvil. Misma lógica que web/lib/api.ts pero con
 * expo-secure-store para persistir el JWT.
 *
 * La URL del backend se inyecta en tiempo de build/dev vía la variable de
 * entorno EXPO_PUBLIC_API_URL (ver eas.json y, para desarrollo local, un
 * archivo .env con `EXPO_PUBLIC_API_URL=...`). Debe usar HTTPS en producción:
 * Android bloquea el tráfico HTTP sin cifrar (cleartext) por defecto.
 *
 * Si la variable no está definida, cae a la URL de producción de Railway, para
 * que el APK nunca quede apuntando a una IP local por accidente.
 */
import * as SecureStore from "expo-secure-store";

// Fuente única de la URL del backend (env de build/dev, con fallback a producción).
export const API_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  "https://tutor-inteligente-production.up.railway.app";

const TOKEN_KEY = "auth_token";

// ----------------------- Token -----------------------

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}
async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}
async function removeToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };

  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    await removeToken();
    throw new ApiError(401, "Sesión expirada");
  }
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ----------------------- Tipos -----------------------

export type Rol = "estudiante" | "docente" | "administrador";
export interface Usuario {
  id: number;
  nombre: string;
  apellido: string;
  username: string;
  rol: Rol;
  grado_id: number | null;
  activo: boolean;
  fecha_creacion: string;
}

export type EstadoLeccion = "bloqueada" | "disponible" | "en_progreso" | "completada";
export interface LeccionEnRuta {
  id: number;
  nombre: string;
  descripcion: string | null;
  orden: number;
  tema_clave: string;
  paginas: string | null;
  estado: EstadoLeccion;
  puntaje_promedio: number;
  actividades_completadas: number;
  actividades_requeridas: number;
  nivel_actual: number;
  nivel_completado: number;
  tiene_corona: boolean;
}
export interface RutaAprendizaje {
  libro_id: number;
  asignatura: string;
  total_lecciones: number;
  lecciones_completadas: number;
  progreso_porcentaje: number;
  lecciones: LeccionEnRuta[];
}

export interface RachaResponse {
  racha_actual: number;
  mejor_racha: number;
  activo_hoy: boolean;
}
export interface RankingEstudiante {
  posicion: number;
  nombre: string;
  apellido: string;
  lecciones_completadas: number;
  puntos_totales: number;
  racha_actual: number;
}
export interface RankingResponse {
  ranking: RankingEstudiante[];
  mi_posicion: number;
}

export interface PerfilTema {
  asignatura: string;
  tema: string;
  puntaje_promedio: number;
  nivel: "domina" | "en_proceso" | "refuerzo";
  total_actividades: number;
}

export interface ChatResponse {
  conversacion_id: number;
  respuesta: string;
  referencias: { page_num: number | null; libro_id: number | null; distance: number | null }[];
}

// ----------------------- Auth -----------------------

export async function login(username: string, password: string): Promise<void> {
  const body = new URLSearchParams();
  body.append("username", username);
  body.append("password", password);

  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) throw new ApiError(res.status, "Usuario o contraseña incorrectos");
  const data = await res.json();
  await setToken(data.access_token);
}

export function getMe(): Promise<Usuario> {
  return request<Usuario>("/auth/me");
}

export async function logout(): Promise<void> {
  await removeToken();
}

// ----------------------- Ruta + gamificación -----------------------

export interface MiLibro {
  libro_id: number;
  titulo: string;
  total_lecciones: number;
}
export function obtenerMiLibro(): Promise<MiLibro> {
  return request<MiLibro>("/lecciones/mi-libro");
}
export function obtenerRuta(libroId: number): Promise<RutaAprendizaje> {
  return request<RutaAprendizaje>(`/lecciones/ruta?libro_id=${libroId}`);
}

/** Un libro disponible del grado del estudiante, con su asignatura. */
export interface LibroDisponible {
  libro_id: number;
  titulo: string;
  asignatura_id: number;
  asignatura_nombre: string;
  total_lecciones: number;
}
/** Todos los libros disponibles del estudiante (por grado). Lista vacía si no hay. */
export function obtenerMisLibros(): Promise<LibroDisponible[]> {
  return request<LibroDisponible[]>("/lecciones/mis-libros");
}

export interface PreguntaRapida {
  texto: string;
  tipo: string; // verdadero_falso | opcion_multiple
  opciones: string[];
  respuesta_correcta: string;
  explicacion: string;
}
export interface TarjetaEducativa {
  tipo: "introduccion" | "concepto" | "resumen";
  contenido: string;
  emoji: string;
  titulo_concepto: string | null;
  dato_curioso: string | null;
  pregunta: PreguntaRapida | null;
}
export interface MicroLeccion {
  titulo: string;
  tarjetas: TarjetaEducativa[];
  fragment_ids: number[];
  nivel_actual: number;
  es_ultimo_nivel: boolean;
}
export function obtenerMicroLeccion(leccionId: number, nivel = 1): Promise<MicroLeccion> {
  return request<MicroLeccion>(`/lecciones/${leccionId}/micro-leccion?nivel=${nivel}`);
}
export interface CompletarNivelResponse {
  nivel_completado: number;
  nivel_actual: number;
  aprobado: boolean;
  mensaje_feedback: string;
}
export function completarNivel(
  leccionId: number,
  puntaje: number,
  nivel: number,
  actividadesAprobadas: number,
): Promise<CompletarNivelResponse> {
  return request<CompletarNivelResponse>(`/lecciones/${leccionId}/completar-actividad`, {
    method: "POST",
    body: JSON.stringify({ puntaje, nivel, actividades_aprobadas: actividadesAprobadas }),
  });
}
export function iniciarLeccion(leccionId: number): Promise<LeccionEnRuta> {
  return request<LeccionEnRuta>(`/lecciones/${leccionId}/iniciar`, { method: "POST" });
}
export function obtenerRacha(): Promise<RachaResponse> {
  return request<RachaResponse>("/gamificacion/racha");
}
export function obtenerRanking(): Promise<RankingResponse> {
  return request<RankingResponse>("/gamificacion/ranking");
}
export function getPerfil(): Promise<PerfilTema[]> {
  return request<PerfilTema[]>("/actividades/perfil");
}

// ----------------------- Chat + actividades (para Parte 2) -----------------------

export function preguntar(
  pregunta: string,
  asignaturaId: number,
  conversacionId: number | null,
): Promise<ChatResponse> {
  return request<ChatResponse>("/chat/preguntar", {
    method: "POST",
    body: JSON.stringify({ pregunta, asignatura_id: asignaturaId, conversacion_id: conversacionId }),
  });
}
export type TipoActividad =
  | "opcion_multiple"
  | "verdadero_falso"
  | "completar"
  | "ordenar"
  | "respuesta_corta";

export interface ActividadResponse {
  id: number;
  tipo: TipoActividad;
  tema: string | null;
  contenido: Record<string, unknown>;
  fecha_creacion: string;
}

export interface ResultadoResponse {
  actividad_id: number;
  puntaje: number; // 0-100
  retroalimentacion: string;
  respuesta_correcta: Record<string, unknown>;
}

export function generarActividad(
  asignaturaId: number,
  tipo: TipoActividad,
  tema: string,
  leccionId: number | null = null,
  fragmentIds: number[] = [],
  evitarPreguntas: string[] = [],
): Promise<ActividadResponse> {
  return request<ActividadResponse>("/actividades/generar", {
    method: "POST",
    body: JSON.stringify({
      asignatura_id: asignaturaId,
      tipo,
      tema,
      leccion_id: leccionId,
      fragment_ids: fragmentIds,
      evitar_preguntas: evitarPreguntas,
    }),
  });
}
export function responderActividad(
  actividadId: number,
  respuesta: Record<string, unknown>,
): Promise<ResultadoResponse> {
  return request<ResultadoResponse>("/actividades/responder", {
    method: "POST",
    body: JSON.stringify({ actividad_id: actividadId, respuesta }),
  });
}
