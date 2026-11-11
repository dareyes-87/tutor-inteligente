# Resultados — correcciones del jurado

Rama: `correcciones-jurado`. Entorno: Docker local (ChromaDB `chromadb/chroma:1.5.9`, colección `libros_texto`).

## Paso 1 — Diagnóstico de tokens (2026-11-10, sin costo)

Comando (dentro del contenedor backend):

```bash
docker compose exec backend python scripts/evaluacion/diagnostico_tokens.py
```

Fuente de los fragmentos: la ChromaDB local poblada (los mismos chunks que produjo
`process_pdf()` + `chunk_pages()` en la ingesta). Tokenizador: `get_model().tokenizer`
de `paraphrase-multilingual-MiniLM-L12-v2`; la ventana `max_seq_length` incluye los
tokens especiales ([CLS]/[SEP]).

| Dato | Valor |
|---|---|
| Libros indexados | 12 (4to–6to Primaria y 1ro–3ro Básico; Ciencias Naturales y Matemáticas) |
| Fragmentos | 8 882 |
| Caracteres por fragmento (media) | 693,0 |
| Tokens por fragmento — media | 121,2 |
| Tokens por fragmento — mediana | 114 |
| Tokens por fragmento — p90 | 216 |
| Tokens por fragmento — máximo | 317 |
| `max_seq_length` del modelo | 128 tokens |
| Fragmentos que superan 128 tokens | 3 504 (**39,45 %**) |
| Texto fuera del embedding, promedio sobre todos los fragmentos | **10,32 %** |
| Texto fuera del embedding, promedio sobre los fragmentos truncados | **26,17 %** |
| Dimensión del vector | 384 |
| `TOP_K` (`app/modules/rag/search.py`) | 5 |
| Distancia máxima `MAX_DISTANCE` | 1,55 (decisión de relevancia: `UMBRAL_ESTRICTO` 0,85 con ≥1 fragmento, o `UMBRAL_AMPLIO` 1,5 con ≥2) |
| Fragmentación (`chunking.py`) | `CHUNK_SIZE` = 800 caracteres, `CHUNK_OVERLAP` = 150 |

Lectura: el texto del fragmento sí se guarda completo y es el que recibe el LLM; lo
que se trunca es solo su **representación vectorial** (la que decide qué se recupera).
En 4 de cada 10 fragmentos, en promedio la última cuarta parte del texto no influye en la búsqueda.

## Paso 2 — Índice alternativo con ventana de 512 tokens (2026-11-10, sin costo)

Cambios de código (rama `correcciones-jurado`):

- `app/config.py`: `EMBEDDING_MODEL` (por defecto `paraphrase-multilingual-MiniLM-L12-v2`) y `CHROMA_COLLECTION` (por defecto `libros_texto`).
- `app/modules/ingesta/embeddings.py`: carga `EMBEDDING_MODEL`; si es un modelo e5 antepone `"passage: "` al indexar y `"query: "` al buscar (`generate_embeddings(..., es_consulta=True)` desde `rag/search.py`).
- `app/modules/ingesta/indexer.py`: la colección sale de `CHROMA_COLLECTION`.
- `CHUNK_SIZE = 800` y `CHUNK_OVERLAP = 150` sin cambios.

Indexación de los mismos 12 libros en una colección **nueva** `libros_texto_e5` (la colección `libros_texto` no se tocó), recalculando los embeddings desde la tabla `fragmento` de Postgres (mismos textos, ids y metadatos):

```bash
docker compose exec -e EMBEDDING_MODEL=intfloat/multilingual-e5-small -e CHROMA_COLLECTION=libros_texto_e5 \
    backend python scripts/reconstruir_chroma.py          # 8 882 vectores, 13 min 17 s en CPU
docker compose exec backend python scripts/evaluacion/diagnostico_tokens.py \
    --modelo intfloat/multilingual-e5-small --prefijo "passage: " --coleccion libros_texto_e5
```

| Dato (tokenizador de e5, con el prefijo `"passage: "`) | Valor |
|---|---|
| Modelo | `intfloat/multilingual-e5-small` |
| Ventana `max_seq_length` | 512 tokens |
| Dimensión | 384 |
| Fragmentos | 8 882 (12 libros) |
| Tokens por fragmento — media / mediana / p90 / máx. | 123,2 / 116 / 218 / 319 |
| Fragmentos que superan 512 tokens | **0 (0 %)** |
| Texto fuera del embedding | **0 %** |

### Recalibración de umbrales de distancia para e5

