# Diagnóstico: fallo en generación de micro-lecciones

**Fecha:** 2026-08-20
**Alcance:** SOLO diagnóstico. No se modificó código de producción ni se tocó `MODAL_FINETUNED_GRADOS`.

## Resumen ejecutivo

La generación de micro-lecciones **NO pasa por Modal en ningún momento**. El error
"No se pudo generar la micro-lección" / "No pudimos preparar esta lección" **no está
relacionado con el A/B del modelo fine-tuned**. La causa raíz más probable es un
problema de **arquitectura de concurrencia**: la llamada al LLM en
`generar_micro_leccion()` es **síncrona y bloqueante**, y el backend corre con
**`--workers 1`**. Cuando dos o más estudiantes piden una micro-lección (o cualquier
combinación de chat/micro-lección) casi al mismo tiempo —muy común al inicio de una
clase, cuando el docente pide a todos abrir la app—, las peticiones se **encolan en
serie sobre el único worker**, y la latencia se acumula hasta superar el timeout del
gateway de Railway, que responde 502 y el frontend lo muestra como el error genérico.

Esto reproduce, en esencia, el MISMO problema que ya se corrigió una vez en el commit
`093762a` (9 jul) — pero esa corrección (timeout de 45s + 1 reintento en el SDK,
fallback de cobertura) no cubre el caso de **cola por concurrencia**, que es distinto
a "una sola llamada lenta".

## 1. Confirmación: ¿qué modelo/servicio usa la micro-lección?

`backend/app/modules/lecciones/service.py:616-622`:

```python
modelo = modelo_para_asignatura(asignatura_nombre)
...
data = llm_client.generate_json(messages, max_tokens=4096, model=modelo)
```

`modelo_para_asignatura()` (`backend/app/llm/client.py:24-30`) devuelve
`meta-llama/Llama-3.3-70B-Instruct-Turbo` solo si la asignatura es Matemáticas, y
`None` (=`Qwen2.5-7B-Instruct-Turbo` por defecto) para el resto. **Ambos casos van a
Together AI vía `generate_json()`**, que internamente solo llama a
`self._client.chat.completions.create(...)` del SDK de Together
(`backend/app/llm/client.py:169-178`). `generate_json()` **nunca** invoca
`chat_finetuned()` ni el cliente httpx de Modal — esa ruta solo existe en
`chat/service.py` para el endpoint de chat normal. Confirmado por grep: `Modal`,
`MODAL_`, `chat_finetuned` no aparecen en ningún archivo de `modules/lecciones/`.

**Conclusión del punto 1:** correcto, la micro-lección usa exclusivamente Together AI
(7B o 70B según asignatura). El cold start de Modal no puede afectar esta ruta.

## 2. Logs de producción (Railway)

No tuve acceso a los logs de Railway desde este entorno (no hay `railway` CLI
instalado/autenticado en esta máquina). **Este es el hueco de evidencia más
importante que falta** — recomiendo que alguien con acceso a Railway busque, para el
endpoint `GET /lecciones/{id}/micro-leccion`, específicamente:
- Líneas `[MicroLeccion] ... reintentando…` o `502` en los logs del backend.
- Si el 502 lo genera el propio backend (`HTTPException(502, ...)`, con traceback o
  log warning de `generate_json`) o si el backend nunca llega a loguear nada (lo que
  apuntaría a que el gateway de Railway cortó la conexión ANTES de que el handler
  terminara — consistente con la hipótesis de cola por concurrencia).
- Timestamps de los 502 comparados con timestamps de otras peticiones concurrentes
  (¿hay ráfagas de varios estudiantes pidiendo `/micro-leccion` o `/preguntar` en la
  misma ventana de ~1 minuto?).

## 3. Reproducción en local

Con el stack local (`docker compose up`, libro Matemáticas 4to, `--workers 1` igual
que producción):

**Petición aislada — funciona, pero es lenta:**
| Lección | Nivel | Modelo | Tiempo | Resultado |
|---|---|---|---|---|
| 249 (Conjuntos) | 1 (top-k=5) | 70B | 17.8s | 200 OK |
| 249 (Conjuntos) | 3 (top-k=10) | 70B | 27.3s | 200 OK |

