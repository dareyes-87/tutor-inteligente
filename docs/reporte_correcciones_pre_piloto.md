# Reporte de Correcciones Pre-Piloto

## Fecha: 2026-07-29 / 2026-07-30
## Rama: `fix/pre-piloto`, mergeada y pusheada a `origin/main` (commits `081758a` y `bd8d252`)
## Entorno de prueba: LOCAL (docker compose) + lectura de solo-consulta contra producción para extraer contenido real y medir tiempos

## ⚠️ Incidente post-deploy (resuelto)

El push de `081758a` tumbó producción (`502 Application failed to respond`) durante unos minutos: Daniel ya tenía `MODAL_KEEPWARM_ENABLED`, `MODAL_KEEPWARM_HORA_INICIO`/`HORA_FIN` creadas en Railway pero **vacías**, y los campos nuevos en `config.py` las tipaban como `bool`/`int` — pydantic-settings no acepta `""` para esos tipos y lanza `ValidationError` al instanciar `Settings()` (que corre a nivel de módulo), tumbando toda la app. Hotfix en `bd8d252`: los 5 campos `MODAL_KEEPWARM_*` pasan a `str` (mismo patrón que `MODAL_FINETUNED_GRADOS`), parseados a mano con fallback al default ante vacío/inválido. Reproducido el crash exacto localmente, confirmado que ya no ocurre, y verificado en producción tras el segundo deploy: `/health` → 200, chat real de un estudiante → 200 con el footer de página incluido. **Lección para el futuro:** si se agregan variables de entorno nuevas a `config.py`, revisar primero si Railway ya tiene esa variable creada (aunque sea de un experimento anterior) antes de tipar como `bool`/`int` — mejor usar `str` + parseo manual como patrón por defecto en este proyecto.

---

## 11. Bug encontrado en producción: footer de página duplicado en conversaciones de varios turnos (2026-07-30)

Con el A/B ya ampliado a todos los grados, Daniel probó varias preguntas reales en producción y encontró que 3 de 5 respuestas mostraban el footer de la Prioridad 3 **duplicado**, con rangos de página ligeramente distintos entre las dos líneas. Una (de un solo turno) salió bien.

### 11.1 Diagnóstico (descarté las dos hipótesis originales con evidencia)

**No es el modelo fine-tuned citando por su cuenta.** Reproduje el mismo problema, exacto, con **Together AI** (estudiante que no es de la cohorte fine-tuned), en una conversación de 3 turnos:
```
Turno 3 (Together):
"...Así, las plantas pueden crecer y ayudarnos a respirar. 🌱🌞

📖 Basado en tu libro de Ciencias Naturales, página 62.         ← generado por el modelo, imitando
📖 Basado en tu libro de Ciencias Naturales, páginas 60-63, 70." ← nuestro footer determinístico real
```

**No es un doble-append en el código.** Solo hay un punto de inserción (`chat/service.py`, confirmado por grep y lectura completa); una pregunta aislada (primer turno de cualquier conversación) nunca lo duplica — coincide con que el caso de "latitud" que salió bien era, según Daniel, la única de un solo turno.

**Causa real: el historial de conversación le enseña el patrón al modelo, dentro de la misma sesión.** `obtener_historial()` lee de Postgres los mensajes previos —incluido el footer que ya quedó guardado en `contenido` del turno anterior— y se los pasa de vuelta al LLM en `build_messages()`. El modelo, viendo su propio turno anterior terminar en "📖 Basado en tu libro de...", imita esa frase en el turno siguiente (con una página que él infiere, no necesariamente la del footer real), y luego nuestro código agrega el footer real con los fragmentos de esa consulta — de ahí las dos líneas casi idénticas. Esto **no depende del proveedor del modelo** (pasa igual con Together que con Modal): es un efecto de in-context learning genérico, no algo aprendido en el fine-tuning (el dataset de 563 ejemplos es de antes de que existiera este footer).

Reproducido en producción (conversación real, estudiante `layala`, 3 turnos sobre estrellas/constelaciones) y en local (estudiante `carlos`, 3 turnos sobre fotosíntesis, Together) — mismo patrón en ambos.

### 11.2 Corrección aplicada

Un solo cambio, en `chat/service.py`:
- `_sin_footer_pagina(contenido)` (nueva): corta el texto desde el marcador fijo `"\n\n📖 Basado en tu libro de "` (que solo nuestro código genera, nunca aparece en input del usuario ni en el libro).
- `obtener_historial()`: a los mensajes de rol `asistente` se les aplica `_sin_footer_pagina()` antes de incluirlos en el historial que se le pasa al LLM.

