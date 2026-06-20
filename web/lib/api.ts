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
): Promise<ActividadResponse> {
  return request<ActividadResponse>("/actividades/generar", {
    method: "POST",
    body: JSON.stringify({ asignatura_id: asignaturaId, tipo, tema }),
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