Las distancias de e5 (L2 al cuadrado sobre vectores normalizados, la métrica por defecto de ChromaDB) se concentran en ≈0,15–0,6, así que los umbrales de MiniLM no son comparables. Método: **equivalencia de percentiles**. Se juntaron las distancias top-5 de las 50 preguntas de evaluación y de 24 consultas fuera del libro (12 preguntas × 2 asignaturas de 4to; lista en `comparar_recuperacion.py`) en cada modelo; para cada umbral de MiniLM se calculó qué percentil de su distribución deja pasar, y se tomó el valor de e5 en ese mismo percentil. Luego se redondeó a 2 decimales y se verificó que las métricas no cambian.

| Umbral (`rag/search.py`) | MiniLM | Percentil | e5 (calculado) | e5 (en código) |
|---|---|---|---|---|
| `UMBRAL_ESTRICTO` (1 fragmento basta) | 0,85 | 48,65 % | 0,2941 | 0,29 |
| `UMBRAL_AMPLIO` (≥2 fragmentos) | 1,50 | 90,81 % | 0,4682 | 0,47 |
| `MAX_DISTANCE` (corte del contexto) | 1,55 | 93,51 % | 0,4870 | 0,49 |

## Paso 3 — Comparación de recuperación (2026-11-10, sin costo de LLM)

Búsqueda de producción (`search_fragments`, mismos filtros asignatura/grado, `TOP_K` = 5) sobre las 50 preguntas de `preguntas_ragas.json` (todas de 4to Primaria: 25 Ciencias Naturales, 25 Matemáticas; 20 conceptuales, 16 factuales, 14 procedimentales). Hit@5: al menos un fragmento devuelto (tras el corte `MAX_DISTANCE` de cada modelo) cae en `paginas_ref`. MRR: 1/rango del primero que cae.

```bash
docker compose exec backend python scripts/evaluacion/comparar_recuperacion.py volcar minilm
docker compose exec -e EMBEDDING_MODEL=intfloat/multilingual-e5-small -e CHROMA_COLLECTION=libros_texto_e5 \
    backend python scripts/evaluacion/comparar_recuperacion.py volcar e5
python backend/scripts/evaluacion/comparar_recuperacion.py analizar minilm e5   # → comparacion_minilm_vs_e5.json
```

| Grupo | n | Hit@5 MiniLM | Hit@5 e5 | MRR MiniLM | MRR e5 |
|---|---|---|---|---|---|
| **Global** | 50 | **0,960** | **1,000** | 0,884 | 0,898 |
| Ciencias Naturales | 25 | 1,000 | 1,000 | 0,908 | 0,873 |
| Matemáticas | 25 | 0,920 | 1,000 | 0,860 | 0,923 |
| Conceptual | 20 | 0,950 | 1,000 | 0,910 | 0,917 |
| Factual | 16 | 1,000 | 1,000 | 0,875 | 0,896 |
| Procedimental | 14 | 0,929 | 1,000 | 0,857 | 0,875 |

Otras cifras: con ambos modelos el 100 % de las 50 preguntas del libro pasa la decisión de relevancia (`is_context_relevant`). De las 24 consultas fuera del libro, MiniLM rechaza el 25,0 % y e5 el 29,2 %: ninguno de los dos filtra bien por distancia lo que no está en el libro (la segunda barrera es el prompt del LLM); se reporta como limitación. Con e5, el corte `MAX_DISTANCE` no cambia el Hit@5 ni el MRR (iguales sin corte).

**Decisión (regla fijada de antemano):** e5 iguala o supera a MiniLM en Hit@5 global (1,000 ≥ 0,960) → **se adopta `intfloat/multilingual-e5-small`**. No se corrió la variante MiniLM con `CHUNK_SIZE = 450`.

## Paso 4 — Respuestas de referencia (2026-11-10) — borradores, PENDIENTE revisión docente

1. Texto de las páginas: OCR de los PDFs de 4to Primaria (`LIBROS_OASIS_ESCANEADOS/4to Primaria/`, escaneados, sin capa de texto) con el mismo `process_pdf()` de producción (Tesseract `spa`, 300 dpi): 195 páginas de Ciencias Naturales y 81 de Matemáticas → `backend/scripts/evaluacion/paginas_4to_ocr.json`.
2. Borradores: `deepseek-ai/DeepSeek-V4.1-Flash` (temperatura 0,2), instrucción de responder en 2–4 oraciones para el grado usando **solo** el texto de `paginas_ref`, o `SIN INFORMACIÓN EN LAS PÁGINAS` si no alcanza.

