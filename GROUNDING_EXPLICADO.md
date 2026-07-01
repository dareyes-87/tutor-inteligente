# Grounding del Tutor Inteligente — Explicación técnica

> Documento de apoyo para la defensa de tesis. Describe **cómo el sistema evita
> alucinaciones**, anclando las respuestas del chat en los fragmentos recuperados
> de los libros de texto (RAG) en lugar del conocimiento de entrenamiento del LLM.
>
> **Importante (honestidad técnica):** el sistema se diseñó con la idea de un
> "grounding de triple capa". Al auditar el código real, **la Capa 1 es fuerte y
> determinística; la Capa 2 no es una verificación independiente sino
> instrucciones dentro del mismo prompt de generación; y la Capa 3** detecta
> rechazos **y valida que las páginas citadas por el modelo existan entre los
> fragmentos recuperados** (refuerzo agregado antes del piloto). Sigue sin
> comparar el contenido palabra por palabra contra los fragmentos. Los detalles
> exactos están abajo. Se documenta lo que **realmente existe**, no una versión
> idealizada.

---

## Resumen de las 3 capas (para leer en la defensa)

**Capa 1 — Determinística (umbral de similitud).**
Antes de llamar al LLM, se mide la distancia vectorial entre la pregunta y los
fragmentos recuperados de ChromaDB. Si ningún fragmento supera el umbral de
relevancia, **la pregunta se rechaza con un mensaje fijo y el LLM nunca se
invoca**. Es la capa más fuerte porque no depende de que el modelo obedezca.

**Capa 2 — Verificación por LLM (dentro del prompt).**
Cuando sí hay contexto, al modelo se le entrega un *system prompt* con reglas
estrictas: responder **exclusivamente** con los fragmentos, no complementar con
conocimiento propio, y devolver una frase de rechazo exacta si el tema no
coincide. **No es una segunda llamada a Together AI**: la "verificación" ocurre
como instrucción dentro de la misma generación. Depende de la obediencia del
modelo.

**Capa 3 — Post-generación.**
Tras generar la respuesta se hacen dos comprobaciones sobre el texto: (a)
*string-matching* para detectar si el LLM rechazó la pregunta, y (b)
**validación de citas**: se extraen las páginas citadas ("(página X)") y se
verifica que existan entre los fragmentos recuperados. En cualquiera de los dos
casos problemáticos **se eliminan las referencias a páginas** y se deja un log de
auditoría. (Aún no compara el contenido de la respuesta palabra por palabra
contra los fragmentos.)

---

## Capa 1 — Determinística (umbral de similitud)

**Archivo:** `backend/app/modules/rag/search.py`
**Funciones:** `search_fragments()` e `is_context_relevant()`
**Gate de decisión:** `backend/app/modules/chat/service.py`, función `procesar_pregunta()`

### Cómo se calcula la distancia
La pregunta se convierte en embedding (sentence-transformers, mismo modelo que
indexó los libros) y se consulta ChromaDB, que devuelve una **distancia** por
fragmento (menor = más parecido):

```python
# backend/app/modules/rag/search.py:47-48
query_embedding = generate_embeddings([query])[0]
# ...
# backend/app/modules/rag/search.py:74
results = collection.query(**query_params)
# ...
# backend/app/modules/rag/search.py:81
distance = results["distances"][0][i] if results["distances"] else None
```

### Los umbrales y la "lógica OR"
```python
# backend/app/modules/rag/search.py:20-22
UMBRAL_ESTRICTO = 0.85
UMBRAL_AMPLIO = 1.5
MIN_FRAGMENTOS_AMPLIO = 2

# backend/app/modules/rag/search.py:30
MAX_DISTANCE = 1.55
```

Hay **dos usos distintos** de umbral:

1. **`MAX_DISTANCE = 1.55`** filtra *qué fragmentos se devuelven* como ventana de
   contexto (línea 85-86). Es un recorte de "qué ve el LLM", no la decisión de
   relevancia:
   ```python
   # backend/app/modules/rag/search.py:85-86
   if distance is not None and distance > MAX_DISTANCE:
       continue
   ```

2. **La decisión de relevancia** (`is_context_relevant`) usa la lógica OR con los
   otros dos umbrales:
   ```python
   # backend/app/modules/rag/search.py:129-134
   distancias = [f["distance"] for f in fragments if f.get("distance") is not None]

   match_fuerte = any(d <= UMBRAL_ESTRICTO for d in distancias)
   matches_amplios = sum(1 for d in distancias if d <= UMBRAL_AMPLIO)

   return match_fuerte or matches_amplios >= MIN_FRAGMENTOS_AMPLIO
   ```
   **Condición exacta:** el contexto se considera relevante si
   **(A)** hay ≥1 fragmento con distancia ≤ 0.85 (un match muy bueno) **O**
   **(B)** hay ≥2 fragmentos con distancia ≤ 1.5 (varios matches decentes).

