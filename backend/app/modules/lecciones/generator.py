"""
Generador automático de lecciones (ruta de aprendizaje) a partir del
contenido de un libro ya indexado.

Tras la ingesta, agrupa los fragmentos del libro por página, le pide al LLM
una lista de lecciones ordenadas pedagógicamente y las persiste en la tabla
`leccion`. Si el LLM falla, cae a un fallback determinístico por rango de páginas.
"""
import logging

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import llm_client
from app.models.fragmento import Fragmento
from app.models.leccion import Leccion
from app.modules.lecciones.schemas import LeccionesGeneradas

logger = logging.getLogger(__name__)

# Cuántos caracteres de cada fragmento se le pasan al LLM (control de tokens).
MAX_CHARS_POR_FRAGMENTO = 200
# Tope defensivo del resumen total para no exceder el contexto en libros grandes.
MAX_CHARS_RESUMEN = 24000
# Tamaño de los grupos de páginas en el fallback.
PAGINAS_POR_LECCION_FALLBACK = 5


def _construir_resumen_paginas(fragmentos: list[Fragmento]) -> str:
    """Agrupa los fragmentos por página y arma un resumen breve por página."""
    por_pagina: dict[int, list[str]] = {}
    for f in fragmentos:
        texto = " ".join((f.contenido_texto or "").split())
        por_pagina.setdefault(f.numero_pagina, []).append(texto[:MAX_CHARS_POR_FRAGMENTO])

    partes = []
    for pagina in sorted(por_pagina):
        partes.append(f"Página {pagina}: " + " ".join(por_pagina[pagina]))

    resumen = "\n".join(partes)
    if len(resumen) > MAX_CHARS_RESUMEN:
        logger.info(
            "[Lecciones] Resumen truncado de %d a %d chars",
            len(resumen), MAX_CHARS_RESUMEN,
        )
        resumen = resumen[:MAX_CHARS_RESUMEN]
    return resumen


def _build_messages(resumen_paginas: str, estricto: bool = False) -> list[dict]:
    """Construye los mensajes para el LLM. `estricto` refuerza el reintento."""
    prompt = f"""Eres un experto en diseño curricular. Analiza el siguiente contenido de un libro de texto escolar y genera una lista de lecciones ordenadas pedagógicamente (de lo más básico a lo más avanzado).

CONTENIDO DEL LIBRO (resúmenes por página):
{resumen_paginas}

Genera un JSON con esta estructura exacta:
{{
  "lecciones": [
    {{
      "nombre": "Nombre de la lección (corto, claro, para niños de 8-12 años)",
      "descripcion": "Una oración describiendo qué aprenderá el estudiante",
      "tema_clave": "palabra o frase clave para buscar en la base de datos (1-3 palabras)",
      "paginas": "rango de páginas, ej: 1-5"
    }}
  ]
}}

REGLAS:
- Genera entre 5 y 10 lecciones. Agrupa temas relacionados en una sola lección (ejemplo: "Ruido y Audición" en vez de dos lecciones separadas para ruido y audífonos). Prefiere lecciones que cubran 2-4 páginas cada una sobre lecciones de 1 sola página.
- Cubre TODO el contenido del libro de principio a fin: no omitas páginas ni temas. Si hace falta para no exceder 10 lecciones, agrupa más temas en una misma lección, pero nunca dejes contenido fuera de la ruta.
- Ordénalas pedagógicamente (conceptos básicos primero).
- El tema_clave debe ser específico para buscar en el contenido del libro.
- Los nombres deben ser atractivos para niños.
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


def _parsear(data: dict | None) -> LeccionesGeneradas | None:
    """Valida la salida del LLM contra el schema. Devuelve None si no sirve."""
    if not data:
        return None
    try:
        parsed = LeccionesGeneradas.model_validate(data)
    except ValidationError as e:
        logger.warning("[Lecciones] JSON no cumple el schema esperado: %s", e)
        return None
    if not parsed.lecciones:
        return None
    return parsed


def _fallback(fragmentos: list[Fragmento]) -> list[dict]:
    """Lecciones genéricas por rango de páginas cuando el LLM falla."""
    paginas = sorted({f.numero_pagina for f in fragmentos})
    lecciones = []
    for n, i in enumerate(range(0, len(paginas), PAGINAS_POR_LECCION_FALLBACK), start=1):
        grupo = paginas[i:i + PAGINAS_POR_LECCION_FALLBACK]
        ini, fin = grupo[0], grupo[-1]
        lecciones.append({
            "nombre": f"Lección {n}: Páginas {ini}-{fin}",
            "descripcion": f"Contenido de las páginas {ini} a {fin} del libro.",
            "tema_clave": "general",
            "paginas": f"{ini}-{fin}",
        })
    return lecciones


async def generar_lecciones_desde_libro(libro_id: int, db: AsyncSession) -> list[Leccion]:
    """
    Genera y persiste la ruta de lecciones de un libro.

    1. Lee los fragmentos del libro y los resume por página.
    2. Pide al LLM la lista de lecciones (1 intento + 1 reintento estricto).
    3. Si el LLM falla, usa un fallback por rangos de páginas.
    4. Crea las filas `Leccion` con el `orden` correcto y las devuelve.
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

    resumen = _construir_resumen_paginas(fragmentos)

    # 2. LLM: intento + reintento estricto
    parsed = _parsear(llm_client.generate_json(_build_messages(resumen)))
    if parsed is None:
        logger.info("[Lecciones] JSON inválido para libro %s; reintentando…", libro_id)
        parsed = _parsear(llm_client.generate_json(_build_messages(resumen, estricto=True)))

    # 3. Datos de lecciones (LLM o fallback)
    if parsed is None:
        logger.error("[Lecciones] El LLM no produjo lecciones válidas para libro %s; usando fallback", libro_id)
        lecciones_data = _fallback(fragmentos)
    else:
        lecciones_data = [
            {
                "nombre": l.nombre,
                "descripcion": l.descripcion,
                "tema_clave": l.tema_clave,
                "paginas": l.paginas,
            }
            for l in parsed.lecciones
        ]

    # 4. Persistir con el orden correcto
    creadas: list[Leccion] = []
    for i, ld in enumerate(lecciones_data, start=1):
        nombre = (ld.get("nombre") or f"Lección {i}").strip()[:300]
        tema_clave = (ld.get("tema_clave") or "general").strip()[:200] or "general"
        paginas = ld.get("paginas")
        paginas = paginas[:50] if paginas else None
        leccion = Leccion(
            libro_id=libro_id,
            nombre=nombre,
            descripcion=ld.get("descripcion"),
            orden=i,
            tema_clave=tema_clave,
            paginas=paginas,
        )
        db.add(leccion)
        creadas.append(leccion)

    await db.commit()
    logger.info("[Lecciones] %d lecciones creadas para libro %s", len(creadas), libro_id)
    return creadas


async def libro_tiene_lecciones(libro_id: int, db: AsyncSession) -> bool:
    """True si el libro ya tiene al menos una lección (evita duplicar)."""
    result = await db.execute(
        select(func.count()).select_from(Leccion).where(Leccion.libro_id == libro_id)
    )
    return (result.scalar_one() or 0) > 0
