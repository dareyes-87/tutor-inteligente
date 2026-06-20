"""Lógica de negocio del módulo de actividades."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actividad import Actividad, ResultadoActividad, TipoActividad
from app.models.perfil_comprension import PerfilComprension
from app.models.asignatura import Asignatura
from app.models.grado import Grado
from app.models.usuario import Usuario
from app.modules.rag.search import search_fragments, is_context_relevant
from app.modules.chat.prompts import build_context_prompt
from app.modules.actividades.generator import generar_actividad
from app.modules.actividades.evaluator import evaluar_actividad

logger = logging.getLogger(__name__)


async def crear_actividad(
    db: AsyncSession,
    asignatura_id: int,
    tipo: TipoActividad,
    estudiante: Usuario,
    tema: str | None = None,
) -> Actividad | None:
    """Genera una actividad nueva usando RAG + LLM."""
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

    # Buscar contexto relevante
    query = tema or asignatura.nombre
    fragments = search_fragments(query=query, asignatura=asignatura.nombre, grado=grado_nombre)

    if not fragments:
        logger.warning("No se encontraron fragmentos para generar actividad")
        return None

    # Grounding estricto: no generar actividades sobre temas que no están
    # suficientemente cubiertos por los libros indexados.
    if not is_context_relevant(fragments):
        logger.warning("Contexto no relevante; no se genera actividad (grounding estricto)")
        return None

    context = build_context_prompt(fragments)

    # Generar actividad con el LLM
    result = generar_actividad(tipo, context, tema)
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

    await db.commit()

    return {
        "actividad_id": actividad_id,
        "puntaje": evaluacion["puntaje"],
        "retroalimentacion": evaluacion["retroalimentacion"],
        "respuesta_correcta": actividad.respuesta_correcta,
    }


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