```bash
docker compose exec backend python scripts/evaluacion/generar_referencias.py --max-usd 1
```

| Dato | Valor |
|---|---|
| Modelo de los borradores | `deepseek-ai/DeepSeek-V4.1-Flash` |
| Llamadas / tokens entrada / tokens salida | 50 / 201 097 / 16 629 |
| Costo real (Together) | **US$0,0803** |
| Borradores "sin información" | 2: Q8 «¿Qué son las bacterias?» (págs. 37–49: solo hablan de resistencia a antibióticos; la palabra "bacteria" aparece 11 veces en la pág. 53) y Q41 «¿Cuáles son las propiedades de la división?» (págs. 24–30) |

Salidas: `backend/scripts/evaluacion/referencias_ragas.json` y `referencias_para_revisar.csv` (columna vacía "corrección docente").

**Evaluador del paso 5:** `meta-llama/Llama-3.3-70B-Instruct-Turbo` ya no es serverless en Together (respuesta 400 "Unable to access non-serverless model", 2026-11-10). Se usará `openai/gpt-oss-120b`, que no es el generador del paso 5 (modelo ajustado en Modal) ni el autor de las referencias (DeepSeek).

## Alcance de la evaluación y rechazo de preguntas fuera del libro (2026-11-10)

**Alcance.** Las 50 preguntas de `preguntas_ragas.json` son todas de **4to Primaria**: 25 de Ciencias Naturales y 25 de Matemáticas (20 conceptuales, 16 factuales, 14 procedimentales). Hit@5, MRR y RAGAS miden por lo tanto la recuperación y las respuestas sobre esos dos libros. Los otros 10 libros indexados (5to y 6to Primaria, 1ro a 3ro Básico) entran en el diagnóstico de tokens del paso 1, pero no en la evaluación de recuperación ni de respuestas.

**Rechazo de preguntas fuera del libro.** 12 preguntas ajenas a los libros (fútbol, Python, inflación, capital de Francia, Don Quijote, ajedrez, bitcoin, baloncesto, diabetes, motor de automóvil, tamales, primer presidente de Guatemala), cada una consultada con el filtro de las dos asignaturas de 4to = 24 consultas (lista en `comparar_recuperacion.py`). Se mide con los dos mecanismos basados en distancia de `rag/search.py`:

- *Rechazada*: `is_context_relevant()` devuelve False, así que la pregunta no llega al LLM con contexto del libro.
- *Contexto vacío*: el corte `MAX_DISTANCE` descarta los 5 fragmentos.

| Índice | Grupo | Consultas | Rechazadas | Contexto vacío por `MAX_DISTANCE` | Fragmentos que pasan el corte (media) |
|---|---|---|---|---|---|
| MiniLM | Ciencias Naturales | 12 | 4 (33,3 %) | 0 (0,0 %) | 3,75 |
| MiniLM | Matemáticas | 12 | 2 (16,7 %) | 0 (0,0 %) | 4,25 |
| MiniLM | **Total** | 24 | **6 (25,0 %)** | **0 (0,0 %)** | 4,00 |
| e5 | Ciencias Naturales | 12 | 3 (25,0 %) | 1 (8,3 %) | 4,42 |
| e5 | Matemáticas | 12 | 4 (33,3 %) | 2 (16,7 %) | 3,75 |
| e5 | **Total** | 24 | **7 (29,2 %)** | **3 (12,5 %)** | 4,08 |

Para comparar, el 100 % de las 50 preguntas del libro pasa `is_context_relevant()` con los dos índices. Lectura: el corte por distancia está calibrado para no rechazar preguntas legítimas (un falso negativo es peor que un falso positivo, ver el docstring de `is_context_relevant`). Por eso solo filtra entre una cuarta parte y un tercio de las preguntas ajenas al libro. Para el resto, la barrera es el system prompt del tutor, que le exige responder solo con el contexto del libro. Se reporta como limitación.

## Paso 6 — Preparación (2026-11-10) — NO desplegado, pendiente de aprobación

