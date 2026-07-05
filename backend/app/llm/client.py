"""
Cliente del modelo de lenguaje (Together AI).
Soporta: chat (respuesta completa), generación JSON (para actividades).
"""
import json
import logging

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


class LLMClient:
    def __init__(self) -> None:
        self.model = settings.LLM_MODEL
        self._client = Together(api_key=settings.TOGETHER_API_KEY)

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

    def generate_json(
        self, messages: list[dict], max_tokens: int = 2048, model: str | None = None
    ) -> dict | None:
        """
        Pide al LLM que genere JSON estricto. Usado para crear actividades.
        Devuelve el dict parseado, o None si falla el parseo.

        `model` permite usar un modelo distinto al por defecto (p. ej. uno más
        potente para la generación de la ruta de lecciones, que ocurre una sola
        vez por libro). Si es None, usa el modelo por defecto (`self.model`).
        """
        resp = self._client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,  # Baja temperatura para JSON más consistente
        )
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