### ¿Qué pasa si ningún fragmento pasa el umbral?
**La pregunta se rechaza ANTES de llamar al LLM.** El gate está en el chat:

```python
# backend/app/modules/chat/service.py:138-157
if is_context_relevant(fragments):
    context = build_context_prompt(fragments)
    messages = build_messages(context, history, pregunta, grado_nombre, asignatura_nombre)
    # ...
    respuesta = llm_client.chat(messages)      # ← única llamada al LLM
    fragments_referencia = fragments
else:
    logger.info("[Chat] Contexto NO relevante: respuesta determinística de rechazo (sin LLM)")
    respuesta = RESPUESTA_FUERA_DE_CONTEXTO      # ← mensaje fijo, sin LLM
    fragments_referencia = []
```

El mensaje de rechazo es una constante, no lo genera el modelo:
```python
# backend/app/modules/chat/service.py:22-25
RESPUESTA_FUERA_DE_CONTEXTO = (
    "No encuentro información sobre eso en tus libros de clase. "
    "¿Quieres preguntarme sobre los temas que estamos viendo?"
)
```

> **Esta es la garantía más fuerte contra alucinaciones:** una pregunta fuera de
> los libros **nunca llega al modelo**, así que el modelo no tiene oportunidad de
> inventar. Es puro código determinístico, reproducible y auditable.

---

## Capa 2 — Verificación por LLM (dentro del prompt de generación)

**Archivo:** `backend/app/modules/chat/prompts.py`
**Función:** `build_system_prompt()` → bloque `REGLAS_BASE`

### ⚠️ Aclaración honesta
**NO existe una segunda llamada a Together AI para verificar la respuesta.** La
"verificación por LLM" son **instrucciones dentro del mismo prompt** de la única
llamada de generación (`llm_client.chat(messages)`). Es decir, se le *pide* al
modelo que se auto-limite; no hay un verificador independiente que revise la
salida.

### La instrucción exacta de grounding en el prompt
```text
# backend/app/modules/chat/prompts.py  (constante REGLAS_BASE)
REGLA FUNDAMENTAL: Responde EXCLUSIVAMENTE con la información que aparece en los
fragmentos del libro proporcionados como contexto. Esta regla NO tiene excepciones.

REGLA ADICIONAL DE VERIFICACIÓN:
Antes de responder, compara el TEMA de la pregunta del estudiante con el TEMA de
los fragmentos proporcionados. Si la pregunta trata de un tema distinto al de los
fragmentos —aunque parezcan relacionados o pertenezcan a la misma materia—,
responde EXACTAMENTE: "No encuentro información sobre eso en tus libros de clase.
¿Quieres preguntarme sobre los temas que estamos viendo en clase?"
No uses tu conocimiento propio para llenar vacíos temáticos: si los fragmentos no
tratan específicamente el tema de la pregunta, NO inventes la respuesta aunque
sepas la respuesta correcta.

REGLAS ESTRICTAS:
1. Si la respuesta NO está en los fragmentos, responde EXACTAMENTE: "No encuentro
   información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que
   estamos viendo en clase?"
2. NO complementes con conocimiento propio...
3. Cita la página del libro de donde sacas cada dato: (página X).
```

### ¿Qué pasa si el LLM determina que su respuesta no está sustentada?
El modelo, siguiendo las reglas, **debe emitir la frase de rechazo** (p. ej.
"No encuentro información sobre eso en tus libros..."). Ese texto de rechazo lo
detecta después la Capa 3. Pero si el modelo **desobedece** (alucina igual), esta
capa **no lo impide por sí sola** — su fuerza depende de la obediencia del modelo
(Qwen2.5-7B). Por eso la Capa 1 (determinística) es la red principal y esta es
"la segunda red".

---

## Capa 3 — Post-generación

**Archivo:** `backend/app/modules/chat/service.py`
**Funciones:** `_es_rechazo()`, `_paginas_citadas()`, `_citas_validas()` y su
aplicación en `procesar_pregunta()`

### Qué verifica (dos comprobaciones)

**(a) Detección de rechazo** — *string-matching* de frases típicas de rechazo:
```python
# backend/app/modules/chat/service.py:31-47
PALABRAS_RECHAZO = (
    "no encuentro", "no tengo información", "no tengo informacion",
    "fuera del tema", "no puedo responder", "no está en", "no esta en",
    "lo siento", "no aparece",
)

def _es_rechazo(respuesta: str) -> bool:
    """True si la respuesta del tutor es un rechazo por estar fuera de los libros."""
    texto = respuesta.lower()
    return any(p in texto for p in PALABRAS_RECHAZO)
```

