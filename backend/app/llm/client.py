"""
Cliente del modelo de lenguaje (Together AI).
Soporta: chat (respuesta completa), generación JSON (para actividades).
"""
import json
import logging
import time

import httpx
from together import Together

from app.config import settings

logger = logging.getLogger(__name__)

# Modelo más capaz (aritmética/razonamiento) para Matemáticas. El Qwen 7B por
# defecto no calcula de forma confiable (ver 9 rondas de guardrails), así que
# para Matemáticas se usa el 70B —el mismo que ya genera la ruta de lecciones—
# en actividades, micro-lecciones, retroalimentación y chat. El resto de
# asignaturas sigue con el Qwen 7B (más barato y suficiente para texto).
MODELO_MATEMATICAS = "meta-llama/Llama-3.3-70B-Instruct-Turbo"


def modelo_para_asignatura(asignatura_nombre: str | None) -> str | None:
    """Modelo a usar según la asignatura: el 70B para Matemáticas, o None
    (= modelo por defecto, Qwen 7B) para las demás. Se decide por NOMBRE
    ("matem", robusto al acento y a cambios de asignatura_id)."""
    if asignatura_nombre and "matem" in asignatura_nombre.lower():
        return MODELO_MATEMATICAS
    return None


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
        self.model = settings.LLM_MODEL
        self._client = Together(
            api_key=settings.TOGETHER_API_KEY,
            timeout=LLM_TIMEOUT_SEGUNDOS,
            max_retries=LLM_MAX_REINTENTOS,
        )

    def hello(self) -> str:
        """Llamada de prueba (Sprint 0)."""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Eres un tutor escolar amable de Guatemala. Responde en español, claro y breve."},
                {"role": "user", "content": "Saluda a un estudiante y dile que estás listo para ayudarlo."},
            ],
            max_tokens=120,
            temperature=0.7,
        )
        return resp.choices[0].message.content

    def chat(
        self, messages: list[dict], max_tokens: int = 1024,
        temperature: float = 0.7, model: str | None = None,
    ) -> str:
        """
        Envía una conversación al LLM y devuelve la respuesta completa.
        Usado por el módulo de Chat para las respuestas del tutor.

        `model` permite forzar un modelo distinto al por defecto (p. ej. el 70B
        para el chat de Matemáticas). Si es None, usa `self.model`.
        """
        resp = self._client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content

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
        self, messages: list[dict], max_tokens: int = 2048, model: str | None = None
    ) -> dict | None:
        """
        Pide al LLM que genere JSON estricto. Usado para crear actividades.
        Devuelve el dict parseado, o None si falla el parseo.

        `model` permite usar un modelo distinto al por defecto (p. ej. uno más
        potente para la generación de la ruta de lecciones, que ocurre una sola
        vez por libro). Si es None, usa el modelo por defecto (`self.model`).

        Cualquier error del API (timeout, red, 5xx tras agotar reintentos) se
        captura y devuelve None: el llamador ya trata None como "no se pudo
        generar" y reintenta/degrada, en vez de propagar una excepción que se
        convertiría en un 500 opaco para el estudiante.
        """
        try:
            resp = self._client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,  # Baja temperatura para JSON más consistente
            )
        except Exception as e:  # noqa: BLE001 — degradar ante cualquier fallo del API
            logger.warning(f"Fallo al llamar al LLM (generate_json): {e}")
            return None
        raw = resp.choices[0].message.content.strip()

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
