"""
Keep-warm HÍBRIDO de Modal: evita que el contenedor del modelo fine-tuned
entre en scale-to-zero (scaledown_window=5min en scripts/modal_finetuned/
serve.py) combinando dos señales, para no pagar por horas sin uso real:

1. Ventana base (HORA_INICIO-HORA_FIN): garantizada, para que el contenedor
   ya esté caliente antes de que llegue el primer estudiante típico.
2. Extensión rodante (EXTENSION_MINUTOS): cada vez que un estudiante de la
   cohorte fine-tuned manda una pregunta de chat (ver `registrar_actividad`,
   enganchado desde chat/service.py), el keep-warm se extiende esos minutos
   desde ESE momento — una sesión de uso continuo lo mantiene caliente todo
   el tiempo que dure, sin depender de una ventana de horario fija.

Ambas señales quedan acotadas por FECHA_INICIO/FECHA_FIN (piloto). Apagado
por defecto (MODAL_KEEPWARM_ENABLED=false). Ver MODAL_KEEPWARM_* en
app/config.py.

El ping es a /health del servidor vLLM: NO dispara inferencia real, así que
no consume tokens ni gasta crédito de cómputo más allá de mantener vivo el
contenedor, que es exactamente lo que se busca (el costo de GPU es por
tiempo que el contenedor está arriba, no por request).

Estado en memoria: `_ultima_actividad` vive en una variable de módulo, no en
BD/Redis/archivo (el backend corre con --workers 1, sin condición de carrera
entre procesos). Si Railway reinicia el proceso, se pierde y el keep-warm
cae de nuevo a "solo ventana base" hasta la próxima actividad — peor caso
es un ping de menos, nunca un ping de más ni costo extra.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Guatemala")

# Timestamp (tz-aware) de la última actividad de chat de un estudiante de la
# cohorte fine-tuned. None = sin actividad registrada desde que arrancó el
# proceso (o desde el último reinicio).
_ultima_actividad: datetime | None = None


def registrar_actividad() -> None:
    """Llamar cada vez que un estudiante de la cohorte fine-tuned (grado_id
    en MODAL_FINETUNED_GRADOS) manda una pregunta de chat — ver
    chat/service.py. Extiende (o reinicia, si ya había una activa) la
    ventana rodante de keep-warm por MODAL_KEEPWARM_EXTENSION_MINUTOS desde
    ahora. No hace I/O, no puede fallar."""
    global _ultima_actividad
    _ultima_actividad = datetime.now(_TZ)


def _en_fecha(ahora: datetime) -> bool:
    """True si `ahora` cae dentro del rango de fechas del piloto (vacío en
    un extremo = sin límite en ese extremo). Acota TANTO la ventana base
    como la extensión por actividad, para no seguir gastando crédito fuera
    del período del piloto."""
    if settings.MODAL_KEEPWARM_FECHA_INICIO:
        if ahora.date() < date.fromisoformat(settings.MODAL_KEEPWARM_FECHA_INICIO):
            return False
    if settings.MODAL_KEEPWARM_FECHA_FIN:
        if ahora.date() > date.fromisoformat(settings.MODAL_KEEPWARM_FECHA_FIN):
            return False
    return True


def _en_ventana_base(ahora: datetime) -> bool:
    """True si `ahora` cae en el rango de horas garantizado."""
    return settings.MODAL_KEEPWARM_HORA_INICIO <= ahora.hour < settings.MODAL_KEEPWARM_HORA_FIN


def _en_extension_por_actividad(ahora: datetime) -> bool:
    """True si hubo actividad de un estudiante fine-tuned en los últimos
    MODAL_KEEPWARM_EXTENSION_MINUTOS (ventana rodante)."""
    if _ultima_actividad is None:
        return False
    limite = timedelta(minutes=settings.MODAL_KEEPWARM_EXTENSION_MINUTOS)
    return (ahora - _ultima_actividad) < limite


def _debe_pinguear(ahora: datetime) -> bool:
    if not _en_fecha(ahora):
        return False
    return _en_ventana_base(ahora) or _en_extension_por_actividad(ahora)


async def _ping() -> None:
    """Un solo ping a /health del servidor Modal. Nunca propaga excepción:
    un ping fallido no debe tumbar el loop ni el backend."""
    url = f"{settings.MODAL_FINETUNED_URL.rstrip('/')}/health"
    headers = {"Authorization": f"Bearer {settings.MODAL_FINETUNED_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
        logger.info(f"[KeepWarm] Ping a Modal: status={resp.status_code}")
    except Exception as e:  # noqa: BLE001 — degradar en silencio, ver nota arriba
        logger.warning(f"[KeepWarm] Ping a Modal falló: {e}")


async def keepwarm_loop() -> None:
    """
    Loop de fondo (se lanza una vez desde el lifespan de la app). Cada
    MODAL_KEEPWARM_INTERVALO_SEGUNDOS revisa si `ahora` está en la ventana
    base O en extensión por actividad reciente, y si sí, hace un ping. Si
    MODAL_KEEPWARM_ENABLED es false o no hay MODAL_FINETUNED_URL, retorna de
    inmediato sin hacer nada (no-op).
    """
    if not settings.MODAL_KEEPWARM_ENABLED or not settings.MODAL_FINETUNED_URL:
        logger.info(
            "[KeepWarm] Desactivado (MODAL_KEEPWARM_ENABLED=false o sin MODAL_FINETUNED_URL)"
        )
        return

    logger.info(
        f"[KeepWarm] Activo (híbrido): ventana base {settings.MODAL_KEEPWARM_HORA_INICIO}h-"
        f"{settings.MODAL_KEEPWARM_HORA_FIN}h + extensión rodante de "
        f"{settings.MODAL_KEEPWARM_EXTENSION_MINUTOS}min por actividad "
        f"(America/Guatemala), fechas {settings.MODAL_KEEPWARM_FECHA_INICIO or 'sin límite'} "
        f"a {settings.MODAL_KEEPWARM_FECHA_FIN or 'sin límite'}, cada "
        f"{settings.MODAL_KEEPWARM_INTERVALO_SEGUNDOS}s"
    )
    while True:
        if _debe_pinguear(datetime.now(_TZ)):
            await _ping()
        await asyncio.sleep(settings.MODAL_KEEPWARM_INTERVALO_SEGUNDOS)
