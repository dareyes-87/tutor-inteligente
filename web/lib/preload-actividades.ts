// Pre-carga de actividades de práctica: mientras el estudiante lee la
// micro-lección (Estudiar), se dispara en segundo plano la generación de las
// actividades de la sesión, para que al tocar "Practicar" ya estén listas (o
// casi). Con el modelo 70B de Matemáticas la generación tarda ~3s por
// actividad; adelantarla ahorra la mayor parte de la espera.
//
// La generación es SECUENCIAL a propósito: cada actividad conoce las preguntas
// anteriores para no repetirlas (fix del Prompt 7). La pre-carga solo adelanta
// el inicio de esa misma secuencia; NO la paraleliza.
import {
  generarActividad,
  type ActividadResponse,
  type TarjetaEducativa,
  type TipoActividad,
} from "./api";

/** Extrae de las tarjetas de la micro-lección los conceptos que el tutor
 *  explicó, como "título: explicación". Solo tarjetas de tipo "concepto" (la
 *  intro y el resumen no son conceptos evaluables) y SIN el dato curioso (es
 *  justo la trivia que no queremos que la práctica pregunte). Enfoque A. */
export function conceptosDeTarjetas(tarjetas: TarjetaEducativa[]): string[] {
  return tarjetas
    .filter((t) => t.tipo === "concepto" && (t.contenido || "").trim())
    .map((t) => {
      const titulo = (t.titulo_concepto || "").trim();
      const cuerpo = (t.contenido || "").trim();
      return titulo ? `${titulo}: ${cuerpo}` : cuerpo;
    });
}

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
  // Conceptos que el tutor explicó en la micro-lección (Enfoque A): acotan la
  // práctica a lo estudiado. Vacío = práctica sobre todo el rango (fallback).
  conceptos: string[];
}

// Preguntas ya hechas en la lección, persistidas ENTRE niveles. El generador
// usa un universo reducido (solo los conceptos estudiados), así que sin memoria
// cross-nivel repetiría la misma pregunta a lo largo de las ~15 generaciones de
// una lección (5 por nivel × 3 niveles). Se guardan por lección en
// sessionStorage y se resetean solas al estudiar otra lección (otra key) o al
// cerrar la pestaña. Se acotan a las últimas MAX para no crecer sin límite.
const MAX_PREGUNTAS_PERSISTIDAS = 30;
const keyPreguntas = (leccionId: number) => `preguntas_leccion_${leccionId}`;

function leerPreguntasPrevias(leccionId: number): string[] {
  try {
    const raw = sessionStorage.getItem(keyPreguntas(leccionId));
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(arr) ? arr.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function guardarPreguntasPrevias(leccionId: number, preguntas: string[]): void {
  try {
    const recorte = preguntas.slice(-MAX_PREGUNTAS_PERSISTIDAS);
    sessionStorage.setItem(keyPreguntas(leccionId), JSON.stringify(recorte));
  } catch {
    /* sessionStorage no disponible: la sesión sigue, solo sin memoria cross-nivel */
  }
}

/** Genera las actividades de una sesión EN SECUENCIA, acumulando el texto de
 *  cada pregunta para que la siguiente no la repita. La lista de preguntas se
 *  siembra desde (y se reescribe en) sessionStorage, de modo que la memoria
 *  anti-repetición abarca TODA la lección (los 3 niveles), no solo la sesión
 *  actual. Tolera que una actividad falle (red/timeout): sigue con las demás y
 *  devuelve las que sí salieron. */
export async function generarActividadesSesion(
  p: ParamsGeneracion,
): Promise<ActividadResponse[]> {
  const generadas: ActividadResponse[] = [];
  const preguntasPrevias: string[] = leerPreguntasPrevias(p.leccionId);
  for (const t of TIPOS) {
    try {
      const a = await generarActividad(
        p.asignaturaId,
        t,
        p.tema,
        p.leccionId,
        p.fragmentIds,
        preguntasPrevias,
        p.conceptos,
      );
      generadas.push(a);
      const c = a.contenido as Record<string, unknown>;
      const texto = (c.pregunta ?? c.afirmacion ?? c.oracion ?? c.instruccion) as
        | string
        | undefined;
      if (texto) {
        preguntasPrevias.push(texto);
        guardarPreguntasPrevias(p.leccionId, preguntasPrevias);
      }
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
  // Evita "unhandled rejection" si algo lanzara pese al try/catch interno.
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