- `backend/Dockerfile`: el `RUN` que precarga modelos ahora descarga `paraphrase-multilingual-MiniLM-L12-v2` **y** `intfloat/multilingual-e5-small` antes de `ENV HF_HUB_OFFLINE=1`.
- Verificado en local: `docker compose build backend` (la capa de descarga tardó 278 s) y luego `docker run --rm` de la imagen con `HF_HUB_OFFLINE=1`. Cargan los dos modelos sin red: MiniLM con ventana de 128 y e5 con 512, ambos de dimensión 384. La imagen pesa 4,45 GB.
- Plan de despliegue (cuando Daniel lo apruebe):
  1. Merge de `correcciones-jurado` → deploy en Railway (con las variables sin definir sigue funcionando con MiniLM / `libros_texto`: el cambio es inocuo).
  2. Reindexar en una colección NUEVA, sin borrar la actual: `EMBEDDING_MODEL=intfloat/multilingual-e5-small CHROMA_COLLECTION=libros_texto_e5 python scripts/reconstruir_chroma.py` dentro del servicio backend.
  3. Definir en Railway `EMBEDDING_MODEL=intfloat/multilingual-e5-small` y `CHROMA_COLLECTION=libros_texto_e5` y reiniciar.
  4. Rollback: borrar esas dos variables y reiniciar (la colección `libros_texto` sigue intacta).

### Paso 4 (cont.) — Corrección de `paginas_ref` y revisión de referencias (2026-11-10)

- **Q8 «¿Qué son las bacterias?»**: `37-49` → **`53`**. En las págs. 37–49 solo se habla de parásitos, enfermedades contagiosas y resistencia a antibióticos; la definición está en la pág. 53 («Dominio Bacteria»). Referencia regenerada (`generar_referencias.py --solo 8,41`, US$0,0014).
- **Q41 «¿Cuáles son las propiedades de la división?»**: `24-30` → **`27-29`**. El libro de Matemáticas 4to no presenta «propiedades de la división» (solo de la suma y la multiplicación, pág. 24). Las págs. 27–29 son las de división: términos, comprobación y ceros en el cociente. El modelo volvió a responder «sin información», así que la referencia se redacta a mano con ese contenido.
- Revisión de las 50 referencias contra el texto OCR de sus páginas, y contra la imagen del PDF donde el OCR perdió datos. Se marcaron 5 como dudosas en `referencias_para_revisar.csv`, cada una con una propuesta de corrección: Q12, Q14, Q16, Q34 y Q41.
- Hallazgo: en la tabla de vitaminas (pág. 34, Ciencias 4to) el OCR perdió las letras A, B, C, D, E y K. Ese texto es el que está indexado, así que el tutor tampoco puede recuperarlas. Es una limitación del OCR de tablas.

## Paso 5 — Generación de respuestas de producción (2026-11-10)

Modelo ajustado v1 en Modal (`tutor-finetuned`, Qwen2.5-7B + LoRA, vLLM, A10G) + RAG con el índice e5 (`libros_texto_e5`). El camino es el mismo que el del chat de producción (`recuperar_contexto` → `is_context_relevant` → `build_messages` → `chat_finetuned`), sin el respaldo a Together.

```bash
docker compose exec -e EMBEDDING_MODEL=intfloat/multilingual-e5-small -e CHROMA_COLLECTION=libros_texto_e5 \
    backend python scripts/evaluacion/generar_respuestas_produccion.py      # → respuestas_produccion_e5.json
```

| Dato | Valor |
|---|---|
| Respuestas OK / rechazadas / error | 50 / 0 / 0 |
| Fragmentos de contexto por pregunta | 5 en las 50 |
| Tiempo total | 554 s |
| Latencia por respuesta — mediana / máx. | 6,9 s / 200,8 s (la primera: arranque en frío, la app tenía 0 contenedores) |
| Uso de Modal | ≈ 9 min de A10G + 5 min de `scaledown_window` (saldo de noviembre: US$20) |

### Paso 4 (cierre) — Decisiones de la revisión docente (2026-11-10)

- Q12, Q14, Q16 y Q34: **se aceptaron las correcciones propuestas** (texto final en `referencias_ragas.json`, campo `corregida_por`).
- **Q41 se retira** del conjunto de evaluación: el libro de Matemáticas de 4to no desarrolla propiedades de la división, así que la pregunta no tiene respuesta de referencia en el libro. Se borró de `preguntas_ragas.json` y de `referencias_ragas.json`. **A partir de aquí n = 49** (25 Ciencias Naturales, 24 Matemáticas; 20 conceptuales, 15 factuales, 14 procedimentales).
- Las respuestas del v1 (`respuestas_produccion_e5.json`) no se modificaron. La respuesta a Q41 queda en el archivo, pero el evaluador la ignora.

## Paso 3 (repetición) — Hit@5 y MRR con `paginas_ref` corregidos, n = 49 (2026-11-10)