El footer sigue guardándose completo en `Mensaje.contenido` (el estudiante lo sigue viendo al reabrir la conversación) — solo se le oculta al LLM en su propio historial, que es la fuente de la imitación.

### 11.3 Pruebas en LOCAL

Reproduje el escenario que falló en producción (fotosíntesis, 3 turnos, Together — el bug no es específico de Modal, así que no hacía falta gastar en una llamada a Modal para esta verificación):

| Turno | Footer (conteo de "📖") |
|---|---|
| 1 (pregunta inicial) | 1 — correcto |
| 2 ("Cuéntame más sobre eso") | 0 — el contexto de esa pregunta vaga no pasó el chequeo de citas válidas, footer vacío (comportamiento esperado, no relacionado con este bug) |
| 3 ("¿Y qué necesitan las plantas para hacerla?") | **1 — ya NO se duplica** |

Sin regresión en los otros dos casos ya verificados esta semana:
- **Pregunta fuera de contexto:** `referencias: []`, sin footer — igual que antes.
- **Pregunta por página específica** ("Explícame la página 62"): footer singular ("página 62") — igual que antes.

### 11.4 Archivos modificados

```
backend/app/modules/chat/service.py   (+~20 líneas: _sin_footer_pagina() + uso en obtener_historial())
```
No se tocó `ingesta/`, `chunking.py`, `embeddings.py`, `indexer.py`, modelos, migraciones, ni `actividades/validator.py`/`evaluator.py`.

### 11.5 Estado: listo en LOCAL, esperando confirmación para push

No hice push — queda en el working directory local (rama `main`, ya que el push anterior fue directo a `main`), esperando que Daniel confirme el momento.

---

## 1. Qué se aplicó y qué quedó pendiente

| Prioridad | Estado | Resumen |
|---|---|---|
| 1 — Cold start de Modal | ✅ **Revisada: se mantiene el A/B con keep-warm** | Decisión final revertida: en vez de Opción B, se mantiene el fine-tuned activo en producción con un mecanismo de keep-warm (ping cada 3 min) durante una ventana horaria y de fechas acotada por presupuesto. Implementado y verificado — ver sección 9. `MODAL_FINETUNED_GRADOS` NO se toca (sigue en `3`). |
| 2 — Prompt anti-alucinación | ✅ **Aplicada y verificada** | 5 reglas nuevas en `chat/prompts.py`. Mejora medible en Caso A. Caso B persiste (causa raíz es OCR, no el prompt — ver sección 6). |
| 3 — Referencia de página siempre visible | ✅ **Aplicada y verificada** | Lógica determinística en `chat/service.py`, no depende del LLM. Verificada en 3 escenarios reales (pregunta normal, rechazo, pregunta por página). |
| 4 — Filtro de recuadros decorativos | ❌ **Omitida a propósito** | Medí el impacto de los 9 marcadores candidatos sobre el corpus real (577 fragmentos de producción) y encontré que **todos** aparecen incrustados dentro de teoría legítima, no como recuadros aislados. Agregarlos habría cortado contenido real (Sol, Mendel, Copérnico, célula vegetal, sistema excretor). Daniel confirmó omitirla. |

---

## 2. Archivos modificados (exactos)

```
backend/app/modules/chat/prompts.py    (+5 líneas: reglas 12-16, anti-alucinación)
backend/app/modules/chat/service.py    (+38 líneas: referencia de página determinística)
```

Archivo nuevo (temporal, de prueba, no toca producción):
```
backend/scripts/debug/probar_prompt_antialucinacion.py
```

**No se tocó:** `ingesta/` (ningún archivo), `chunking.py`, `embeddings.py`, `indexer.py`, modelos de datos, migraciones Alembic, `actividades/validator.py`, `actividades/evaluator.py`, `rag/search.py` (Prioridad 4 omitida). No se re-indexó ni re-fragmentó ningún libro, ni en local ni en producción.

---

## 3. Casos de prueba: ANTES vs. DESPUÉS

Metodología: extraje el texto **real** de producción (páginas 83, 161, 36-37 del libro "Ciencias Naturales 6to", vía `GET /chat/debug/fragmentos/3`, solo lectura) porque el libro de 6to no existe indexado en local. Con ese contenido armé el mismo `system_prompt` + contexto que usaría el chat real, y llamé a Together AI directamente (mismo modelo base, sin pasar por Modal/RAG) alternando entre el prompt viejo (`git stash`) y el nuevo. Esto aísla el efecto del prompt.