**Dos peticiones concurrentes (249 y 250, ambas nivel 1) + un `/health` en medio:**

```
p1 (lección 249): 200 OK en 12.6s
/health (disparado 2s después, mientras p1 corría): 200 OK en 10.6s  ← debería ser <100ms
p2 (lección 251): 200 OK en 64.6s                    ← vs. ~13-18s en aislamiento
```

**Esto es la evidencia clave.** `/health` es un endpoint trivial (ping a Postgres +
Chroma) que normalmente responde en milisegundos. Que tardara 10.6s mientras un `curl`
a `/micro-leccion` estaba en vuelo demuestra que el event loop del único worker quedó
bloqueado por la llamada síncrona a Together — **ninguna otra petición pudo avanzar
mientras tanto**. `p2` no tardó ~15s (lo que tarda en aislamiento), tardó 64.6s porque
tuvo que esperar en cola detrás de `p1` antes de que su propio handler pudiera
siquiera empezar a ejecutarse.

Con 2 estudiantes concurrentes ya se llega a >60s. Con 3-4 estudiantes pidiendo
`/micro-leccion` casi a la vez (o mezclado con varios pidiendo `/chat`, que tiene el
mismo problema — ver sección 4), el tiempo de cola fácilmente supera cualquier timeout
razonable de gateway (Railway suele cortar peticiones colgadas bastante antes de los
2-3 minutos que este escenario puede alcanzar), produciendo el 502 que el frontend
muestra como "No pudimos preparar esta lección" / "No se pudo generar la
micro-lección".

No se logró reproducir un 502 real en un entorno de baja concurrencia (1 usuario) —
consistente con que el problema depende de carga concurrente, que mi entorno local no
tiene por defecto.

## 4. Causa raíz: llamadas síncronas bloqueantes en un backend `--workers 1`

`backend/app/llm/client.py` documenta el patrón correcto para llamadas lentas al LLM,
pero **solo lo aplica a una de las tres rutas que llaman a un LLM externo**:

- `chat/service.py:340` — `chat_finetuned()` (Modal): **SÍ** usa
  `await asyncio.to_thread(...)`. El comentario en `client.py:121-124` explica por
  qué: *"El backend corre con --workers 1: el llamador DEBE ejecutar esto en un hilo
  aparte... o un cold start congelaría el servidor entero para todos los
  estudiantes, no solo para este."*
- `chat/service.py:344` y `:347` — `llm_client.chat()` (Together, chat normal,
  incluido el fallback de Modal): llamada síncrona directa, **sin** `to_thread`.
- `actividades/generator.py:861,1211,1216` — `llm_client.generate_json()`: síncrona,
  sin `to_thread`.
- `lecciones/service.py:622` — `llm_client.generate_json()` (micro-lección, hasta 2
  intentos): síncrona, sin `to_thread`.

Es decir: el propio autor del código ya identificó y documentó exactamente este
riesgo para la llamada a Modal, pero el mismo razonamiento no se aplicó a las
llamadas a Together, que son las que usa el 100% de los estudiantes (todos pasan por
`chat()`/`generate_json()`; solo la cohorte del A/B pasa también por
`chat_finetuned()`). La micro-lección es la ruta más expuesta porque:
- Usa `max_tokens=4096` (vs. 1024 en chat normal) → respuestas más largas → más
  tiempo bloqueando el loop.
- Puede hacer **hasta 2 llamadas secuenciales** (el retry-loop de cobertura,
  `lecciones/service.py:618-656`), cada una bloqueante.
- Para Matemáticas usa el 70B, más lento que el 7B por defecto.

## 5. Hipótesis descartadas/confirmadas