Mismos comandos que en el paso 3. Cambios respecto de la primera corrida: Q8 → pág. 53 y Q41 retirada. Los umbrales de e5 se mantienen fijos en los valores del código (0,29 / 0,47 / 0,49). Como control, recalibrar con las 49 preguntas da 0,2931 / 0,4682 / 0,4870, prácticamente lo mismo.

| Grupo | n | Hit@5 MiniLM | Hit@5 e5 | MRR MiniLM | MRR e5 |
|---|---|---|---|---|---|
| **Global** | 49 | **0,959** | **1,000** | 0,898 | 0,923 |
| Ciencias Naturales | 25 | 1,000 | 1,000 | 0,940 | 0,900 |
| Matemáticas | 24 | 0,917 | 1,000 | 0,854 | 0,948 |
| Conceptual | 20 | 0,950 | 1,000 | 0,950 | 0,950 |
| Factual | 15 | 1,000 | 1,000 | 0,867 | 0,933 |
| Procedimental | 14 | 0,929 | 1,000 | 0,857 | 0,875 |

Preguntas del libro aceptadas por `is_context_relevant()`: 100 % con los dos índices. Consultas fuera del libro rechazadas: MiniLM 25,0 %, e5 29,2 % (sin cambios). **La decisión se mantiene: se adopta e5.** Estas cifras reemplazan a las de la primera corrida del paso 3.

## Prueba funcional con e5 en el backend local (2026-11-10)

Segunda instancia de uvicorn dentro del contenedor (puerto 8001, sin publicar) con `EMBEDDING_MODEL=intfloat/multilingual-e5-small` y `CHROMA_COLLECTION=libros_texto_e5`. El backend normal del puerto 8000 no se tocó. Script: `backend/scripts/debug/prueba_e5_leccion_actividades.py`. Usa un estudiante temporal de 4to Primaria creado vía admin y desactivado al terminar. No se desplegó nada.

Lección 179 «El Cuerpo Humano» (Ciencias Naturales 4to, págs. 13–17), nivel 1:

| Llamada | Resultado | Tiempo |
|---|---|---|
| `GET /lecciones/179/micro-leccion?nivel=1` | 200 — 10 tarjetas, 5 `fragment_ids` | 5,2 s |
| `POST /actividades/generar` opción múltiple (con `fragment_ids`) | 200 | 0,6 s |
| verdadero/falso (con `fragment_ids`) | 200 | 0,9 s |
| completar (con `fragment_ids`) | 200 | 0,7 s |
| ordenar (con `fragment_ids`) | 200 | 4,5 s |
| respuesta corta (con `fragment_ids`) | 200 | 0,6 s |
| opción múltiple **sin lección** (búsqueda semántica con e5, grounding estricto) | 200 — `best_dist=0.271`, relevante (< `UMBRAL_ESTRICTO` 0,29) | 0,8 s |

Lectura: la micro-lección y las actividades con lección recuperan **por rango de páginas** (Postgres), no por embeddings, así que el cambio de modelo no las afecta. Las que dependen de e5 son el chat y las actividades sin lección; las dos funcionan con los umbrales recalibrados. Modelo LLM de micro-lección y actividades: `deepseek-ai/DeepSeek-V4.1-Flash` (Together).

## Paso 5 — RAGAS con 4 métricas, 3 corridas (2026-11-10)

- **Configuración evaluada:** chat de producción = modelo ajustado v1 en Modal (Qwen2.5-7B + LoRA, vLLM, A10G) + RAG con el índice e5 (`libros_texto_e5`, `TOP_K` = 5). Respuestas: `respuestas_produccion_e5.json` (generadas una sola vez; las 3 corridas evalúan las mismas respuestas, así que la variación es solo del evaluador).
- **n = 49** (Q41 retirada). Referencias: `referencias_ragas.json`, con la revisión docente.
- **Evaluador:** `openai/gpt-oss-120b` (Together), `reasoning_effort="low"`. Llama-3.3-70B-Instruct-Turbo ya no es serverless.
- **Embeddings de las métricas** (Answer Relevancy y la parte semántica de Answer Correctness): `intfloat/multilingual-e5-small` local, prefijo `"query: "`.
- **Métricas:** `Faithfulness`, `ResponseRelevancy`, `LLMContextPrecisionWithReference`, `AnswerCorrectness`.
- **Versión:** ragas 0.4.3 (Python 3.14, venv aparte; `langchain-community` fijado en 0.3.31 porque la 0.4 quitó un módulo que ragas importa).

