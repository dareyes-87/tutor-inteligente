/**
 * Cliente API centralizado del Tutor Inteligente.
 *
 * - Base URL configurable vía NEXT_PUBLIC_API_URL (default http://localhost:8000).
 * - Inyecta el JWT (Bearer) automáticamente en cada petición.
 * - Guarda/lee/borra el token en localStorage.
 * - En 401 limpia el token y redirige a /login.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

const TOKEN_KEY = "tutor_token";

// ----------------------- Tipos (espejo de los schemas del backend) -----------------------

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

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface ReferenciaFragment {
  page_num: number | null;
  libro_id: number | null;
  distance: number | null;
}

export interface ChatResponse {
  conversacion_id: number;
  respuesta: string;
  referencias: ReferenciaFragment[];
}

export interface Conversacion {
  id: number;
  titulo: string;
  asignatura_id: number;
  fecha_creacion: string;
  fecha_ultimo_mensaje: string;
}

// ----------------------- Manejo de token -----------------------

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

// ----------------------- Error tipado -----------------------

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function extractDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail) && data.detail[0]?.msg) return data.detail[0].msg;
  } catch {
    /* respuesta sin cuerpo JSON */
  }
  return res.statusText || "Error desconocido";
}

/** Petición genérica con JWT automático. */
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);

  // Solo fijamos JSON si hay body y no es FormData (multipart fija su propio header).
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Sesión expirada. Inicia sesión de nuevo.");
  }

  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ----------------------- Auth -----------------------

/**
 * Login con OAuth2 password flow (form-urlencoded, campos username/password).
 * Guarda el token en localStorage si tiene éxito.
 */
export async function login(username: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);

  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res));
  }

  const data = (await res.json()) as TokenResponse;
  setToken(data.access_token);
  return data;
}

export function logout(): void {
  clearToken();
}

export function getMe(): Promise<Usuario> {
  return request<Usuario>("/auth/me");
}

// ----------------------- Chat -----------------------

export function preguntar(
  pregunta: string,
  asignaturaId: number,
  conversacionId: number | null,
): Promise<ChatResponse> {
  return request<ChatResponse>("/chat/preguntar", {
    method: "POST",
    body: JSON.stringify({
      pregunta,
      asignatura_id: asignaturaId,
      conversacion_id: conversacionId,
    }),
  });
}

export function getConversaciones(): Promise<Conversacion[]> {
  return request<Conversacion[]>("/chat/conversaciones");
}

export function getConversacion(id: number): Promise<unknown> {
  return request<unknown>(`/chat/conversaciones/${id}`);
}

// ----------------------- Actividades -----------------------

export type TipoActividad =
  | "opcion_multiple"
  | "verdadero_falso"
  | "completar"
  | "ordenar"
  | "respuesta_corta";

/** Actividad generada por el backend (sin la respuesta correcta). */
export interface ActividadResponse {
  id: number;
  tipo: TipoActividad;
  tema: string | null;
  /** Forma según el tipo; el frontend la interpreta por `tipo`. */
  contenido: Record<string, unknown>;
  fecha_creacion: string;
}

/** Resultado de evaluar la respuesta del estudiante. */
export interface ResultadoResponse {
  actividad_id: number;
  puntaje: number; // 0–100
  retroalimentacion: string;
  respuesta_correcta: Record<string, unknown>;
}

/** Genera una actividad nueva (usa LLM + RAG; puede tardar varios segundos). */
export function generarActividad(
  asignaturaId: number,
  tipo: TipoActividad,
  tema: string | null,
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

/** Envía la respuesta del estudiante y devuelve puntaje + retroalimentación. */
export function responderActividad(
  actividadId: number,
  respuesta: Record<string, unknown>,
): Promise<ResultadoResponse> {
  return request<ResultadoResponse>("/actividades/responder", {
    method: "POST",
    body: JSON.stringify({ actividad_id: actividadId, respuesta }),
  });
}

// ----------------------- Perfil de comprensión -----------------------

export type NivelComprension = "domina" | "en_proceso" | "refuerzo";

/** Una entrada del perfil de comprensión del estudiante (por tema). */
export interface PerfilTema {
  asignatura: string;
  tema: string;
  puntaje_promedio: number; // 0–100
  nivel: NivelComprension;
  total_actividades: number;
}

/** Perfil de comprensión del estudiante autenticado (por asignatura/tema). */
export function getPerfil(): Promise<PerfilTema[]> {
  return request<PerfilTema[]>("/actividades/perfil");
}

// ----------------------- Ruta de aprendizaje -----------------------

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
  progreso_porcentaje: number; // 0-100
  lecciones: LeccionEnRuta[];
}

