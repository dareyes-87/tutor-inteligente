# Dataset de fine-tuning del tutor pedagógico — estadísticas

Dataset para QLoRA/LoRA del objetivo específico 3 (tutor pedagógico open source vs. modelo
base). Generado localmente con el pipeline `backend/scripts/generar_dataset_finetuning.py`.
Formato: JSONL de Together AI (una línea por ejemplo, campo `messages` con roles
`system` / `user` / `assistant`).

## 1. Tamaño y división

| Archivo | Ejemplos | Proporción |
|---|---:|---:|
| `train.jsonl` | **506** | 89.9 % |
| `val.jsonl` | **57** | 10.1 % |
| **Total** | **563** | 100 % |

División **90/10 estratificada** por (asignatura × grado): ambos conjuntos conservan la
proporción de materias y grados (no hay materias/grados exclusivos de un solo split).

Validaciones automáticas: **0** ejemplos con formato inválido, **0** solapamiento
train∩val (sin fuga), **0** duplicados internos.

## 2. Composición del dataset

- **552 ejemplos sintéticos** generados con `meta-llama/Llama-3.3-70B-Instruct-Turbo`
  (preguntas + respuestas "ideales") + **3 casos de oro** hechos a mano (guía Socrática en
  matemáticas, notación ∈, rechazo fuera de contexto).
- **11 ejemplos reales limpios** extraídos de conversaciones reales del chat (con grounding
  válido, deduplicados y sin fugas de "plomería" del RAG).

El `system` de cada ejemplo es el mismo `build_system_prompt(grado, asignatura)` de
producción; el contexto recuperado (fragmentos del libro) va en el turno `user`, de modo
que las citas "(página X)" de la respuesta están respaldadas por texto visible (no se
entrena a citar páginas inventadas). El contenido específico lo aporta el RAG en inferencia;
el fine-tuning aprende el **comportamiento** (grounding estricto, guía Socrática en
matemáticas, adaptación de registro por grado, estilo vívido).

## 3. Balance por asignatura y grado

### Train (506)
| Grado | Ciencias Naturales | Matemáticas |
|---|---:|---:|
| 4to Primaria | 85 | 48 |
| 5to Primaria | 78 | 47 |
| 6to Primaria | 77 | 45 |
| 8vo Básico | 73 | 44 |
| 1ro Básico* | 6 | 3 |
| **Subtotal** | **319** | **187** |

### Validación (57)
| Grado | Ciencias Naturales | Matemáticas |
|---|---:|---:|
| 4to Primaria | 9 | 5 |
| 5to Primaria | 9 | 5 |
| 6to Primaria | 9 | 5 |
| 8vo Básico | 8 | 5 |
| 1ro Básico* | 1 | 1 |
| **Subtotal** | **36** | **21** |

Proporción global: Ciencias Naturales **63 %**, Matemáticas **37 %** (Matemáticas
sobre-representada respecto a su presencia natural en el corpus real, que era casi nula).

\* Los ejemplos de "1ro Básico" provienen de las conversaciones reales locales (el grado
etiquetado en la base de datos de desarrollo); los sintéticos usan etiquetas de grado
variadas (4to–6to Primaria, 8vo Básico).

## 4. Control de calidad — rechazos del juez (LLM-juez endurecido)

Durante la generación, cada respuesta sintética pasó por gates determinísticos (citas y
meta-frases del RAG) y un LLM-juez endurecido. Ejemplos rechazados por motivo (sobre
~680 candidatos crudos):

| Motivo | Rechazados |
|---|---:|
| Plano / robótico (correcto pero sin vida ni analogía memorable) | **114** |
| Analogía incoherente (no mapea al concepto) | **87** |
| Imprecisión conceptual (procedimiento engañoso aunque el resultado sea correcto) | **65** |
| Resultado directo en matemáticas (debía guiar paso a paso) | **4** |

Los gates determinísticos garantizan además **0 citas de página inventadas** y **0
meta-frases del RAG** ("fragmentos", "contexto proporcionado", etc.) en el dataset final.
Diversidad de estilo verificada: la analogía "mercado" aparece en **0 %** y la apertura
"¡Hola" en **0 %** del dataset (se corrigió una monotonía estilística detectada en una
versión previa).

## 5. Conteo de tokens (tokenizer Qwen2.5, exacto)

| Conjunto | Tokens |
|---|---:|
| Train | **706,197** |
| Validación | **80,798** |
| **Total** | **786,995** |

## 6. Hiperparámetros de fine-tuning (LoRA) — elegidos y justificación

**Modelo base:** `Qwen/Qwen2.5-7B-Instruct` (variante fine-tuneable; NO la de inferencia
`-Turbo`).