**(b) Validación de citas de página** — extrae las páginas citadas en la
respuesta y verifica que existan entre los fragmentos recuperados (campo
`page_num`, ver `rag/search.py:93`):
```python
# backend/app/modules/chat/service.py
def _paginas_citadas(respuesta: str) -> list[int]:
    """Extrae los números de página citados en el texto, formato '(página X)'."""
    return [int(n) for n in re.findall(r"p[aá]gina\s+(\d+)", respuesta, re.IGNORECASE)]


def _citas_validas(respuesta: str, fragments: list[dict]) -> bool:
    """
    True si todas las páginas citadas en la respuesta existen entre los
    fragmentos recuperados. Si la respuesta no cita ninguna página, se considera
    válida (no es una alucinación de citas).
    """
    citadas = _paginas_citadas(respuesta)
    if not citadas:
        return True
    paginas_disponibles = {
        f.get("page_num") for f in fragments if f.get("page_num") is not None
    }
    return all(p in paginas_disponibles for p in citadas)
```

### Cómo se aplican en el flujo (Opción A: limpiar referencias + log)
```python
# backend/app/modules/chat/service.py
if _es_rechazo(respuesta):
    fragments_referencia = []
elif not _citas_validas(respuesta, fragments):
    logger.warning(
        "[Chat] Grounding: el modelo citó una página que NO está en los "
        "fragmentos recuperados. Pregunta=%r, respuesta=%r, "
        "paginas_citadas=%r, paginas_disponibles=%r",
        pregunta, respuesta, _paginas_citadas(respuesta),
        {f.get("page_num") for f in fragments},
    )
    fragments_referencia = []
    # OPCIÓN B (más estricta, desactivada): descartar también el contenido.
    # respuesta = RESPUESTA_FUERA_DE_CONTEXTO
```

**Efecto cuando detecta una cita inválida (Opción A, la activa):** elimina las
referencias (no se muestran páginas que no respaldan la respuesta) y registra un
`logger.warning` con la pregunta, la respuesta, las páginas citadas y las
disponibles — **evidencia auditable** en los logs de Railway. La respuesta sí se
muestra al estudiante. Cambiar a la Opción B (tratar la cita inválida como
alucinación y reemplazar toda la respuesta por el mensaje de rechazo) es
descomentar una línea.

**Lo que esta capa todavía NO hace:**
- ❌ No compara el texto de la respuesta palabra por palabra contra los
  fragmentos (no mide *faithfulness* semántico completo).
- ❌ No reintenta ni corrige la respuesta (en Opción A).

**Lo que SÍ hace ahora (nuevo):** valida que **cada página citada exista** entre
los fragmentos recuperados; si el modelo inventa una cita ("(página 99)" cuando
solo se recuperaron las páginas 12–13), lo detecta, limpia las referencias y lo
registra.

---

## Flujo completo (paso a paso)

```
Estudiante envía pregunta
        │
        ▼
[1] Embedding de la pregunta (sentence-transformers)
        │  search.py:48
        ▼
[2] ChromaDB devuelve TOP_K=5 fragmentos con distancia,
    filtrados por asignatura + grado (metadatos)
        │  search.py:74
        ▼
[3] Se descartan fragmentos con distancia > MAX_DISTANCE (1.55)
        │  search.py:85-86
        ▼
┌─────────────────────────────────────────────────────────────┐
│ CAPA 1 (determinística) — is_context_relevant(fragments)     │
│  ¿(≥1 frag ≤ 0.85)  OR  (≥2 frags ≤ 1.5)?                     │
│  search.py:129-134  ·  gate en chat/service.py:138           │
└─────────────────────────────────────────────────────────────┘
        │                                   │
     NO relevante                        SÍ relevante
        │                                   │
        ▼                                   ▼
  Respuesta FIJA                    Se arma el prompt con los
  RESPUESTA_FUERA_DE_CONTEXTO       fragmentos como contexto
  (LLM NO se llama)                 + reglas de grounding
  referencias = []                        │  ┌──────────────────────────────┐
  service.py:156-157                      │  │ CAPA 2 (LLM, dentro del prompt)│
        │                                 │  │ REGLAS_BASE en prompts.py       │
        │                                 ▼  └──────────────────────────────┘
        │                          llm_client.chat(messages)  ← ÚNICA llamada al LLM
        │                          service.py:150
        │                                 │
        │                                 ▼
        │                    ┌────────────────────────────────────────────┐
        │                    │ CAPA 3 (post-generación)                   │
        │                    │ (a) _es_rechazo(respuesta)?                │
        │                    │ (b) _citas_validas(respuesta, fragments)?  │
        │                    │  → rechazo O cita inválida: referencias=[] │
        │                    │  → cita inválida: logger.warning (auditoría)│
        │                    └────────────────────────────────────────────┘
        │                                 │
        └────────────────┬────────────────┘
                         ▼
        Se guardan mensajes (usuario + asistente) en Postgres,
        con referencias = páginas de los fragmentos usados
        service.py:164-189
                         ▼
        El estudiante recibe la respuesta (+ referencias, salvo rechazo)
```