### Caso A — página 83 (sistemas de la planta)

**ANTES:**
> Claro, te explicaré lo que dice la página 83.
>
> Las plantas tienen un tejido similar al dermis de los animales, pero se llama dermis vegetal. Este tejido protege a las plantas, como los tallos, hojas y raíces. También ayuda a que las plantas respiren y detecten a posibles enemigos que las puedan hacer enfermas.
>
> Este tejido vegetal tiene dos partes: la epidermis y la peridermis. La epidermis es una capa que cubre la planta cuando está creciendo. La peridermis aparece durante el crecimiento de la planta y reemplaza a la epidermis. **La peridermis ayuda a que la planta pueda crecer más grande.**
>
> Además, el tejido vegetal ayuda a transportar nutrientes...
>
> **Es importante mencionar que una parte del Objetivo de Desarrollo Sostenible es "Hambre cero"**, que busca asegurar que todas las personas tengan suficiente comida. Este objetivo está relacionado con cómo cuidamos la naturaleza y las plantas, porque las plantas son muy importantes para alimentarnos.
>
> ¿Tienes alguna pregunta sobre lo que acabo de explicar?

**DESPUÉS:**
> Claro, te explicaré sobre la página 83 del libro.
>
> En la página 83, hablan sobre el tejido dermis en las plantas. Este tejido, que en los animales es el epidermis, cubre las partes de la planta como tallos, hojas y raíces. Ayuda a proteger la planta y permite la respiración. También reconoce los organismos que causan enfermedades, como los hongos.
>
> El tejido dermis tiene dos capas: la epidermis, que cubre la planta en sus primeras etapas de crecimiento, y la peridermis, que aparece durante el crecimiento secundario y reemplaza a la epidermis. La peridermis permite la formación de corteza.
>
> Además, explica que el sistema vascular de las plantas es como un sistema de transporte. Este sistema lleva agua, minerales y nutrientes de las hojas y tallos verdes, donde se producen gracias a la fotosíntesis, hasta todas las partes de la planta, especialmente las raíces y el tallo.

**Veredicto: MEJORÓ.** Ya no agrega el mecanismo inventado ("ayuda a crecer más grande") ni cierra con el recuadro decorativo del ODS "Hambre cero". La regla 16 (no usar recuadros/rótulos como cierre) funcionó.

---

### Caso B — página 161 (las nubes)

**ANTES:**
> ...3. **Nubes bajas**: Son las más bajas en el cielo... Su nombre es **estratocúmulos**. Si ves estas nubes, **es un aviso de que puede llover**.

**DESPUÉS (corrida 1):**
> 3. **Nubes bajas**: ... - **Nimbostratos**: Forman una capa gruesa y anuncian lluvia. - **Estratocúmulos**: Son bancos gruesos que **pueden anunciar lluvia**.

**DESPUÉS (corrida 2, repetición para descartar ruido de muestreo):**
> Nubes bajas: - Altostratos: ...Anuncian lluvias. - Nimbostratos: ...Indican lluvia intensa. - **Estratocúmulos**: bancos de nubes de color gris. **Indican lluvia**.

**DESPUÉS (corrida 3):**
> 3. Nubes bajas: Son las que están más cerca del suelo... Anuncian lluvia y un cambio en el clima.

**Veredicto: NO SE RESOLVIÓ.** Confirmé el error en 3 corridas independientes (no es ruido de `temperature=0.7`, es consistente). **La causa raíz no es el prompt, es el OCR**: el texto real de producción para la tabla de nubes es:

```
cirros cirrocúmulos cirrostratos altocúmulos altostratos nimbostratos estratocúmulos estratos
Blancas y transparentes... Bancos de neblina. Pre-...con sombras. Anuncian...sagian...Avisan...
```

El OCR de esta tabla perdió la correspondencia nombre↔descripción (columnas desordenadas). Ninguna instrucción de "no inventes" puede reconstruir una relación que ya no está en el texto. Esto es un problema de `pdf_processor.py` (fuera de alcance esta semana, confirmado con Daniel). **Riesgo residual conocido y aceptado** — ver sección 6.

---

### Caso C — sistema excretor

**ANTES (esta corrida local):**
> 6. **El uréter**: Es un tubo que lleva la orina **desde los riñones hasta la vejiga**. [dirección correcta en esta muestra]

**DESPUÉS:**
> 3. **Uréter**: Es un tubo que lleva la orina **desde cada riñón hasta la vejiga**. [correcto, sin datos inventados adicionales]