- **¿Cambios recientes en `lecciones/service.py`, `rag/search.py` o
  `chat/prompts.py` esta semana?** No. `git log` confirma que los commits de esta
  semana (`4bef2c4`, `778d298`, `081758a`, `bd8d252`, `e25142c`) tocaron
  `chat/service.py`, `chat/prompts.py`, `config.py`, `main.py` y
  `workers/modal_keepwarm.py` — **ninguno tocó `lecciones/service.py` ni
  `rag/search.py`**. El único cambio de `4bef2c4` en la página de "Estudiar"
  (`web/app/(app)/ruta/[leccionId]/estudiar/page.tsx`) fue el aviso "el tutor está
  despertando" dentro del **mini-chat incrustado** de esa página (que sí usa
  `/preguntar`), no en la carga de la micro-lección misma.
- **¿Filtro de cobertura mínima (4 tarjetas) fallando por rangos de página
  específicos (portada/OCR)?** Ya mitigado desde el commit `093762a` (9 jul): si el
  filtro dejaría 0 tarjetas, se devuelven las tarjetas sin filtrar en vez de un 502
  (`lecciones/service.py:640-647`). Sigue siendo una fuente *posible* de 502 si el
  LLM nunca genera tarjetas válidas en 2 intentos, pero no fue lo que reproduje
  localmente.
- **¿Rate limit o cuota de Together (429)?** No se observó en las pruebas locales.
  No puedo confirmar ni descartar del todo sin los logs de Railway (sección 2).
- **¿Timeout de red Railway↔Together no relacionado con Modal?** **Sí, esta es la
  hipótesis que la evidencia local respalda mejor** — pero el mecanismo específico
  encontrado es cola por concurrencia en un solo worker, no una llamada individual
  colgada (eso ya se corrigió en `093762a`).

## 6. Relación con el A/B de Modal

**Ninguna relación directa.** La ruta de micro-lección nunca toca Modal. Sí hay una
relación **indirecta** que vale la pena que el equipo conozca (sin que implique
tocar el A/B): si en producción hay estudiantes de la cohorte fine-tuned generando
carga adicional en el mismo worker (aunque su propia llamada a Modal esté
correctamente en `to_thread`, cualquier OTRA petición síncrona —chat normal,
actividades, micro-lección— seguirá bloqueando ese mismo worker), el problema de cola
descrito en la sección 4 empeora con más estudiantes activos simultáneamente,
independientemente de si usan Modal o no. Es decir: ampliar el A/B a todos los grados
aumentó la cantidad de estudiantes activos a la vez, lo cual **sí pudo aumentar la
frecuencia con la que se dispara este problema preexistente**, sin que el A/B sea la
causa del error en sí.

## 7. Propuesta de corrección (NO implementada — pendiente de confirmación)

Ordenadas de más simple/menos invasiva a más completa:

1. **Mínimo viable:** envolver la llamada síncrona de
   `lecciones/service.py:622` en `await asyncio.to_thread(llm_client.generate_json, ...)`,
   igual que ya se hace para `chat_finetuned()`. Esto no evita que Together tarde,
   pero libera el event loop para que otras peticiones (incluidas otras
   micro-lecciones o chats) no queden bloqueadas detrás de esta. Es el cambio de
   menor riesgo: una línea, mismo patrón ya validado en el propio código.
2. **Misma idea, aplicada también** a `chat/service.py:344,347` y a las 3 llamadas
   de `actividades/generator.py` — para que NINGUNA llamada al LLM bloquee el
   worker único. Más cobertura, pero toca más archivos/módulos.
3. **Más completo (fuera de alcance de un fix rápido):** subir `--workers` en
   `start.sh` si el resto del backend lo permite (revisar si hay estado
   in-memory compartido entre requests que asuma un solo proceso, p. ej. el
   singleton de embeddings en `pdf_processor`/`embeddings.py`), o migrar las
   llamadas al SDK de Together a su variante async si Together la ofrece (evitaría
   el hilo extra de `to_thread`).

**Recomendación:** opción 1 primero (aislado a `lecciones/service.py`, que es el
módulo que reportó el bug), medir en producción si baja la tasa de 502, y luego
evaluar si conviene extenderlo a chat/actividades (opción 2). No se implementó nada
de esto todavía, a la espera de confirmación.