```bash
TOGETHER_API_KEY=… python backend/scripts/evaluacion/evaluar_ragas_4metricas.py --max-usd 0.33 \
    --salida backend/scripts/evaluacion/ragas_2026-11_produccion_e5/corrida_N      # N = 1, 2, 3
python backend/scripts/evaluacion/resumir_corridas_ragas.py backend/scripts/evaluacion/ragas_2026-11_produccion_e5/corrida_{1,2,3}
```

Media ± desviación estándar entre las 3 corridas:

| Grupo | n | Faithfulness | Answer Relevancy | Context Precision (ref.) | Answer Correctness |
|---|---|---|---|---|---|
| **Global** | 49 | **0,804 ± 0,014** | **0,894 ± 0,003** | **0,824 ± 0,004** | **0,611 ± 0,005** |
| Ciencias Naturales | 25 | 0,858 ± 0,027 | 0,895 ± 0,005 | 0,737 ± 0,010 | 0,620 ± 0,012 |
| Matemáticas | 24 | 0,748 ± 0,008 | 0,894 ± 0,000 | 0,914 ± 0,004 | 0,601 ± 0,008 |
| Conceptual | 20 | 0,806 ± 0,028 | 0,897 ± 0,002 | 0,843 ± 0,010 | 0,624 ± 0,010 |
| Factual | 15 | 0,782 ± 0,027 | 0,871 ± 0,007 | 0,785 ± 0,001 | 0,592 ± 0,003 |
| Procedimental | 14 | 0,826 ± 0,015 | 0,916 ± 0,002 | 0,837 ± 0,000 | 0,611 ± 0,030 |

- **Umbral de fidelidad 0,80:** la media global (0,804) queda justo en el umbral. Ciencias Naturales lo supera (0,858) y Matemáticas no (0,748). Por pregunta, 32, 31 y 31 de las 49 alcanzan ≥ 0,80 en las corridas 1, 2 y 3.
- **Fidelidad más baja** (media de las 3 corridas): suma y resta de fracciones con igual denominador (0,22), niveles de organización del cuerpo humano (0,40), media aritmética y moda (0,40), potencia (0,44), multiplicación y sus propiedades (0,54), vitaminas (0,56). Q8 «bacterias»: 0,857 en las 3 corridas; la respuesta agrega «desde antes de los dinosaurios», que no está en la pág. 53.
- **Métricas que el evaluador no pudo puntuar (NaN):** 0 en las 3 corridas.
- **Costo real (Together, gpt-oss-120b):** US$0,2405 + 0,2326 + 0,2324 = **US$0,7055**.
- **Comparabilidad:** la fidelidad que reporta la tesis para la configuración C (v1 + RAG, 0,8476) se midió con otro evaluador (Llama-3.3-70B), otro índice (MiniLM) y n = 50. Esta cifra no es directamente comparable con aquella: cambian a la vez el evaluador, el índice y las referencias.

## Costos acumulados de las correcciones (hasta 2026-11-10)

| Concepto | Proveedor | US$ |
|---|---|---|
| Borradores de referencias (50) + regeneración Q8/Q41 | Together (DeepSeek-V4.1-Flash) | 0,0816 |
| Pruebas del evaluador (2 corridas de humo, 2 preguntas) | Together (gpt-oss-120b) | 0,0158 |
| RAGAS 4 métricas × 3 corridas | Together (gpt-oss-120b) | 0,7055 |
| Prueba de micro-lección + actividades con e5 (2 corridas) | Together (DeepSeek-V4.1-Flash) | < 0,01 (no instrumentado; 16 llamadas cortas) |
| Preguntas para otros grados (30) | Together (DeepSeek-V4.1-Flash) | 0,0407 |
| **Total Together** | | **≈ 0,85** (tope del encargo: 5) |
| Generación de 50 respuestas v1 | Modal (A10G) | ≈ 9 min de GPU + 5 min de `scaledown_window` (saldo de noviembre: US$20) |

## Paso 3b — Preguntas de recuperación para los demás grados (2026-11-10) — PENDIENTE revisión docente

```bash
docker compose exec backend python scripts/evaluacion/generar_preguntas_otros_grados.py --max-usd 0.5
```