---

## Tabla resumen

| Capa | Archivo | Función | Qué verifica | Qué pasa si "falla" (no hay grounding) |
|------|---------|---------|--------------|-----------------------------------------|
| **1 — Determinística** | `rag/search.py` (gate en `chat/service.py:138`) | `is_context_relevant()` / `search_fragments()` | Que exista contexto suficientemente cercano: (≥1 frag ≤0.85) **OR** (≥2 frags ≤1.5) | Se devuelve mensaje fijo `RESPUESTA_FUERA_DE_CONTEXTO`; **el LLM nunca se invoca**; referencias vacías |
| **2 — LLM (en prompt)** | `chat/prompts.py` | `build_system_prompt()` / `REGLAS_BASE` | Instruye al modelo a responder solo con los fragmentos y emitir frase de rechazo si el tema no coincide | El modelo *debería* emitir el rechazo; si desobedece, esta capa por sí sola no lo impide (depende de la Capa 1 y 3) |
| **3 — Post-generación** | `chat/service.py` | `_es_rechazo()`, `_citas_validas()`, `_paginas_citadas()` | (a) si la respuesta es un rechazo (*string-matching*); (b) que cada página citada exista entre los fragmentos recuperados | En ambos casos **elimina las referencias** (páginas) y, en cita inválida, deja `logger.warning` de auditoría. No re-verifica el contenido semántico completo |

---

## Regla "NO retornar referencias cuando el grounding rechaza"

**Confirmada.** Se aplica en **dos puntos** de
`backend/app/modules/chat/service.py`:

1. **Rechazo determinístico (Capa 1):** cuando el contexto no es relevante, ni
   siquiera se llama al LLM y las referencias quedan vacías:
   ```python
   # backend/app/modules/chat/service.py:156-157
   respuesta = RESPUESTA_FUERA_DE_CONTEXTO
   fragments_referencia = []
   ```

2. **Rechazo del propio LLM (Capa 3):** aunque el contexto pasara el umbral, si el
   modelo respondió con un rechazo, se limpian las referencias:
   ```python
   # backend/app/modules/chat/service.py:161-162
   if _es_rechazo(respuesta):
       fragments_referencia = []
   ```

Luego, las referencias que llegan al estudiante se construyen desde
`fragments_referencia` (vacío en ambos casos de rechazo):
```python
# backend/app/modules/chat/service.py:165-168
referencias_json = [
    {"page_num": f.get("page_num"), "libro_id": f.get("libro_id"), "distance": f.get("distance")}
    for f in fragments_referencia
]
```

---

## Nota: el mismo grounding se reutiliza en Actividades

La generación de actividades usa la **misma Capa 1** (`is_context_relevant`) como
guardarraíl:
```python
# backend/app/modules/actividades/service.py:132-133
if usar_grounding and not is_context_relevant(fragments):
    logger.warning("Contexto no relevante; no se genera actividad (grounding estricto)")
```

---

## Evaluación honesta para la defensa

- **Capa más fuerte:** la **Capa 1 (determinística)**. Es código puro, no depende
  del modelo, es reproducible y auditable, y **corta la pregunta antes de que el
  LLM pueda alucinar**. Es el argumento técnico más sólido ante el asesor.
- **Capa 2:** es real pero es **instrucción en el prompt**, no un verificador
  independiente. No hay una segunda llamada al LLM. Su eficacia depende de que
  Qwen2.5-7B obedezca.
- **Capa 3:** reforzada. Además de detectar rechazos, ahora **valida que las
  páginas citadas por el modelo existan** entre los fragmentos recuperados y deja
  evidencia en logs cuando no. Sigue sin medir *faithfulness* semántico completo
  (no compara el contenido palabra por palabra), así que no debe presentarse como
  una verificación total del contenido, pero **ya no es un simple post-procesado
  de referencias**: detecta un tipo concreto y frecuente de alucinación (citas
  inventadas).

**Recomendación honesta:** al defender, enfatizar la Capa 1 (determinística) como
la garantía principal, describir la Capa 2 como "refuerzo por prompt (in-context)"
y presentar la Capa 3 como detección de rechazos + **validación de citas de
página** con evidencia auditable en logs (mostrar el `logger.warning` si el asesor
lo pide).
