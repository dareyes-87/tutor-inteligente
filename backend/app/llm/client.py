"""
Cliente del modelo de lenguaje (Together AI).
Soporta: chat (respuesta completa), generación JSON (para actividades).
"""
import json
import logging
import time

import httpx
import together
from together import Together

from app.config import cadenas_modelos, settings

logger = logging.getLogger(__name__)

# Los modelos (y sus respaldos) se eligen por ROL en app/config.py:
# "chat" (resto de asignaturas), "matematicas" (aritmética más confiable) y
# "ruta" (generación de lecciones en la ingesta). Cambiar de modelo es solo
# configuración: LLM_MODEL*, LLM_MODEL*_FALLBACKS.
ROL_POR_DEFECTO = "chat"

# Modelos de razonamiento: el razonamiento consume max_tokens y, si lo agota,
# `content` llega vacío/None (medido 2026-10-28). Para los conocidos se apaga o
# se baja; un modelo que no esté aquí se llama sin parámetros extra.
PARAMS_POR_MODELO: dict[str, dict] = {
    "Qwen/Qwen3.5-9B": {"reasoning": {"enabled": False}},
    "deepseek-ai/DeepSeek-V4.1-Flash": {"reasoning": {"enabled": False}},
    "openai/gpt-oss-120b": {"reasoning_effort": "low"},
    # Con reasoning desactivado Muse-Glimmer devuelve content vacío; "low" sí funciona.
    "meta-models/Muse-Glimmer-30B": {"reasoning_effort": "low"},
}


def rol_para_asignatura(asignatura_nombre: str | None) -> str:
    """Rol de modelo según la asignatura: "matematicas" para Matemáticas, el
    rol por defecto para las demás. Se decide por NOMBRE ("matem", robusto al
    acento y a cambios de asignatura_id)."""
    if asignatura_nombre and "matem" in asignatura_nombre.lower():
        return "matematicas"
    return ROL_POR_DEFECTO


def _modelo_no_disponible(e: Exception) -> bool:
    """True solo si Together dice que el modelo no existe o no es serverless
    (400/404 con code=model_not_available). Timeouts, 5xx y errores de
    contenido NO activan el respaldo."""
    if not isinstance(e, together.APIStatusError) or e.status_code not in (400, 404):
        return False
    error = (e.body or {}).get("error") if isinstance(e.body, dict) else None
    return e.status_code == 404 or (isinstance(error, dict) and error.get("code") == "model_not_available")


def _contenido(resp) -> str | None:
    """Texto de la respuesta, o None si vino vacío (p. ej. un modelo de
    razonamiento que gastó max_tokens razonando)."""
    contenido = resp.choices[0].message.content
    return contenido.strip() or None if contenido else None


def _grados_finetuned() -> set[int]:
    """Parsea MODAL_FINETUNED_GRADOS ("3" o "3,4") a un set de IDs. Vacío = feature apagada."""
    crudo = settings.MODAL_FINETUNED_GRADOS.strip()
    if not crudo:
        return set()
    return {int(g) for g in crudo.split(",") if g.strip().isdigit()}


MODAL_FINETUNED_REINTENTO_SEGUNDOS = 10.0


def grado_usa_finetuned(grado_id: int | None) -> bool:
    """True si el estudiante (por su grado) pertenece a la cohorte experimental
    del modelo fine-tuned (objetivo específico 3 de tesis). Requiere
    MODAL_FINETUNED_URL configurado además del grado en la lista."""
    if not settings.MODAL_FINETUNED_URL or grado_id is None:
        return False
    return grado_id in _grados_finetuned()


# Timeout (segundos) por llamada al API de Together. Sin esto, el SDK usa un
# timeout por defecto muy alto (~600s): si Together se cuelga, la petición queda
# colgada hasta que el gateway de Railway la corta y devuelve un 502 opaco al
# estudiante. Con un timeout acotado + 1 reintento del SDK, una llamada lenta
# falla rápido y de forma controlada (la capa de arriba reintenta o degrada).
LLM_TIMEOUT_SEGUNDOS = 45.0
LLM_MAX_REINTENTOS = 1