**Veredicto: SIN REGRESIÓN, pero no pude reproducir el error original** (dirección invertida "conecta la vejiga con la uretra") ni con el prompt viejo ni con el nuevo en mis pruebas — salió correcto en ambas. Es probable que la muestra original de producción haya sido una salida particular del modelo (no determinista). No hay evidencia de que el prompt nuevo empeore ni garantice este caso puntual, pero tampoco hay regresión.

---

## 4. Prioridad 3 — verificación end-to-end (local, libro real indexado)

Probé contra el backend local real (estudiante `carlos`, libro "Ciencias Naturales 4to Primaria" indexado localmente), los 3 escenarios que pide el diseño:

**Pregunta normal** (fotosíntesis) → la respuesta terminó con:
```
📖 Basado en tu libro de Ciencias Naturales, páginas 60, 62, 94, 167, 195.
```
(lista, no rango, porque las páginas no son consecutivas — formato correcto)

**Pregunta fuera de contexto** (capital de Francia) → `referencias: []`, **sin** footer agregado (correcto, no se agrega referencia cuando no hay grounding).

**Pregunta por página específica** ("Explícame la página 62") → footer en singular:
```
📖 Basado en tu libro de Ciencias Naturales, página 62.
```

Confirmé además con un sub-agente que tanto el chat web (`react-markdown`, trata `\n\n` como salto de párrafo) como el móvil (`<Text>` nativo, trata `\n` como salto de línea) van a mostrar el emoji y el salto de línea sin necesidad de tocar ningún código de frontend.

---

## 5. Tiempos de respuesta medidos (producción, hoy)

| Escenario | Tiempo |
|---|---|
| Modal **frío** (contenedor dormido, estudiante de 6to) | **195.1 s** |
| Modal **caliente** (misma pregunta, inmediatamente después) | **2.4 s** |
| Together AI directo (estudiante que no es de 6to, mismo tipo de pregunta) | **0.9 s – 11 s** según la pregunta |

195s confirma la violación del RNF de 15s — de ahí la decisión de Daniel (Prioridad 1, Opción B).

---

## 6. Conteo de fragmentos filtrados (Prioridad 4)

No se agregó ningún marcador nuevo (Prioridad 4 omitida), así que el filtro CORE actual queda **sin cambios**:

- Filtro actual (20 marcadores): **31 de 577 fragmentos** (5.4%) del corpus de Ciencias Naturales 6to en producción.
- Con los 9 candidatos propuestos habría subido a ~40/577 (≈7%), pero la inspección manual mostró que serían en su mayoría **falsos positivos** (teoría real cortada junto con la instrucción incrustada) — ver el mensaje de la sección anterior en la conversación para los ejemplos concretos (Sol, Mendel, Copérnico, célula vegetal, sistema excretor).

---

## 7. Riesgos residuales conocidos

1. **Caso B (nubes, página 161) sigue sin resolverse.** Causa raíz: OCR de tabla con columnas desordenadas. Fuera de alcance esta semana (no tocar `ingesta/`). Si un estudiante de 6to pregunta específicamente por tipos de nubes durante el piloto, puede recibir una clasificación incorrecta. Sugerencia para después del piloto: corregir a mano el `contenido_texto` de ese fragmento en Postgres (fix quirúrgico, sin re-indexar) — Daniel prefirió no hacerlo esta semana.
2. **Rótulos de figura en general** (el patrón del Caso A: "epidermis superior e inferior" como rótulo de diagrama): mitigado parcialmente por la regla 16 del prompt, pero no eliminado al 100% — no hay manera de filtrarlo en la capa de retrieval sin marcador textual limpio. Documentado como limitación conocida (ya anticipado en el prompt original).
3. **Recuadros decorativos en general** (Prioridad 4 omitida): el prompt (regla 16) ayuda a que el modelo no los use como definición/cierre, pero siguen entrando al contexto que ve el LLM. Es una mitigación de segunda capa, no una eliminación en el retrieval.
4. **Cold start de Modal**: la decisión (Opción B) está tomada pero **no aplicada** — depende de que Daniel cambie `MODAL_FINETUNED_GRADOS` en Railway. Mientras no se aplique, el riesgo de 195s sigue activo en producción.
5. **Suite de pytest**: no pude correr los 11 tests de integración documentados en `CLAUDE.md` porque `pytest` no está instalado ni en el contenedor backend ni en un venv local disponible (gap preexistente, no introducido por este cambio). Verifiqué manualmente los endpoints de chat afectados (pregunta normal, rechazo, pregunta por página) contra el backend local, todos con `status=200` y comportamiento esperado.

