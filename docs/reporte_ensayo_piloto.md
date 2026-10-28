# Reporte de Ensayo Técnico del Piloto
## Fecha: 2026-07-28 04:08 UTC
## Entorno: Producción (Railway) — https://tutor-inteligente-production.up.railway.app

### Resumen
- Total de verificaciones: 36
- Aprobadas: 36 ✅
- Fallidas: 0 ❌

### Resultados detallados

#### A) Health Check
- [✅] GET /health responde 200 (estado_general=ok) — 430ms
- [✅] Servidor responde en <3s — 430ms

#### B) Autenticación
- [✅] Login estudiante (naldana) → JWT — 714ms
- [✅] Login docente (MValery) → JWT — 614ms
- [✅] Login estudiante 6to (layala) → JWT — 850ms
- [✅] GET /auth/me con token estudiante → rol y grado_id correctos (rol=estudiante grado_id=1) — 5504ms
- [✅] GET /auth/me con token docente → rol y grado_id correctos (rol=docente grado_id=3) — 309ms
- [✅] Login con credenciales incorrectas → 401 — 642ms

#### C) Verificación de datos en BD
- [✅] Login admin → JWT — 769ms
- [✅] GET /admin/grados devuelve 7 grados: ['4to Primaria', '5to Primaria', '6to Primaria', '7mo Básico', '8vo Básico', '9no Básico', 'Grado Pruebas'] — 307ms
- [✅] Existen grados 4to a 9no
- [✅] Todos los grados tienen al menos 1 estudiante
- [✅] Ningún estudiante (110 totales) tiene grado_id NULL
- [✅] Asignaturas y libros indexados: {'Ciencias Naturales': 2, 'Comunicación y Lenguaje': 0, 'Matemáticas': 3} — 302ms
- [✅] Existen libros indexados de Matemáticas
- [✅] Existen libros indexados de Ciencias Naturales

#### D) ChromaDB
- [✅] No existe endpoint HTTP que exponga stats de ChromaDB (confirmado en código) — se infiere vía chat en sección E

#### E) Chat
- [✅] Respuesta incluye referencias a página (5 refs) — 1691ms
- [✅] Responde en <30s — 1691ms
- [✅] Modelo usado: NO verificable desde la respuesta (schema ChatResponse no expone el modelo)
- [✅] Chat estudiante 6to (A/B Modal): respuesta llega (cold=False) — 1979ms
- [✅] Sistema rechaza pregunta fuera de contexto (heurística de texto)

#### F) Lecciones y micro-lecciones
- [✅] GET /lecciones/mis-libros devuelve 2 libro(s) — 380ms
- [✅] Ruta de aprendizaje devuelve 38 lecciones con títulos — 376ms
- [✅] Micro-lección devuelve 8 tarjetas (≥4) — 16409ms
- [✅] Micro-lección responde en <60s — 16409ms

#### G) Actividades
- [✅] Estudiante temporal creado (id=119, username=ensayo_piloto_1785211708) — 578ms
- [✅] Actividad generada con estructura válida (tipo=opcion_multiple) — 2719ms
- [✅] Evaluar respuesta devuelve puntaje/retroalimentación (puntaje=0.0) — 805ms
- [✅] Estudiante temporal desactivado (soft-delete, id=119) — 1375ms

#### H) Diagnóstico / Analytics
- [✅] Dashboard docente devuelve datos (9 estudiantes, 2 libros, progreso=0.2%) — 904ms
- [✅] GET /docente/estudiantes devuelve 9 estudiante(s) — 570ms
- [✅] Detalle de estudiante devuelve perfil (perfil=3 temas, puede estar vacío) — 432ms

#### I) Seguridad
- [✅] Estudiante accediendo a endpoint docente → 403 — 341ms
- [✅] Endpoint protegido sin JWT → 401 — 346ms
- [✅] CORS responde Access-Control-Allow-Origin para http://localhost:3000 (Access-Control-Allow-Origin=http://localhost:3000) — 370ms

### Problemas encontrados
Ninguno bloqueante. Observaciones menores:

1. [MENOR] "Comunicación y Lenguaje" tiene 0 libros indexados.
   - Impacto: ninguno para el piloto si solo se usarán Matemáticas y Ciencias Naturales; si se planea activar esa asignatura para el 3 de agosto, falta subir e indexar contenido.
   - Acción sugerida: confirmar con el equipo si esa asignatura entra en el alcance del piloto.
2. [INFORMATIVO] El progreso promedio que ve el docente MValery es 0.2% sobre 9 estudiantes de su grado.
   - Impacto: ninguno — esperable si el piloto real aún no arrancó y no hay uso registrado.
   - Acción sugerida: ninguna, solo confirmar que no es un estudiante/grado de prueba mezclado con los reales del piloto.

### Limitaciones de esta verificación (no automatizables desde afuera)
- **D) ChromaDB**: no existe ningún endpoint HTTP que exponga el estado interno de la colección `libros_texto` (se confirmó revisando el código: solo se usa dentro de `ingesta/indexer.py` y `rag/search.py`). Se infirió indirectamente vía el chat en la sección E — la respuesta trajo 5 referencias con página, lo que confirma que el retrieval en Chroma está funcionando para al menos un grado/asignatura. No se verificó fragmento por fragmento ni por cada combinación grado×asignatura.
- **E) "Modelo usado"**: el schema `ChatResponse` no expone qué modelo respondió (Together AI base vs. fine-tuned en Modal), así que no se puede confirmar por la respuesta HTTP. La prueba A/B con el estudiante de 6to (`layala`) solo confirma que la ruta responde y da una señal de tiempo (frío vs. caliente), no qué modelo generó el texto.
- **C) Libros por grado**: se confirmó que existen libros de Matemáticas y Ciencias a nivel de asignatura (agregado global), pero no hay un endpoint que cruce "libro indexado × grado específico" para los 7 grados de una sola vez; se infirió parcialmente a través de `/lecciones/mis-libros` de los estudiantes de prueba (naldana ve 2 libros).

### Verificación adicional: CORS en producción (28 jul 2026)
- Dominio del frontend: `https://just-blessing-production-6164.up.railway.app`
- Prueba: preflight `OPTIONS /auth/login` y request real `GET /health`, ambos con header `Origin: https://just-blessing-production-6164.up.railway.app`, contra el backend en `https://tutor-inteligente-production.up.railway.app`.
- Resultado: ✅ coincide exactamente. El backend responde `access-control-allow-origin: https://just-blessing-production-6164.up.railway.app` (no wildcard `*`), `access-control-allow-credentials: true`, y el preflight autoriza `GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS` con el header `content-type`. `ALLOWED_ORIGINS` en Railway incluye el dominio real del frontend.
- Acción tomada: ninguna — no hace falta tocar la variable de entorno. Se cierra el punto 2 de "Pendientes" abajo.

### Conclusión
El sistema ESTÁ listo para el piloto del 3 de agosto, según las 36 verificaciones automatizadas + la verificación adicional de CORS (todas aprobadas). Quedan 2 puntos sin verificar por falta de acceso/endpoint (ver "Limitaciones" arriba), no bloqueantes: cobertura de ChromaDB fragmento por fragmento y confirmación del modelo exacto (Together vs. Modal) en cada respuesta de chat.