- **Libros:** los 10 de 5to y 6to Primaria y de 1ro a 3ro Básico, Matemáticas y Ciencias Naturales (libro_id 5–14; en la BD local los grados de básico se llaman 7mo, 8vo y 9no Básico). 3 preguntas por libro, una de cada tipo: 30 en total.
- **Texto de las páginas:** reconstruido desde la tabla `fragmento` (el mismo OCR indexado), quitando el solapamiento entre chunks.
- **Páginas elegibles:** número de página > 5 (portada, créditos e índice), ≥ 700 caracteres, sin pinta de índice (≤ 40 % de líneas que terminan en número) y con más de la mitad de sus fragmentos clasificados como teoría por `es_ejercicio_del_libro`.
- **Sorteo:** `random.Random(20261110).sample(elegibles, 3)` por libro, en orden de `libro_id`. **Semilla: 20261110.**
- **Redacción:** `deepseek-ai/DeepSeek-V4.1-Flash` (temperatura 0,7; no es gpt-oss-120b), como estudiante del grado, sin copiar frases ni títulos (máximo 3 palabras seguidas iguales). El modelo indica si el tema sigue en la página siguiente; en ese caso `paginas_ref` = «p-(p+1)».
- **Control de copia:** se mide el solapamiento literal con las páginas (máximo de palabras seguidas iguales). 28 preguntas tienen ≤ 3 y 2 tienen 4 (la nº 20 y la nº 23 del CSV).
- **Costo:** 30 llamadas, US$0,0407.
- **Salidas:** `preguntas_recuperacion_otros_grados.csv` (columna «revisión docente») y `preguntas_recuperacion_otros_grados.json`.

### Paso 3b (cont.) — Reemplazo de 6 preguntas que no venían de páginas de teoría (2026-11-10) — aprobadas por el docente

Las preguntas nº 2, 8, 17, 18, 24 y 29 salían de páginas de problema resuelto, de cuadro para llenar o de actividad o proyecto, que el filtro automático no detectó. Para cada una se eligió una página nueva del mismo libro (mismo grado y asignatura) y del mismo tipo de pregunta:

1. Orden aleatorio de las páginas elegibles del libro que aún no se habían usado: `random.Random(f"20261110:{libro_id}").sample(...)` (misma semilla base).
2. Se leyeron las páginas en ese orden y se tomó la primera que fuera **teoría**: definición o explicación, no un problema resuelto, un cuadro para llenar ni una actividad.
3. Pregunta nueva con el mismo modelo y las mismas reglas: `generar_preguntas_otros_grados.py --reemplazar n:página`.

| nº | Libro | Tipo | Página anterior (motivo) | Descartadas en el orden de la semilla | Página nueva | Pregunta nueva | Solap. |
|---|---|---|---|---|---|---|---|
| 2 | Matemáticas 5to | factual | p58, problema «baño uno» | — | p39 (clasificación de triángulos y cuadriláteros) | ¿Cómo se llaman los triángulos que tienen todos sus lados iguales, dos iguales y ninguno igual? | 2 |
| 8 | Matemáticas 6to | factual | p83, problema de cambio de moneda | p74 (la regla de volumen mezclada con problemas resueltos; las 2 preguntas generadas salieron de los ejemplos) | p35–36 (polígonos y cuadriláteros) | ¿Cómo se le llama a una figura cerrada de cuatro lados? | 3 |
| 17 | Ciencias 1ro Básico | factual | p242, logística de un festival | p91, p146 (actividades) | p68–69 («¿Qué necesitamos saber?»: drogas) | ¿Qué efectos suelen causar la marihuana, la cocaína y la heroína? | 2 |
| 18 | Ciencias 1ro Básico | procedimental | p207, cuadro para llenar | — (siguiente en el orden) | p194–195 (MRU y MRUV) | ¿Cómo puedo calcular la aceleración de algo que va en línea recta si sé su velocidad al empezar, su velocidad al final y el tiempo que pasó? | 3 |
| 24 | Ciencias 2do Básico | procedimental | p272, armar el periódico (proyecto) | p108 (lectura de artículos), p81 (FODA del proyecto) | p255–256 (requisitos de los instrumentos y análisis de datos) | ¿Cómo se analizan los datos después de recogerlos en una investigación? | 3 |
| 29 | Ciencias 3ro Básico | factual | p106, pregunta sobre «los cuadros» | — | p67 (reglas de seguridad en el laboratorio) | ¿Qué cosas no se deben hacer nunca dentro del laboratorio? | 2 |

Costo de los reemplazos: US$0,0114 (8 llamadas: 6 + 2 regeneraciones de la nº 8). La columna «reemplazo» del CSV guarda la pregunta y la página anteriores.

**Revisión docente (2026-11-10):** las 6 preguntas reemplazadas quedan aprobadas; el set final es de 30 preguntas.

### Paso 3b (cont.) — Hit@5 y MRR por grado y asignatura, MiniLM vs e5 (2026-11-10, n = 30)

