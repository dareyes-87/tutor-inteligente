# Limitaciones conocidas

## Filtro de ejercicios en libros con teoría y ejercicios mezclados

El RAG descarta como contexto los fragmentos que parecen ejercicios del libro (`es_ejercicio_del_libro` en `backend/app/modules/rag/search.py`, por marcadores como "¡Mesa lista!" o "Ahora es tu turno"). En libros de Matemáticas como el de 4to Primaria, la ingesta corta el texto en fragmentos de ~800 caracteres sin respetar dónde termina la teoría y empieza el ejercicio, así que un mismo fragmento suele traer las dos cosas, y el OCR además parte los marcadores en dos líneas ("Ahora es tu\nturno"). Por eso el filtro puede **dejar pasar ejercicios** (unos 58 fragmentos de Matemáticas 4to cuyo marcador quedó partido) y, si se endurece normalizando los saltos de línea, **descarta teoría real** (se probó el 2026-10-28: se perdían la definición de número decimal, p. 65, y los criterios de divisibilidad, p. 34, y se revirtió). La solución de fondo —trabajo futuro— es fragmentar en la ingesta respetando los límites teoría/ejercicio (detectar las cabeceras de ejercicio y cortar ahí) y volver a indexar los libros; mientras tanto, `backend/scripts/debug/simular_filtro_ejercicio.py` mide el efecto de cualquier cambio de marcadores sobre el corpus y sobre las lecciones de la ruta.

## Fracciones apiladas y signos en los libros de Matemática del MINEDUC (1B/2B/3B)

Los libros de Matemática de básico son PDF digitales cuyas fórmulas usan fuentes de símbolos (MathMagic) que extraen mal algunos glifos: "÷" sale como `'`, "×" como `#` y los paréntesis grandes como `^ … h`. La ingesta los corrige en `_extract_digital_text` (`backend/app/modules/ingesta/pdf_processor.py`), pero solo cuando el número de apariciones del carácter en la página coincide con el de esas fuentes; si no cuadra (p. ej. hay un `#` de otra fuente), la página se deja como está. Medido el 2026-10-28: ÷ 100/100/86 %, × 97/96/97 %, "(" 100/100/98 % y ")" 96/78/69 % en 1B/2B/3B. Las **fracciones apiladas** salen partidas en dos líneas (numerador arriba, denominador abajo, p. ej. "x" y "3" en lugar de "x/3"): ningún modo de extracción de PyMuPDF las reconstruye, porque son textos separados con una raya dibujada entre ellos. Rehacerlas requeriría reconstruir la fórmula por posición en la página —trabajo futuro—. Las conclusiones en prosa del recuadro "C" sí se extraen limpias, así que la teoría llega al RAG; lo que se degrada son los ejemplos con fracciones.

## Páginas de presentación en los libros del MINEDUC (básico)

La ingesta indexa todas las páginas del PDF. En los libros de básico, las primeras páginas
no son contenido: créditos, Himno Nacional, "cómo usar este libro" y, en las Guías de
Ciencias, tablas de planificación de ~100 000 caracteres por página (pp. 6–9), que generaban
unos 700 fragmentos basura por Guía (34–36 % del libro) y una lección 1 "Explorando la Guía…".
En local se borraron a mano (oct. 2026) de Postgres y Chroma los fragmentos de las pp. 1–6 de
1B/2B/3B Matemática (el contenido empieza en la p. 7, "Clase 1") y de las pp. 1–11 de las
Guías G1/G2/G3 (empieza en la p. 12), y se regeneraron sus lecciones con
`scripts/regenerar_lecciones.py --libro-id N`.

**En una ingesta futura de estos libros** (o de otro con páginas de presentación):

1. Recortar el PDF antes de subirlo, quitando esas páginas (con cualquier editor de PDF o con
   PyMuPDF: `doc.select(range(primera_pagina_de_contenido - 1, len(doc)))`). Ojo: la ingesta
   numera las páginas desde 1 sobre el PDF recortado, así que las referencias "página X" del
   tutor ya no coincidirían con la numeración del libro impreso.
2. O bien, subirlo completo y luego borrar los fragmentos de esas páginas (Postgres `fragmento`
   + Chroma por `chunk_id_vectordb`) y regenerar las lecciones, como se hizo en local.

**Propuesta (sin implementar): parámetro `pagina_inicio` en `POST /ingesta/libros`.** Campo
opcional del formulario (entero ≥ 1, por defecto 1) guardado en `LibroTexto` (requiere una
migración); `procesar_libro` descartaría las páginas `< pagina_inicio` después de
`process_pdf` y antes del chunking, conservando la numeración original del PDF (las
referencias de página siguen coincidiendo con el libro). En `/docente/libros` se pediría como
"Primera página con contenido". Toca: `ingesta/router.py`, `ingesta/service.py`,
`models/libro.py` + migración, `workers/ingesta_worker.py` y el formulario de subida web.

**Pendiente de decidir:** la última lección de G2 y G3 (L50, p. 306) es la bibliografía
("El Rincón de las Fuentes"). El seed del piloto no la usa (practica entre la 2ª y la
penúltima lección), pero aparece en la ruta de 8vo y 9no.
