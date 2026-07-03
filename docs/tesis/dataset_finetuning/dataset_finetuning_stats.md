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