Mismo procedimiento que el paso 3: búsqueda de producción (`search_fragments`, filtros de asignatura y grado, TOP_K = 5) con cada índice. Umbrales de producción de cada modelo (MiniLM 0,85/1,5/1,55; e5 0,29/0,47/0,49, sin recalibrar).

```bash
F=scripts/evaluacion/preguntas_recuperacion_otros_grados.json
docker compose exec backend python scripts/evaluacion/comparar_recuperacion.py volcar minilm_3b $F
docker compose exec -e EMBEDDING_MODEL=intfloat/multilingual-e5-small -e CHROMA_COLLECTION=libros_texto_e5 \
    backend python scripts/evaluacion/comparar_recuperacion.py volcar e5_3b $F
python backend/scripts/evaluacion/comparar_recuperacion.py analizar minilm_3b e5_3b
```

Salidas: `recuperacion_minilm_3b.json`, `recuperacion_e5_3b.json`, `comparacion_minilm_3b_vs_e5_3b.json`.

| Grupo | n | Hit@5 MiniLM | Hit@5 e5 | MRR MiniLM | MRR e5 |
|---|---|---|---|---|---|
| **Global** | 30 | 0,733 | **0,967** | 0,597 | **0,791** |
| Matemáticas | 15 | 0,733 | 1,000 | 0,506 | 0,782 |
| Ciencias Naturales | 15 | 0,733 | 0,933 | 0,689 | 0,800 |
| Conceptual | 10 | 0,400 | 0,900 | 0,325 | 0,687 |
| Factual | 10 | 1,000 | 1,000 | 0,717 | 0,870 |
| Procedimental | 10 | 0,800 | 1,000 | 0,750 | 0,817 |
| 5to Primaria | 6 | 0,833 | 1,000 | 0,667 | 0,650 |
| 6to Primaria | 6 | 0,667 | 1,000 | 0,472 | 0,917 |
| 1ro Básico | 6 | 1,000 | 1,000 | 0,875 | 0,889 |
| 2do Básico | 6 | 0,500 | 0,833 | 0,417 | 0,722 |
| 3ro Básico | 6 | 0,667 | 1,000 | 0,556 | 0,778 |

Por grado y asignatura (n = 3 cada celda; solo descriptivo):

| Grado | Asignatura | Hit@5 MiniLM | Hit@5 e5 | MRR MiniLM | MRR e5 |
|---|---|---|---|---|---|
| 5to Primaria | Matemáticas | 0,667 | 1,000 | 0,333 | 0,300 |
| 5to Primaria | Ciencias Naturales | 1,000 | 1,000 | 1,000 | 1,000 |
| 6to Primaria | Matemáticas | 0,667 | 1,000 | 0,500 | 0,833 |
| 6to Primaria | Ciencias Naturales | 0,667 | 1,000 | 0,444 | 1,000 |
| 1ro Básico | Matemáticas | 1,000 | 1,000 | 0,750 | 1,000 |
| 1ro Básico | Ciencias Naturales | 1,000 | 1,000 | 1,000 | 0,778 |
| 2do Básico | Matemáticas | 0,667 | 1,000 | 0,500 | 1,000 |
| 2do Básico | Ciencias Naturales | 0,333 | 0,667 | 0,333 | 0,444 |
| 3ro Básico | Matemáticas | 0,667 | 1,000 | 0,444 | 0,778 |
| 3ro Básico | Ciencias Naturales | 0,667 | 1,000 | 0,667 | 0,778 |

- **Fallos:** MiniLM falla 8 de 30 (nº 1, 7, 10, 19, 22, 24, 27, 28; 6 de ellas conceptuales). e5 falla 1: la nº 22 (Ciencias 2do Básico, botiquín, ref. p83), cuyo top-5 son p78–79 y p138; MiniLM también la falla.
- **Aceptación:** con ambos índices, las 30 preguntas pasan `is_context_relevant` (100 %), y el corte `MAX_DISTANCE` de e5 no elimina ningún acierto (Hit@5 sin corte = 0,967).
- **Comparación con 4to (n = 49):** la ventaja de e5 es mayor fuera de 4to (+0,233 en Hit@5 y +0,194 en MRR, frente a +0,041 y +0,025 en 4to). Los libros de 5to a 3ro Básico tienen más fragmentos largos que MiniLM trunca a 128 tokens. Esto es coherente con el diagnóstico del paso 1, aunque no se midió por libro.
- **Limitación:** con n = 3 por celda, las diferencias por grado y asignatura no tienen valor estadístico; la conclusión se apoya en el global y en el sentido consistente de la mejora: e5 es igual o mejor en Hit@5 en las 10 celdas.