---

## 8. Recomendación

**Prioridades 2 y 3: sí, recomendable desplegar antes del piloto.** Son cambios aditivos y de bajo riesgo (texto de prompt + lógica determinística en `chat/service.py`), no tocan `ingesta/`, modelos de datos ni migraciones, y quedaron verificados localmente end-to-end. Mejoran fidelidad medible (Caso A) y agregan transparencia de fuente en cada respuesta (Prioridad 3), sin depender de que el LLM obedezca instrucciones.

**Antes de desplegar, dos pendientes de Daniel (no de código):**
- Aplicar la Opción B en Railway (`MODAL_FINETUNED_GRADOS` vacío) — puede hacerse independientemente del push de código.
- Decidir el momento del push a `origin/main` con tiempo suficiente para verificar en producción antes del sábado (no el viernes por la noche), según la regla que vos mismo pusiste.

**Caso B queda como riesgo residual conocido, no bloqueante** para el piloto en general (es un tema puntual del libro, no todo el contenido), pero vale avisarle al docente por si surge la pregunta específica sobre tipos de nubes.

No hice push ni merge. Todo el trabajo está en la rama `fix/pre-piloto`, esperando tu confirmación explícita para el siguiente paso.

---

## 9. Prioridad 1 (revisada dos veces) — Keep-warm HÍBRIDO de Modal

Decisión final: el fine-tuned se queda activo en producción para 6to grado (`MODAL_FINETUNED_GRADOS` NO se toca, sigue en `3`). El mecanismo de keep-warm pasó por dos versiones:

1. **v1 (descartada):** ventana fija de 4h/día (2pm-6pm). Funcionaba, pero pagaba por 4 horas completas todos los días aunque no hubiera estudiantes conectados todo ese tiempo.
2. **v2 (final, implementada):** **híbrido** — ventana base corta y garantizada + extensión rodante por actividad real de un estudiante de la cohorte fine-tuned. Más eficiente en presupuesto, propuesto por Daniel.

### 9.1 Diseño híbrido

- **Ventana base garantizada: 2pm–3pm** (1 hora), para que el contenedor ya esté caliente antes de que llegue el primer estudiante típico. Usa las mismas variables `MODAL_KEEPWARM_HORA_INICIO`/`HORA_FIN` de la v1 (sin cambiar su tipo).
- **Extensión rodante de 15 minutos:** cada vez que un estudiante de la cohorte fine-tuned (grado_id en `MODAL_FINETUNED_GRADOS`) manda una pregunta de chat, se extiende (o reinicia, si ya había una activa) el keep-warm por `MODAL_KEEPWARM_EXTENSION_MINUTOS` (default 15) desde ESE momento. Una sesión de uso continuo mantiene el contenedor caliente todo lo que dure, sin pagar por horas sin uso.
- **Dónde se engancha:** `chat/service.py:267`, en la rama que YA existe (`if grado_usa_finetuned(estudiante.grado_id):`) — se llama a `registrar_actividad()` justo ahí, antes de intentar `chat_finetuned`. **No se tocó `auth/`** — se descartó enganchar en el login porque hubiera significado tocar un módulo fuera de lo ya contemplado, y el chat es donde el código YA sabe que este estudiante va a golpear Modal.
- **Fuera de la ventana base y sin actividad reciente:** no hay pings, Modal puede dormirse normal, y el fallback a Together AI existente sigue cubriendo esos casos igual que siempre.
- **Ambas señales (base y extensión) quedan acotadas por `MODAL_KEEPWARM_FECHA_INICIO`/`FECHA_FIN`** — si un estudiante de 6to escribe fuera del rango de fechas del piloto, no dispara ningún ping. Sin este límite, la extensión por actividad podría seguir gastando crédito después de terminado el piloto.
- **Estado en memoria, no persistente:** `_ultima_actividad` es una variable de módulo (un `datetime`), no hay Redis/BD/archivo — no hace falta, el backend corre con `--workers 1` (confirmado en `llm/client.py`), así que no hay condición de carrera entre procesos. **Si Railway reinicia el proceso**, se pierde ese estado y el keep-warm cae de nuevo a "solo ventana base" hasta la próxima actividad real. Peor caso: un ping de menos justo después de un restart, nunca un ping de más ni costo extra.

### 9.2 Costo estimado (rango, calculado ANTES de implementar)

Con "A10" a $0.000306/seg = $1.10/hora (Modal no lista "A10G" aparte, ver nota de la v1) y 5 días (lunes a viernes):