| Parámetro | Valor | Justificación |
|---|---|---|
| `n_epochs` | **3** | Pasadas suficientes para aprender comportamiento sin memorizar en un dataset de 506 ejemplos. El costo de Together (≤16B LoRA, $0.48/1M tokens) cae en el **mínimo de $4** para 1–~10 épocas, así que el número lo decide la curva de validation loss, no el presupuesto. Punto de partida conservador. |
| `lora_r` (rank) | **8** (default) | Capacidad suficiente para 506 ejemplos; no se sube a 16 en el primer intento para no combinar más capacidad con más pasadas (riesgo de sobreajuste). Subir solo si se observa underfit. |
| `lora_alpha` | **16** | Escala α/r = 2, práctica estándar de LoRA. |
| `lora_dropout` | **0.1** | Regularización ligera contra sobreajuste en dataset pequeño (default 0.0). |
| `learning_rate` | **1e-5** (default) | Valor estándar y seguro para LoRA. |

**Costo estimado del entrenamiento (3 épocas):** `(3 × 706,197) + (n_evals × 80,798)` ≈
2.36M tokens × $0.48/1M ≈ $1.13 → **se factura el mínimo de $4.00**.

**Criterio de decisión sobre las épocas (validation loss):**
- Si el val-loss baja de forma sostenida y sigue al train-loss (brecha pequeña) hasta la
  época 3 → el modelo aún aprende; se justifica una segunda corrida con 4–6 épocas.
- Si el val-loss toca un mínimo y luego **sube** mientras el train-loss sigue bajando
  (brecha creciente) → sobreajuste; el óptimo es la época del mínimo de val-loss.

## 7. Resultados del entrenamiento (job real)

- **Job ID:** `ft-0b6b58db-9271`
- **Modelo resultante (LoRA adapter):** `dhreyes03_8f57/Qwen2.5-7B-Instruct-tutor-pedagogico-51b293e9`
- **Estado:** completado · **duración total ≈ 10 min** (cola + entrenamiento).
- **Tokens facturables:** 714,293 · **Costo real:** **$4.00** (mínimo de Together; el cómputo por tokens daba ~$1.13).

**Curva de validation loss (eval por época):**

| Época | Step | Val loss | Δ vs. época anterior |
|---:|---:|---:|---:|
| 1 | 32 | 1.0850 | — |
| 2 | 64 | 1.0010 | −0.0840 |
| 3 | 96 | 0.9932 | −0.0078 |

**Lectura (regla de decisión aplicada):** el val-loss **decrece de forma monótona** en las 3
épocas (nunca sube) → **no hay señal de sobreajuste**; 3 épocas fue una elección segura. La
mejora marginal cae ~10× entre época 1→2 (−0.084) y 2→3 (−0.008), es decir **se alcanzó una
meseta** hacia la época 3. Conclusión: 3 épocas es un buen punto de parada; una segunda
corrida con 4–6 épocas rendiría mejoras marginales (y sigue costando el mínimo de $4), pero
la palanca de mayor impacto sería **más/mejor data**, no más épocas. (El train-loss por paso
no está en la API de eventos de Together; vive en el dashboard/W&B.)

## 8. Decisión de despliegue

El modelo fine-tuneado se entrenó y evaluó exitosamente (sección 7): la curva de
validation loss (1.0850 → 1.0010 → 0.9932 en 3 épocas) muestra aprendizaje sostenido
sin sobreajuste, con meseta hacia la época 3.

Para servir el modelo en producción, Together AI requiere un **endpoint dedicado**
sobre hardware **2× NVIDIA H100 80GB** a **$12.98/hora**, a diferencia del modelo base
`Qwen/Qwen2.5-7B-Instruct-Turbo`, que es **serverless** (facturación por token, sin
costo de infraestructura dedicada porque el modelo está compartido entre múltiples
clientes de Together AI).

El patrón de uso real del piloto —acceso abierto de estudiantes durante un mes
completo, sin horario ni días fijos, incluyendo el uso fuera del horario escolar
(7:00–12:30)— implica mantener el endpoint disponible de forma continua:

| Modalidad de disponibilidad | Cálculo | Costo mensual estimado |
|---|---|---|
| 24/7 (cobertura del uso real) | $12.98/h × 24 h × 30 días | **≈ $9,345/mes** |
| Solo horario escolar (5.5 h × 22 días hábiles) | $12.98/h × 5.5 h × 22 días | **≈ $1,571/mes** |

Ambas modalidades exceden el presupuesto del proyecto; además, la modalidad de horario
escolar no cubre el patrón de uso real (los estudiantes acceden mayormente fuera del
horario de clases).

**Decisión.** El modelo fine-tuneado se mantiene como **resultado evaluado del objetivo
específico 3** (comparación fine-tuned vs. base), documentado con datos reales de costo
de Together AI. El despliegue en producción para el piloto continúa sobre el **modelo
base serverless** (`Qwen/Qwen2.5-7B-Instruct-Turbo`), que no presenta esta limitación de
costo por estar compartido entre múltiples clientes de la plataforma. La comparación de
comportamiento entre ambos modelos se realiza en entorno de evaluación, no en
producción, evitando el costo de infraestructura dedicada.
