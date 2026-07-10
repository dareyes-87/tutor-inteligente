"""Lógica de negocio del módulo de actividades."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actividad import Actividad, ResultadoActividad, TipoActividad
from app.models.perfil_comprension import PerfilComprension
from app.models.asignatura import Asignatura
from app.models.fragmento import Fragmento
from app.models.grado import Grado
from app.models.leccion import Leccion
from app.models.usuario import Usuario
from app.modules.rag.search import es_ejercicio_del_libro, is_context_relevant, search_fragments
from app.modules.chat.prompts import build_context_prompt
from app.modules.actividades.generator import generar_actividad
from app.modules.actividades.evaluator import evaluar_actividad
from app.modules.lecciones.service import actualizar_racha

logger = logging.getLogger(__name__)


def _parsear_rango_paginas(paginas: str | None) -> tuple[int, int] | None:
    """Convierte un rango de páginas tipo '18-22' (o '18') a (ini, fin)."""
    if not paginas:
        return None
    partes = paginas.replace(" ", "").split("-")
    try:
        nums = [int(p) for p in partes if p]
    except ValueError:
        return None
    if not nums:
        return None
    return (min(nums), max(nums))


async def crear_actividad(
    db: AsyncSession,
    asignatura_id: int,
    tipo: TipoActividad,
    estudiante: Usuario,
    tema: str | None = None,
    leccion_id: int | None = None,
    fragment_ids: list[int] | None = None,
    evitar_preguntas: list[str] | None = None,
    conceptos_estudiados: list[str] | None = None,
) -> Actividad | None:
    """Genera una actividad nueva usando RAG + LLM.

    Tres modos de obtener el contexto (en orden de prioridad):
      1. `fragment_ids`: usa EXACTAMENTE esos fragmentos (los que el tutor explicó
         en la micro-lección). Alinea teoría y práctica.
      2. `leccion_id`: usa los fragmentos del rango de páginas de la lección.
      3. ninguno: búsqueda semántica por tema + grounding estricto.

    En los modos 1 y 2 NO se aplica el grounding estricto: el contenido proviene
    de una lección del libro, así que ya está garantizado que es "del libro"
    (era la causa de los 500 "contexto no relevante" en /practicar).

    `conceptos_estudiados` (Enfoque A) es ortogonal a los tres modos: si viene,
    ACOTA la pregunta a los conceptos que el tutor explicó en la micro-lección
    (no a cualquier detalle de los fragmentos). Vacío = comportamiento anterior.
    """
    # Obtener nombres para filtrar RAG
    asig = await db.execute(select(Asignatura).where(Asignatura.id == asignatura_id))
    asignatura = asig.scalar_one_or_none()
    if not asignatura:
        return None

    grado_nombre = None
    grado_id = estudiante.grado_id or 1
    if estudiante.grado_id:
        gr = await db.execute(select(Grado).where(Grado.id == estudiante.grado_id))
        grado = gr.scalar_one_or_none()
        grado_nombre = grado.nombre if grado else None

    # Si viene una lección, resolverla para fijar el tema (perfil de comprensión)
    # y tener su rango de páginas disponible como fallback.
    leccion = None
    if leccion_id is not None:
        leccion = (
            await db.execute(select(Leccion).where(Leccion.id == leccion_id))
        ).scalar_one_or_none()
        if leccion is not None:
            tema = tema or leccion.tema_clave or leccion.nombre

    fragments: list[dict] = []
    usar_grounding = True

    # Modo 1: fragmentos explícitos de la micro-lección.
    if fragment_ids:
        rows = (
            await db.execute(
                select(Fragmento)
                .where(Fragmento.id.in_(fragment_ids))
                .order_by(Fragmento.numero_pagina, Fragmento.id)
            )
        ).scalars().all()
        fragments = [{"page_num": r.numero_pagina, "text": r.contenido_texto} for r in rows]
        # Filtrar ejercicios del libro (Mesa lista, Ahora es tu turno…): el LLM
        # los copia como si fueran teoría. No cambia qué se recupera, solo qué
        # de lo recuperado se usa como contexto.
        fragments = [f for f in fragments if not es_ejercicio_del_libro(f["text"])]
        if fragments:
            usar_grounding = False

    # Modo 2: fragmentos del rango de páginas de la lección (fallback si no hubo
    # fragment_ids o quedaron vacíos).
    if not fragments and leccion is not None:
        rango = _parsear_rango_paginas(leccion.paginas)
        if rango is not None:
            ini, fin = rango
            rows = (
                await db.execute(
                    select(Fragmento)
                    .where(
                        Fragmento.libro_id == leccion.libro_id,
                        Fragmento.numero_pagina >= ini,
                        Fragmento.numero_pagina <= fin,
                    )
                    .order_by(Fragmento.numero_pagina, Fragmento.id)
                )
            ).scalars().all()
            fragments = [
                {"page_num": r.numero_pagina, "text": r.contenido_texto} for r in rows
            ]
            fragments = [f for f in fragments if not es_ejercicio_del_libro(f["text"])]
            if fragments:
                usar_grounding = False

    # Modo 3: búsqueda semántica (sin lección / sin fragmentos).
    if not fragments:
        query = tema or asignatura.nombre
        fragments = search_fragments(
            query=query, asignatura=asignatura.nombre, grado=grado_nombre
        )
        fragments = [f for f in fragments if not es_ejercicio_del_libro(f.get("text", ""))]

    if not fragments:
        logger.warning("No se encontraron fragmentos para generar actividad")
        return None

    # Grounding estricto SOLO para búsqueda semántica libre (modo 3).
    if usar_grounding and not is_context_relevant(fragments):
        logger.warning("Contexto no relevante; no se genera actividad (grounding estricto)")
        return None

    context = build_context_prompt(fragments)

    # Generar actividad con el LLM. `tipo` puede cambiar si el guardrail forzó
    # opcion_multiple (ver generar_actividad): usar SIEMPRE el tipo efectivo
    # para dar forma a contenido/respuesta_correcta y para guardar la actividad.
    tipo, result = generar_actividad(
        tipo, context, tema, evitar_preguntas, asignatura.nombre, grado_nombre,
        conceptos_estudiados,
    )
    if not result:
        return None

    # Separar contenido (lo que ve el estudiante) de respuesta correcta
    respuesta_correcta = {}
    contenido = {}

    if tipo == TipoActividad.opcion_multiple:
        contenido = {"pregunta": result.get("pregunta"), "opciones": result.get("opciones")}
        respuesta_correcta = {"respuesta_correcta": result.get("respuesta_correcta"), "explicacion": result.get("explicacion")}
    elif tipo == TipoActividad.verdadero_falso:
        contenido = {"afirmacion": result.get("afirmacion")}
        respuesta_correcta = {"respuesta_correcta": result.get("respuesta_correcta"), "explicacion": result.get("explicacion")}
    elif tipo == TipoActividad.completar:
        contenido = {"oracion": result.get("oracion"), "pista": result.get("pista")}
        respuesta_correcta = {"respuesta_correcta": result.get("respuesta_correcta")}
    elif tipo == TipoActividad.ordenar:
        contenido = {"instruccion": result.get("instruccion"), "elementos_desordenados": result.get("elementos_desordenados")}
        respuesta_correcta = {"orden_correcto": result.get("orden_correcto"), "explicacion": result.get("explicacion")}
    elif tipo == TipoActividad.respuesta_corta:
        contenido = {"pregunta": result.get("pregunta")}
        respuesta_correcta = {"respuesta_correcta": result.get("respuesta_correcta"), "palabras_clave": result.get("palabras_clave", []), "explicacion": result.get("explicacion")}

    # Determinar tema de los fragmentos
    tema_actividad = tema or (fragments[0].get("asignatura", "General") if fragments else "General")

    actividad = Actividad(
        asignatura_id=asignatura_id,
        grado_id=grado_id,
        tipo=tipo,
        tema=tema_actividad,
        contenido=contenido,
        respuesta_correcta=respuesta_correcta,
    )
    db.add(actividad)
    await db.commit()
    await db.refresh(actividad)

    logger.info(f"Actividad {tipo.value} creada (id={actividad.id})")
    return actividad


async def responder_actividad(
    db: AsyncSession,
    actividad_id: int,
    respuesta_estudiante: dict,
    estudiante_id: int,
) -> dict | None:
    """Evalúa la respuesta del estudiante y actualiza su perfil."""
    result = await db.execute(select(Actividad).where(Actividad.id == actividad_id))
    actividad = result.scalar_one_or_none()
    if not actividad:
        return None

    # Evaluar
    evaluacion = evaluar_actividad(
        tipo=actividad.tipo,
        respuesta_estudiante=respuesta_estudiante,
        respuesta_correcta=actividad.respuesta_correcta,
        contenido=actividad.contenido,
    )

    # Guardar resultado
    resultado = ResultadoActividad(
        actividad_id=actividad_id,
        estudiante_id=estudiante_id,
        respuesta_estudiante=respuesta_estudiante,
        puntaje=evaluacion["puntaje"],
        retroalimentacion=evaluacion["retroalimentacion"],
    )
    db.add(resultado)

    # Actualizar perfil de comprensión
    await _actualizar_perfil(
        db, estudiante_id, actividad.asignatura_id,
        actividad.tema or "General", evaluacion["puntaje"],
    )

    # Gamificación: responder una actividad cuenta como "usar la app hoy" para la racha.
    await actualizar_racha(estudiante_id, db)

    await db.commit()

    # Se arma la respuesta ANTES de la integración: si esta falla y hace
    # rollback (que expira los objetos), el return no necesita tocar la BD.
    respuesta = {
        "actividad_id": actividad_id,
        "puntaje": evaluacion["puntaje"],
        "retroalimentacion": evaluacion["retroalimentacion"],
        "respuesta_correcta": actividad.respuesta_correcta,
    }

    # NOTA (sistema de 3 niveles): la progresión de la lección, la racha y los
    # puntos YA NO se actualizan por cada actividad respondida. Eso lo decide
    # ahora el endpoint POST /lecciones/{id}/completar-actividad (service
    # completar_nivel), que se llama UNA vez al final de la práctica con el nivel
    # y cuántas actividades se aprobaron. Aquí solo se califica la actividad y se
    # actualiza el perfil de comprensión (que lee GET /actividades/perfil).
    return respuesta


async def _actualizar_perfil(
    db: AsyncSession,
    estudiante_id: int,
    asignatura_id: int,
    tema: str,
    nuevo_puntaje: float,
):
    """Actualiza o crea el perfil de comprensión del estudiante."""
    result = await db.execute(
        select(PerfilComprension).where(
            PerfilComprension.estudiante_id == estudiante_id,
            PerfilComprension.asignatura_id == asignatura_id,
            PerfilComprension.tema == tema,
        )
    )
    perfil = result.scalar_one_or_none()

    if perfil:
        # Recalcular promedio
        total = perfil.total_actividades
        perfil.puntaje_promedio = (
            (perfil.puntaje_promedio * total + nuevo_puntaje) / (total + 1)
        )
        perfil.total_actividades = total + 1
        perfil.fecha_actualizacion = datetime.now(timezone.utc)
    else:
        perfil = PerfilComprension(
            estudiante_id=estudiante_id,
            asignatura_id=asignatura_id,
            tema=tema,
            puntaje_promedio=nuevo_puntaje,
            total_actividades=1,
        )
        db.add(perfil)


async def obtener_perfil_estudiante(
    db: AsyncSession, estudiante_id: int
) -> list[dict]:
    """Obtiene el perfil de comprensión completo de un estudiante."""
    result = await db.execute(
        select(PerfilComprension, Asignatura.nombre)
        .join(Asignatura, PerfilComprension.asignatura_id == Asignatura.id)
        .where(PerfilComprension.estudiante_id == estudiante_id)
        .order_by(Asignatura.nombre, PerfilComprension.tema)
    )
    rows = result.all()
    return [
        {
            "asignatura": nombre,
            "tema": perfil.tema,
            "puntaje_promedio": round(perfil.puntaje_promedio, 1),
            "nivel": perfil.nivel,
            "total_actividades": perfil.total_actividades,
        }
        for perfil, nombre in rows
    ]