| Escenario | Cálculo | Costo |
|---|---|---|
| **Mínimo** (solo ventana base, casi sin actividad real de 6to) | 5 días × 1h | **$5.51** |
| **Máximo razonable** (actividad dispersa cubre las ~4h típicas de sesión + 15min de cola tras el último mensaje) | 5 días × 4.25h | **$23.41** |

Ambos extremos quedan por debajo de los $29 de crédito — el máximo razonable deja ~$5.6 de margen, más que la v1 ($22.03 fijo, sin margen para imprevistos). Si el uso real es bajo, el ahorro es sustancial (hasta $17.90 menos que la v1).

### 9.3 Configuración final para Railway (completa y explícita)

```
MODAL_KEEPWARM_ENABLED=true
MODAL_KEEPWARM_HORA_INICIO=14
MODAL_KEEPWARM_HORA_FIN=15
MODAL_KEEPWARM_EXTENSION_MINUTOS=15
MODAL_KEEPWARM_FECHA_INICIO=2026-08-03
MODAL_KEEPWARM_FECHA_FIN=2026-08-07
MODAL_KEEPWARM_INTERVALO_SEGUNDOS=180
```
(`MODAL_KEEPWARM_INTERVALO_SEGUNDOS` es opcional — 180 ya es el default en código; lo dejo explícito para que quede completo en un solo lugar, ya que la vez pasada quedaron variables sin valor en Railway.) `MODAL_FINETUNED_GRADOS` **no se toca**, sigue en `3`.

### 9.4 Archivos modificados (acumulado v1+v2)

```
backend/app/config.py                    (+18 líneas: 7 variables MODAL_KEEPWARM_*)
backend/app/main.py                      (+4 líneas: lanzar/cancelar el loop en el lifespan)
backend/app/workers/modal_keepwarm.py    (nuevo, ~115 líneas: ventana base + extensión rodante)
backend/app/modules/chat/service.py      (+4 líneas: import y llamada a registrar_actividad())
```
No se tocó `MODAL_FINETUNED_GRADOS`, `auth/` (ningún archivo), ni `scripts/modal_finetuned/serve.py`.

### 9.5 Pruebas en LOCAL (contra el Modal real — no existe un "Modal local")

**Mecanismo de ping base (v1, sigue vigente sin cambios):** con ventana abierta (0h-24h) e intervalo de 30s, confirmé transición 503→200 a los ~180s (consistente con el cold start de ~195s ya medido) y 34 pings seguidos en 200 durante 17+ minutos sin volver a dormirse. Con Modal caliente, una pregunta real de un estudiante de 6to contra producción respondió en **7.99s** (dentro del RNF de 15s, vs. 195s en frío).

**Mecanismo híbrido (v2, las 3 pruebas que pidió el diseño):**
1. **Ventana base cerrada + actividad real →** con `HORA_INICIO=3`/`HORA_FIN=4` (cerrada a esa hora del día) y `EXTENSION_MINUTOS=1` (acortado para no esperar 15 min reales), mandé una pregunta real como estudiante local (mapeado temporalmente a `MODAL_FINETUNED_GRADOS` solo para esta prueba). El keep-warm arrancó a pinguear a los pocos segundos de la actividad — confirmado en logs.
2. **Expiración tras el vencimiento →** sin actividad adicional, los pings se detuvieron solos ~40s después de empezar (el 1 minuto configurado) y no volvieron a aparecer en los siguientes 2+ minutos observados.
3. **Reinicio rodante (dos actividades cercanas) →** probado con la lógica directamente (sin repetir una llamada real de ~200s a Modal): actividad en t=0, segunda actividad en t=30s. A los t=75s (45s desde la 2ª actividad, que sin reinicio ya habría expirado a los t=60s) el sistema seguía diciendo que debía pinguear; a los t=95s (65s desde la 2ª actividad) ya no. Confirma que una sesión de preguntas seguidas mantiene el keep-warm activo sin cortes.

### 9.6 Riesgos residuales conocidos