/** Libro activo del estudiante, resuelto por su grado en el backend. */
export interface MiLibro {
  libro_id: number;
  titulo: string;
  total_lecciones: number;
}

/** Resuelve el libro activo del estudiante (evita hardcodear el libro_id). */
export function obtenerMiLibro(): Promise<MiLibro> {
  return request<MiLibro>("/lecciones/mi-libro");
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

/** Grado del estudiante autenticado (para el sidebar). */
export interface MiGradoEstudiante {
  id: number | null;
  nombre: string | null;
}
export function obtenerMiGradoEstudiante(): Promise<MiGradoEstudiante> {
  return request<MiGradoEstudiante>("/lecciones/mi-grado");
}

/** Ruta de aprendizaje del libro con el progreso del estudiante. */
export function obtenerRuta(libroId: number): Promise<RutaAprendizaje> {
  return request<RutaAprendizaje>(`/lecciones/ruta?libro_id=${libroId}`);
}

// ----------------------- Micro-lección guiada -----------------------

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

/** Micro-lección guiada (tarjetas) de una lección y nivel; se genera on-demand. */
export function obtenerMicroLeccion(leccionId: number, nivel = 1): Promise<MicroLeccion> {
  return request<MicroLeccion>(`/lecciones/${leccionId}/micro-leccion?nivel=${nivel}`);
}

export interface CompletarNivelResponse {
  nivel_completado: number;
  nivel_actual: number;
  aprobado: boolean;
  mensaje_feedback: string;
  puntos_ganados: number;
  puntos_totales: number;
  posicion_ranking: number;
  cambio_posicion: number;
}

/** Envía el resultado de practicar un nivel (cuántas actividades se aprobaron). */
export function completarNivel(
  leccionId: number,
  puntaje: number,
  nivel: number,
  actividadesAprobadas: number,
  totalActividades: number,
): Promise<CompletarNivelResponse> {
  return request<CompletarNivelResponse>(`/lecciones/${leccionId}/completar-actividad`, {
    method: "POST",
    body: JSON.stringify({
      puntaje,
      nivel,
      actividades_aprobadas: actividadesAprobadas,
      total_actividades: totalActividades,
    }),
  });
}

/** Marca una lección disponible como en progreso. */
export function iniciarLeccion(leccionId: number): Promise<LeccionEnRuta> {
  return request<LeccionEnRuta>(`/lecciones/${leccionId}/iniciar`, { method: "POST" });
}

/** Registra una actividad completada en una lección (puede completarla). */
export function completarActividadLeccion(
  leccionId: number,
  puntaje: number,
): Promise<LeccionEnRuta> {
  return request<LeccionEnRuta>(`/lecciones/${leccionId}/completar-actividad`, {
    method: "POST",
    body: JSON.stringify({ puntaje }),
  });
}

// ----------------------- Gamificación -----------------------

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

/** Racha del estudiante (actual, mejor, y si ya estuvo activo hoy). */
export function obtenerRacha(): Promise<RachaResponse> {
  return request<RachaResponse>("/gamificacion/racha");
}

/** Ranking de los estudiantes del grado del estudiante actual. */
export function obtenerRanking(): Promise<RankingResponse> {
  return request<RankingResponse>("/gamificacion/ranking");
}

// ----------------------- Docente -----------------------

export interface LibroDocente {
  id: number;
  titulo: string;
  asignatura: string;
  grado: string;
  estado: string; // procesando / completado / error / pendiente
  total_fragmentos: number;
  total_lecciones: number;
  fecha_creacion: string;
}

export interface EstudianteResumen {
  id: number;
  nombre: string;
  apellido: string;
  grado: string | null;
  racha_actual: number;
  puntos_totales: number;
  lecciones_completadas: number;
  ultima_actividad: string | null;
}

export interface PerfilTemaDocente {
  asignatura: string;
  tema: string;
  puntaje_promedio: number;
  nivel: string;
  total_actividades: number;
}

export interface EstudianteDetalle {
  id: number;
  nombre: string;
  apellido: string;
  grado: string | null;
  racha_actual: number;
  puntos_totales: number;
  ruta: RutaAprendizaje | null;
  perfil: PerfilTemaDocente[];
}

export interface TemaPreguntado {
  tema: string;
  total: number;
  ejemplo?: string | null;
}

export interface PreguntaFrecuente {
  pregunta: string;
  total: number;
  asignatura: string;
}

export interface EstadisticasDocente {
  total_estudiantes: number;
  total_libros: number;
  total_lecciones: number;
  promedio_progreso: number;
  temas_mas_preguntados: TemaPreguntado[];
  preguntas_frecuentes: PreguntaFrecuente[];
}

export interface LibroSubido {
  id: number;
  titulo: string;
  asignatura_id: number;
  grado_id: number;
  estado_indexacion: string;
}

export function obtenerLibros(): Promise<LibroDocente[]> {
  return request<LibroDocente[]>("/docente/libros");
}

export function obtenerEstudiantes(): Promise<EstudianteResumen[]> {
  return request<EstudianteResumen[]>("/docente/estudiantes");
}

export function obtenerDetalleEstudiante(id: number): Promise<EstudianteDetalle> {
  return request<EstudianteDetalle>(`/docente/estudiantes/${id}/detalle`);
}

export function obtenerEstadisticas(): Promise<EstadisticasDocente> {
  return request<EstadisticasDocente>("/docente/estadisticas");
}

/** Grado del docente autenticado (para el sidebar). */
export interface MiGrado {
  id: number | null;
  nombre: string | null;
}
export function obtenerMiGrado(): Promise<MiGrado> {
  return request<MiGrado>("/docente/mi-grado");
}

/** Asignaturas para el dropdown de subida de libros (rol docente). */
export interface AsignaturaOpcion {
  id: number;
  nombre: string;
}
export function obtenerAsignaturasDocente(): Promise<AsignaturaOpcion[]> {
  return request<AsignaturaOpcion[]>("/docente/asignaturas");
}

/**
 * Sube un libro PDF (multipart). El helper `request` NO fija Content-Type
 * cuando el body es FormData, así que el browser pone el boundary correcto.
 */
export function subirLibro(formData: FormData): Promise<LibroSubido> {
  return request<LibroSubido>("/ingesta/libros", { method: "POST", body: formData });
}

// ===================== Panel administrador =====================

export interface DocenteResumen {
  id: number;
  nombre: string;
  apellido: string;
  username: string;
  activo: boolean;
  grado_id: number | null;
  grado: string | null;
  libros_subidos: number;
}

export interface EstudianteAdminResumen {
  id: number;
  nombre: string;
  apellido: string;
  username: string;
  grado_id: number | null;
  grado: string | null;
  activo: boolean;
  progreso: number;
  ultima_actividad: string | null;
}

export interface EstudianteCreado {
  id: number | null;
  nombre: string;
  apellido: string;
  username: string;
  password_generado: string;
}

export interface GradoResumen {
  id: number;
  nombre: string;
  nivel: string;
  cantidad_estudiantes: number;
  cantidad_docentes: number;
}

export interface AsignaturaResumen {
  id: number;
  nombre: string;
  cantidad_libros: number;
}

export interface DashboardAdmin {
  total_estudiantes: number;
  total_docentes: number;
  total_grados: number;
  total_asignaturas: number;
  total_libros: number;
  total_lecciones: number;
  total_fragmentos: number;
  progreso_general: number;
  estudiantes_activos_hoy: number;
  libro_mas_reciente: { titulo: string; fecha_subida: string; estado: string } | null;
}

// --- Docentes ---
export function adminListarDocentes(): Promise<DocenteResumen[]> {
  return request<DocenteResumen[]>("/admin/docentes");
}
export function adminCrearDocente(body: {
  nombre: string; apellido: string; username: string; password: string; grado_id?: number | null;
}): Promise<Usuario> {
  return request<Usuario>("/admin/docentes", { method: "POST", body: JSON.stringify(body) });
}
export function adminActualizarDocente(
  id: number,
  body: { nombre?: string; apellido?: string; grado_id?: number | null; activo?: boolean },
): Promise<Usuario> {
  return request<Usuario>(`/admin/docentes/${id}`, { method: "PUT", body: JSON.stringify(body) });
}
export function adminResetPasswordDocente(id: number, nueva_password: string): Promise<void> {
  return request<void>(`/admin/docentes/${id}/reset-password`, {
    method: "POST", body: JSON.stringify({ nueva_password }),
  });
}

// --- Estudiantes ---
export function adminListarEstudiantes(params?: { grado_id?: number; activo?: boolean }): Promise<EstudianteAdminResumen[]> {
  const q = new URLSearchParams();
  if (params?.grado_id != null) q.set("grado_id", String(params.grado_id));
  if (params?.activo != null) q.set("activo", String(params.activo));
  const qs = q.toString();
  return request<EstudianteAdminResumen[]>(`/admin/estudiantes${qs ? `?${qs}` : ""}`);
}
export function adminCrearEstudiante(body: {
  nombre: string; apellido: string; grado_id: number; username?: string; password?: string;
}): Promise<EstudianteCreado> {
  return request<EstudianteCreado>("/admin/estudiantes", { method: "POST", body: JSON.stringify(body) });
}
export function adminActualizarEstudiante(
  id: number,
  body: { nombre?: string; apellido?: string; grado_id?: number | null; activo?: boolean },
): Promise<Usuario> {
  return request<Usuario>(`/admin/estudiantes/${id}`, { method: "PUT", body: JSON.stringify(body) });
}
export function adminResetPasswordEstudiante(id: number, nueva_password: string): Promise<void> {
  return request<void>(`/admin/estudiantes/${id}/reset-password`, {
    method: "POST", body: JSON.stringify({ nueva_password }),
  });
}
export function adminImportarEstudiantes(formData: FormData): Promise<EstudianteCreado[]> {
  return request<EstudianteCreado[]>("/admin/estudiantes/importar", { method: "POST", body: formData });
}

// --- Grados ---
export function adminListarGrados(): Promise<GradoResumen[]> {
  return request<GradoResumen[]>("/admin/grados");
}
export function adminCrearGrado(nombre: string): Promise<GradoResumen> {
  return request<GradoResumen>("/admin/grados", { method: "POST", body: JSON.stringify({ nombre }) });
}
export function adminActualizarGrado(id: number, nombre: string): Promise<GradoResumen> {
  return request<GradoResumen>(`/admin/grados/${id}`, { method: "PUT", body: JSON.stringify({ nombre }) });
}
export function adminEliminarGrado(id: number): Promise<void> {
  return request<void>(`/admin/grados/${id}`, { method: "DELETE" });
}
export function adminPromoverGrado(grado_origen_id: number, grado_destino_id: number): Promise<{ estudiantes_promovidos: number }> {
  return request<{ estudiantes_promovidos: number }>("/admin/promover-grado", {
    method: "POST", body: JSON.stringify({ grado_origen_id, grado_destino_id }),
  });
}

// --- Asignaturas ---
export function adminListarAsignaturas(): Promise<AsignaturaResumen[]> {
  return request<AsignaturaResumen[]>("/admin/asignaturas");
}
export function adminCrearAsignatura(nombre: string): Promise<AsignaturaResumen> {
  return request<AsignaturaResumen>("/admin/asignaturas", { method: "POST", body: JSON.stringify({ nombre }) });
}
export function adminActualizarAsignatura(id: number, nombre: string): Promise<AsignaturaResumen> {
  return request<AsignaturaResumen>(`/admin/asignaturas/${id}`, { method: "PUT", body: JSON.stringify({ nombre }) });
}
export function adminEliminarAsignatura(id: number): Promise<void> {
  return request<void>(`/admin/asignaturas/${id}`, { method: "DELETE" });
}

// --- Dashboard ---
export function adminDashboard(): Promise<DashboardAdmin> {
  return request<DashboardAdmin>("/admin/dashboard");
}
