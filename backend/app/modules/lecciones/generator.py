"""
Generador automático de lecciones (ruta de aprendizaje) a partir del
contenido de un libro ya indexado.

Tras la ingesta, divide el libro en segmentos de páginas CONSECUTIVOS (tantos
como lecciones queremos, escalado por el tamaño del libro) y le pide al LLM que
le ponga nombre/descripción/tema a cada segmento. Así la ruta cubre el libro de
principio a fin de forma determinística (el LLM no puede "olvidar" la mitad
final): la cobertura la garantiza la segmentación, y el LLM solo aporta los
nombres atractivos. Si el LLM falla, cada segmento recibe un nombre genérico.
"""
import logging
import math

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import llm_client
from app.models.fragmento import Fragmento
from app.models.leccion import Leccion
from app.modules.lecciones.schemas import LeccionGenerada

logger = logging.getLogger(__name__)

# Caracteres del primer fragmento de cada página que se le pasan al LLM como
# extracto. Solo el INICIO de cada página acota el costo de tokens; si el total
# excede el contexto, se reduce.
CHARS_POR_PAGINA = 100
CHARS_POR_PAGINA_REDUCIDO = 50
# Tope defensivo del texto total que ve el LLM. Qwen 7B tiene ~32K tokens de
# contexto (≈48K chars en español); 48000 deja margen para el prompt + la salida.
MAX_CHARS_CONTEXTO = 48000

# --- Cantidad de lecciones, escalada por el tamaño del libro ---
# nº lecciones = (páginas con contenido / PAGINAS_POR_LECCION), acotado [MIN, MAX].
# Un libro corto da pocas lecciones; uno largo cubre TODO el contenido sin
# quedarse en el inicio. Con ~5 págs/lección un libro de 189 págs ≈ 38 lecciones
# (antes 9 págs/lección daba 21), para que cada lección sea más granular y el
# tutor pueda profundizar en subtemas.
#
# IMPORTANTE (regenerar lecciones existentes): cambiar estos parámetros NO
# actualiza las lecciones ya guardadas en la BD. Para aplicarlo a un libro ya
# indexado, el admin debe:
#   1. Borrar las lecciones (y su progreso) del libro, por ejemplo:
#      DELETE FROM progreso_leccion; DELETE FROM leccion WHERE libro_id = <id>;
#      (o vía script con delete(ProgresoLeccion) + delete(Leccion).where(...))
#   2. Re-disparar la generación llamando a generar_lecciones_desde_libro(<id>, db).
# NO se borran datos automáticamente.
PAGINAS_POR_LECCION = 5
MIN_LECCIONES = 5
MAX_LECCIONES = 50

# La ruta se genera UNA sola vez por libro, así que aquí sí conviene un modelo más
# potente que el 7B por defecto: nombra mejor los segmentos y respeta el contenido.
# Solo lo usa este generador; el chat y las actividades siguen con el modelo base.
# Nota: Qwen2.5-72B-Instruct-Turbo NO está disponible serverless en esta cuenta de
# Together (requiere endpoint dedicado), así que se usa el 70B de Llama, que sí lo está.
MODELO_RUTA = "meta-llama/Llama-3.3-70B-Instruct-Turbo"


def _calcular_num_lecciones(fragmentos: list[Fragmento]) -> int:
    """Cuántas lecciones generar según cuántas páginas de contenido tiene el libro."""
    num_paginas = len({f.numero_pagina for f in fragmentos})
    objetivo = math.ceil(num_paginas / PAGINAS_POR_LECCION) if num_paginas else MIN_LECCIONES
    return max(MIN_LECCIONES, min(MAX_LECCIONES, objetivo))


def _snippets_por_pagina(fragmentos: list[Fragmento], chars_por_pagina: int) -> dict[int, str]:
    """Mapa página -> primeros `chars_por_pagina` de su primer fragmento.

    Los fragmentos llegan ordenados por (numero_pagina, id), así que el primero
    de cada página es el inicio de esa página.
    """
    por_pagina: dict[int, str] = {}
    for f in fragmentos:
        if f.numero_pagina in por_pagina:
            continue  # solo el primer fragmento de cada página
        texto = " ".join((f.contenido_texto or "").split())
        por_pagina[f.numero_pagina] = texto[:chars_por_pagina]
    return por_pagina


def _segmentar(fragmentos: list[Fragmento], num_lecciones: int) -> list[dict]:
    """Divide las páginas del libro en ~`num_lecciones` segmentos consecutivos.

    Cada segmento = {ini, fin, paginas: "ini-fin", texto: extractos de sus páginas}.
    Es la unidad de una lección y garantiza cobertura completa del libro.
    Si el texto total excede el contexto, reduce los extractos por página.
    """
    chars = CHARS_POR_PAGINA
    snippets = _snippets_por_pagina(fragmentos, chars)
    paginas = sorted(snippets)
    if not paginas:
        return []
    # Si el extracto completo no cabe en el contexto, reduce chars/página.
    total = sum(len(snippets[p]) for p in paginas)
    if total > MAX_CHARS_CONTEXTO:
        chars = CHARS_POR_PAGINA_REDUCIDO
        logger.info(
            "[Lecciones] Extractos de %d chars superan %d; reduciendo a %d chars/página",
            total, MAX_CHARS_CONTEXTO, chars,
        )
        snippets = _snippets_por_pagina(fragmentos, chars)

    grupos = max(1, min(num_lecciones, len(paginas)))
    tam = math.ceil(len(paginas) / grupos)
    segmentos: list[dict] = []
    for i in range(0, len(paginas), tam):
        grupo = paginas[i:i + tam]
        ini, fin = grupo[0], grupo[-1]
        texto = " ".join(f"[p{p}] {snippets[p]}" for p in grupo)
        segmentos.append({"ini": ini, "fin": fin, "paginas": f"{ini}-{fin}", "texto": texto})
    return segmentos