- **El primer estudiante de cada racha de inactividad prolongada todavía puede esperar el cold start completo (~195s)** si su primera pregunta cae fuera de la ventana base (2pm-3pm). El keep-warm evita que Modal se vuelva a dormir MIENTRAS hay actividad, pero no elimina el primer despertar si empieza tarde. Esta limitación ya la tenías clara y la aceptaste al proponer el diseño.
- Presupuesto: con la config recomendada (5 días), el rango es $5.51-$23.41 — dentro de los $29 en ambos extremos, con más margen que la v1.
- Si Railway reinicia el proceso del backend durante el piloto, se pierde el estado de "actividad reciente" (vuelve a depender solo de la ventana base hasta la próxima pregunta de un estudiante de 6to) — ya evaluado como aceptable.
- El ping usa el mismo `MODAL_FINETUNED_API_KEY` de producción — no expone nada nuevo, ya viaja como header en cada llamada real del chat.
- **Pendiente de Daniel:** las variables `MODAL_KEEPWARM_ENABLED`, `MODAL_KEEPWARM_HORA_INICIO`, `MODAL_KEEPWARM_HORA_FIN` que ya se agregaron en Railway (sin valor todavía) deben actualizarse con los valores de la tabla de la sección 9.3 antes del push — no las toqué yo.

**⚠️ SUPERADO por la sección 10 — el keep-warm de esta sección 9 quedó revertido/inerte.** Se mantiene el texto de arriba como registro de lo que se probó, pero el diseño vigente es el de la sección 10.

---

## 10. Cold start aceptado + A/B ampliado a todos los grados (decisión final, 2026-07-29)

Nueva decisión de Daniel: durante el piloto, el modelo fine-tuned atiende a **todos los grados**, no solo 6to. El cold start (~195s la primera vez que Modal está dormido) se acepta como comportamiento normal — **no hay keep-warm**. La protección de presupuesto ahora es un **Workspace Budget de $20 en el dashboard de Modal** (Settings → Usage & Billing), configurado por Daniel fuera de este repo: cuando el gasto del mes llega a $20, Modal detiene las apps automáticamente. Después del piloto, todos los grados vuelven a Together AI exclusivamente (recordatorio para Daniel, no acción de código todavía).

### 10.1 Keep-warm: revertido, código inerte (no borrado)

Elegí **dejar el código presente pero inerte** en vez de borrar archivos, por ser menos propenso a error a esta altura de la semana:
- `backend/app/workers/modal_keepwarm.py`: queda tal cual, pero **nada lo llama** — `keepwarm_loop()` sigue arrancando desde el `lifespan` de `main.py`, pero retorna de inmediato porque `MODAL_KEEPWARM_ENABLED` es `false` por default (y nadie define esa variable en producción ahora).
- `backend/app/config.py`: las 7 variables `MODAL_KEEPWARM_*` quedan definidas (con sus defaults), sin usarse.
- `backend/app/main.py`: el `asyncio.create_task(keepwarm_loop())` en el lifespan queda igual — es barato (retorna al instante si está desactivado) y quitar el import + la línea no aportaba nada a esta altura de la semana.
- **`backend/app/modules/chat/service.py`: SÍ se revirtió el gancho específico** — se quitó el `import registrar_actividad` y la línea `registrar_actividad()` dentro de la rama `grado_usa_finetuned`. La Prioridad 3 (referencia de página determinística, en otra parte del mismo archivo) **no se tocó**.

Verifiqué que no queda ninguna otra referencia a `registrar_actividad` fuera del propio módulo (`grep -rn "registrar_actividad" app/` solo encuentra la definición y comentarios internos).

### 10.2 A/B ampliado — grados reales confirmados contra la BD de producción

Consulté `GET /admin/grados` en producción (no asumí "1 a 6"): los IDs **no son consecutivos**.

| grado_id | Nombre | Estudiantes |
|---|---|---|
| 1 | 4to Primaria | 25 |
| 2 | 5to Primaria | 19 |
| 3 | 6to Primaria | 9 |
| 5 | 7mo Básico | 15 |
| 6 | 8vo Básico | 12 |
| 7 | 9no Básico | 10 |
| 4 | **Grado Pruebas** | 21 |

**⚠️ Necesito que confirmes:** `grado_id=4` ("Grado Pruebas") tiene 21 registros pero el nombre indica que es un grado de prueba/desarrollo, no uno real del piloto. Lo **excluí** de la lista recomendada de abajo. Si esos 21 sí son estudiantes reales del piloto, avisame y lo agrego.

**Valor recomendado:** `MODAL_FINETUNED_GRADOS=1,2,3,5,6,7`

**No hizo falta tocar el parsing.** `_grados_finetuned()` en `app/llm/client.py` ya soporta una lista separada por comas (`"3" o "3,4"`, según su propio docstring) — verifiqué con el valor real de 6 grados y funciona sin cambios: `grado_usa_finetuned(1..7 excepto 4)` → `True`, `grado_usa_finetuned(4)` → `False`.