class LLMClient:
    def __init__(self) -> None:
        self._client = Together(
            api_key=settings.TOGETHER_API_KEY,
            timeout=LLM_TIMEOUT_SEGUNDOS,
            max_retries=LLM_MAX_REINTENTOS,
        )
        # Modelos que Together ya rechazó como no disponibles en este proceso:
        # se saltan para no pagar la latencia del 400 en cada llamada.
        self._no_disponibles: set[str] = set()

    def _crear(self, rol: str, **kwargs):
        """chat.completions.create con el primer modelo disponible de la cadena
        del rol. Pasa al siguiente SOLO ante "modelo no disponible"; cualquier
        otro error se propaga."""
        cadena = cadenas_modelos()[rol]
        candidatos = [m for m in cadena if m not in self._no_disponibles] or cadena[-1:]
        for i, modelo in enumerate(candidatos):
            try:
                return self._client.chat.completions.create(
                    model=modelo, **PARAMS_POR_MODELO.get(modelo, {}), **kwargs
                )
            except Exception as e:
                if not _modelo_no_disponible(e) or i == len(candidatos) - 1:
                    raise
                self._no_disponibles.add(modelo)
                logger.warning(
                    f"[LLM] Modelo '{modelo}' (rol {rol}) no disponible en Together "
                    f"({e.status_code}); usando respaldo '{candidatos[i + 1]}'"
                )

    def hello(self) -> str | None:
        """Llamada de prueba (Sprint 0)."""
        resp = self._crear(
            ROL_POR_DEFECTO,
            messages=[
                {"role": "system", "content": "Eres un tutor escolar amable de Guatemala. Responde en español, claro y breve."},
                {"role": "user", "content": "Saluda a un estudiante y dile que estás listo para ayudarlo."},
            ],
            max_tokens=120,
            temperature=0.7,
        )
        return _contenido(resp)

    def chat(
        self, messages: list[dict], max_tokens: int = 1024,
        temperature: float = 0.7, rol: str = ROL_POR_DEFECTO,
    ) -> str | None:
        """
        Envía una conversación al LLM y devuelve la respuesta completa, o None
        si vino vacía. Usado por el módulo de Chat para las respuestas del tutor.

        `rol` elige el modelo (ver `rol_para_asignatura`). Los errores del API
        se propagan: el llamador decide la respuesta de respaldo.
        """
        resp = self._crear(rol, messages=messages, max_tokens=max_tokens, temperature=temperature)
        return _contenido(resp)

    def chat_finetuned(
        self, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.7,
    ) -> str:
        """
        Envía la conversación al modelo fine-tuned servido en Modal (endpoint
        OpenAI-compatible vLLM). Usado SOLO para la cohorte experimental (ver
        `grado_usa_finetuned`); el llamador debe capturar excepciones (timeout,
        cold start agotado, contenedor caído) y degradar a `chat()` — nunca debe
        propagarse un error visible al estudiante por esto.

        Modal responde con un 503 fail-fast (no encola) mientras el contenedor
        está "despertando" tras estar inactivo, en vez de hacer esperar al
        cliente. Por eso acá se reintenta cada `MODAL_FINETUNED_REINTENTO_SEGUNDOS`
        hasta agotar `MODAL_FINETUNED_TIMEOUT_SEGUNDOS` en total, en vez de
        degradar al primer fallo: así una pregunta que llega con el contenedor
        frío sí espera el cold start (hasta el límite configurado) y recibe la
        respuesta real del fine-tuned, no un fallback innecesario.

        BLOQUEANTE hasta por `MODAL_FINETUNED_TIMEOUT_SEGUNDOS` (sleep incluido).
        El backend corre con --workers 1: el llamador DEBE ejecutar esto en un
        hilo aparte (`asyncio.to_thread`), o un cold start congelaría el
        servidor entero para todos los estudiantes, no solo para este.
        """
        plazo = settings.MODAL_FINETUNED_TIMEOUT_SEGUNDOS
        inicio = time.monotonic()
        url = f"{settings.MODAL_FINETUNED_URL.rstrip('/')}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.MODAL_FINETUNED_API_KEY}"}
        payload = {
            "model": settings.MODAL_FINETUNED_MODEL_NAME,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        while True:
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception:
                transcurrido = time.monotonic() - inicio
                if transcurrido + MODAL_FINETUNED_REINTENTO_SEGUNDOS >= plazo:
                    raise
                logger.info(
                    f"[Chat] Fine-tuned no listo (cold start?), reintentando "
                    f"en {MODAL_FINETUNED_REINTENTO_SEGUNDOS}s "
                    f"(transcurrido={transcurrido:.0f}s de {plazo:.0f}s)"
                )
                time.sleep(MODAL_FINETUNED_REINTENTO_SEGUNDOS)

    def generate_json(
        self, messages: list[dict], max_tokens: int = 2048, rol: str = ROL_POR_DEFECTO
    ) -> dict | None:
        """
        Pide al LLM que genere JSON estricto. Usado para crear actividades.
        Devuelve el dict parseado, o None ante CUALQUIER fallo.

        `rol` elige el modelo: "ruta" para la generación de lecciones (una vez
        por libro), "matematicas" o el rol por defecto (ver config.py).

        Cualquier error del API (timeout, red, 5xx tras agotar reintentos), una
        respuesta vacía (content=None) o JSON inválido devuelven None: el
        llamador ya trata None como "no se pudo generar" y reintenta/degrada,
        en vez de propagar una excepción que sería un 500 opaco para el estudiante.
        """
        try:
            resp = self._crear(
                rol,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,  # Baja temperatura para JSON más consistente
            )
        except Exception as e:  # noqa: BLE001 — degradar ante cualquier fallo del API
            logger.warning(f"Fallo al llamar al LLM (generate_json): {e}")
            return None
        raw = _contenido(resp)
        if raw is None:
            logger.warning("LLM devolvió una respuesta vacía (generate_json)")
            return None

        # Limpiar si viene envuelto en ```json ... ```
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"LLM devolvió JSON inválido: {raw[:200]}...")
            return None


# Instancia única reutilizable
llm_client = LLMClient()