def _build_messages_segmento(
    seg: dict, indice: int, total: int, estricto: bool = False
) -> list[dict]:
    """Pide al LLM el nombre/descripción/tema de UN solo segmento.

    Una llamada por segmento evita que el modelo "arrastre" el tema de las
    primeras páginas al resto del libro: solo ve el contenido de este segmento.
    """
    prompt = f"""Eres un experto en diseño curricular escolar en Guatemala. A continuación tienes el contenido de UNA lección (la {indice} de {total}) de un libro de Ciencias Naturales, correspondiente a las páginas {seg['paginas']}:

{seg['texto']}

Genera un JSON para ESTA lección, basándote ÚNICAMENTE en el contenido anterior:
{{
  "nombre": "Nombre corto y atractivo para niños de 8-12 años, sobre el tema REAL de este contenido",
  "descripcion": "Una oración sobre qué aprenderá el estudiante",
  "tema_clave": "palabra o frase clave (1-3 palabras) específica de este contenido para buscar en la base de datos"
}}

REGLAS:
- El nombre y el tema_clave deben reflejar el contenido REAL mostrado arriba. NO inventes temas que no aparecen (si habla de plantas, no lo llames del cuerpo humano).
- Responde SOLO con el JSON, sin texto adicional."""

    if estricto:
        prompt += "\n\nIMPORTANTE: Responde ÚNICAMENTE con el JSON válido, sin markdown, sin explicaciones adicionales."

    return [
        {
            "role": "system",
            "content": "Eres un experto en diseño curricular escolar en Guatemala. Respondes solo con JSON válido.",
        },
        {"role": "user", "content": prompt},
    ]


def _parsear(data: dict | None) -> LeccionGenerada | None:
    """Valida la salida del LLM (una lección) contra el schema; None si no sirve."""
    if not data:
        return None
    try:
        return LeccionGenerada.model_validate(data)
    except ValidationError as e:
        logger.warning("[Lecciones] JSON no cumple el schema esperado: %s", e)
        return None


async def generar_lecciones_desde_libro(libro_id: int, db: AsyncSession) -> list[Leccion]:
    """
    Genera y persiste la ruta de lecciones de un libro.

    1. Lee los fragmentos del libro y divide las páginas en segmentos consecutivos.
    2. Pide al LLM un nombre por segmento (1 intento + 1 reintento estricto).
    3. Cada segmento sin nombre del LLM recibe un nombre genérico (cobertura asegurada).
    4. Crea las filas `Leccion` con el `orden` y el rango de páginas correctos.
    """
    # 1. Fragmentos del libro
    result = await db.execute(
        select(Fragmento)
        .where(Fragmento.libro_id == libro_id)
        .order_by(Fragmento.numero_pagina, Fragmento.id)
    )
    fragmentos = list(result.scalars().all())
    if not fragmentos:
        logger.warning("[Lecciones] Libro %s sin fragmentos; no se generan lecciones", libro_id)
        return []

    num_lecciones = _calcular_num_lecciones(fragmentos)
    segmentos = _segmentar(fragmentos, num_lecciones)
    n = len(segmentos)
    logger.info(
        "[Lecciones] Libro %s: %d segmentos para %d páginas de contenido (%s a %s)",
        libro_id, n, len({f.numero_pagina for f in fragmentos}),
        segmentos[0]["ini"], segmentos[-1]["fin"],
    )

    # 2/3. Nombrar cada segmento con una llamada propia (evita que el LLM arrastre
    # el tema de las primeras páginas) y persistir. El rango de páginas lo fija la
    # segmentación; el LLM solo aporta nombre/descripción/tema.
    sin_nombre = 0
    creadas: list[Leccion] = []
    for i, seg in enumerate(segmentos, start=1):
        item = _parsear(
            llm_client.generate_json(
                _build_messages_segmento(seg, i, n), max_tokens=512, model=MODELO_RUTA
            )
        )
        if item is None:
            item = _parsear(
                llm_client.generate_json(
                    _build_messages_segmento(seg, i, n, estricto=True),
                    max_tokens=512,
                    model=MODELO_RUTA,
                )
            )

        if item is not None:
            nombre = (item.nombre or f"Lección {i}").strip()[:300]
            descripcion = item.descripcion
            tema_clave = (item.tema_clave or "general").strip()[:200] or "general"
        else:
            sin_nombre += 1
            nombre = f"Lección {i}: Páginas {seg['paginas']}"
            descripcion = f"Contenido de las páginas {seg['paginas']} del libro."
            tema_clave = "general"

        leccion = Leccion(
            libro_id=libro_id,
            nombre=nombre,
            descripcion=descripcion,
            orden=i,
            tema_clave=tema_clave,
            paginas=seg["paginas"][:50],
        )
        db.add(leccion)
        creadas.append(leccion)

    await db.commit()
    if sin_nombre:
        logger.warning(
            "[Lecciones] %d de %d segmentos quedaron con nombre genérico (libro %s)",
            sin_nombre, len(creadas), libro_id,
        )
    logger.info("[Lecciones] %d lecciones creadas para libro %s", len(creadas), libro_id)
    return creadas


async def libro_tiene_lecciones(libro_id: int, db: AsyncSession) -> bool:
    """True si el libro ya tiene al menos una lección (evita duplicar)."""
    result = await db.execute(
        select(func.count()).select_from(Leccion).where(Leccion.libro_id == libro_id)
    )
    return (result.scalar_one() or 0) > 0