### 10.3 Pruebas en LOCAL

1. **Grado que antes NO estaba en el A/B ahora enruta a Modal:** con `MODAL_FINETUNED_GRADOS=1` localmente (antes solo se probaba con grado 3), `carlos` (grado_id=1) enrutó correctamente a `chat_finetuned()` — confirmado en logs (`[Chat] Fine-tuned no listo (cold start?)...` y luego éxito).
2. **Fallback a Together sigue intacto:** con `MODAL_FINETUNED_URL` apuntando a un dominio roto a propósito, la pregunta de `carlos` devolvió `status=200` en 12.3s con una respuesta real y coherente sobre fotosíntesis. Logs: `Fine-tuned no listo (cold start?), reintentando en 10.0s` → `Fine-tuned no disponible, fallback a base: [Errno -2] Name or service not known`. Ningún error llega al estudiante.
3. **Keep-warm ya no pinguea:** en cada arranque del backend durante esta sesión, el único log de `modal_keepwarm` es `[KeepWarm] Desactivado (MODAL_KEEPWARM_ENABLED=false o sin MODAL_FINETUNED_URL)` — cero pings.
4. **Casos A/B/C reproducidos vía el modelo fine-tuned real (no Together)** — ver hallazgo importante abajo.

### 10.4 ⚠️ Hallazgo importante: el fine-tuned NO mejora los 3 casos frente al prompt nuevo — en algunos puntos es peor que Together

Como ahora TODOS los grados pueden terminar respondidos por el fine-tuned (antes solo 6to), reproduje los 3 casos reales usando `chat_finetuned()` directamente (mismo prompt con las reglas anti-alucinación de la Prioridad 2, mismo contexto real de producción). Comparado con la versión "DESPUÉS" ya documentada en la sección 3 (que usó Together):

- **Caso A (página 83):** el fine-tuned **volvió a citar el recuadro del ODS "Hambre cero"** al final, y encima agregó una conexión inventada ("esto se conecta con cómo las plantas producen su propia comida a través de la fotosíntesis") — Together, con el mismo prompt, ya NO hacía esto. **Regresión frente a Together.**
- **Caso B (nubes):** sigue mal, igual que con Together — sigue afirmando que las nubes bajas "anuncian lluvia" (el libro dice que no). Sin cambio relativo a Together (ambos fallan por la causa raíz de OCR, ver sección 6).
- **Caso C (sistema excretor):** la dirección del uréter salió correcta (riñón→vejiga), pero el fine-tuned **elaboró extensamente sobre arteria renal, vena cava, arteria inferior y aorta con información anatómica general no presente en el fragmento** (ej. "la aorta es la arteria más grande del cuerpo que lleva sangre rica en oxígeno desde el corazón") — una violación más marcada de la regla 12 (no agregar información no literal) que la que mostró Together en la misma prueba.

**Interpretación:** el modelo fine-tuned (QLoRA sobre 563 ejemplos) no necesariamente sigue las reglas nuevas del prompt (agregadas después del fine-tuning) tan bien como el modelo base de Together, que es más grande y generalista en seguir instrucciones nuevas de system prompt. Esto no cambia la decisión de Daniel (fine-tuned para todos los grados durante el piloto), pero es información relevante: **el riesgo de alucinación de la Prioridad 2 no baja al ampliar el A/B — puede que suba un poco**, según estos 3 casos puntuales (muestra pequeña, no es una evaluación estadística).

### 10.5 Recordatorio para después del piloto

Volver a poner `MODAL_FINETUNED_GRADOS` vacío (o decidir en su momento mantenerlo) para que todos los grados usen Together AI exclusivamente, como estaba antes de esta semana.

### 10.6 Archivos modificados (acumulado de toda la semana, estado final)

```
backend/app/config.py                    (Prioridad 1: 7 variables MODAL_KEEPWARM_*, ahora sin uso)
backend/app/main.py                      (Prioridad 1: lifespan lanza keepwarm_loop(), inerte por default)
backend/app/workers/modal_keepwarm.py    (nuevo, Prioridad 1, código completo pero sin ningún caller — inerte)
backend/app/modules/chat/service.py      (Prioridad 3: referencia de página — vigente; Prioridad 1: gancho de keep-warm — REVERTIDO)
backend/app/modules/chat/prompts.py      (Prioridad 2: reglas 12-16 anti-alucinación — vigente)
```

`MODAL_FINETUNED_GRADOS` se actualiza en Railway (no en código) — pendiente de que Daniel confirme el valor exacto (sección 10.2) y lo aplique.
