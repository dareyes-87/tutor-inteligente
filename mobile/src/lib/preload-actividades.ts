// Pre-carga de actividades de práctica: mientras el estudiante lee la
// micro-lección (Estudiar), se dispara en segundo plano la generación de las
// actividades de la sesión, para que al tocar "Practicar" ya estén listas (o
// casi). Con el modelo 70B de Matemáticas la generación tarda ~3s por
// actividad; adelantarla ahorra la mayor parte de la espera.
//
// La generación es SECUENCIAL a propósito: cada actividad conoce las preguntas
// anteriores para no repetirlas (fix del Prompt 7). La pre-carga solo adelanta
// el inicio de esa misma secuencia; NO la paraleliza.
import { generarActividad, type ActividadResponse, type TipoActividad } from "./api";

const TIPOS: TipoActividad[] = [
  "opcion_multiple",
  "verdadero_falso",
  "completar",
  "ordenar",
  "respuesta_corta",
];

export interface ParamsGeneracion {
  leccionId: number;
  asignaturaId: number;
  tema: string;
  fragmentIds: number[];
}

/** Genera las actividades de una sesión EN SECUENCIA, acumulando el texto de
 *  cada pregunta para que la siguiente no la repita. Tolera que una actividad
 *  falle (red/timeout): sigue con las demás y devuelve las que sí salieron. */
export async function generarActividadesSesion(
  p: ParamsGeneracion,
): Promise<ActividadResponse[]> {
  const generadas: ActividadResponse[] = [];
  const preguntasPrevias: string[] = [];
  for (const t of TIPOS) {
    try {
      const a = await generarActividad(
        p.asignaturaId,
        t,
        p.tema,
        p.leccionId,
        p.fragmentIds,
        preguntasPrevias,
      );
      generadas.push(a);
      const c = a.contenido as Record<string, unknown>;
      const texto = (c.pregunta ?? c.afirmacion ?? c.oracion ?? c.instruccion) as
        | string
        | undefined;
      if (texto) preguntasPrevias.push(texto);
    } catch {
      /* una actividad fallida no rompe la sesión: se sigue con las demás */
    }
  }
  return generadas;
}

// Cache de UNA sola pre-carga en curso/lista (la última disparada). Vive a
// nivel de módulo para sobrevivir la navegación Estudiar → Practicar.
let cache: { key: string; promise: Promise<ActividadResponse[]> } | null = null;
const makeKey = (leccionId: number, nivel: number) => `${leccionId}:${nivel}`;

/** Dispara la generación en segundo plano. Idempotente por lección+nivel: si
 *  ya hay una pre-carga para ese objetivo, no vuelve a lanzarla. */
export function precargarActividades(nivel: number, p: ParamsGeneracion): void {
  const key = makeKey(p.leccionId, nivel);
  if (cache?.key === key) return;
  const promise = generarActividadesSesion(p);
  promise.catch(() => {});
  cache = { key, promise };
}

/** Consume la pre-carga si coincide con lección+nivel (y la limpia, para que
 *  una visita futura vuelva a pre-cargar). Devuelve null si no hay pre-carga
 *  para ese objetivo (p. ej. el estudiante entró directo a Practicar). */
export function tomarActividadesPrecargadas(
  leccionId: number,
  nivel: number,
): Promise<ActividadResponse[]> | null {
  if (cache?.key === makeKey(leccionId, nivel)) {
    const promise = cache.promise;
    cache = null;
    return promise;
  }
  return null;
}
