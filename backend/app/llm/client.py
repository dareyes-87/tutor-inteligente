"""
Cliente del modelo de lenguaje (Together AI).
Soporta: chat (respuesta completa), generación JSON (para actividades).
"""
import json
import logging

from together import Together

from app.config import settings

logger = logging.getLogger(__name__)


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

    def chat(self, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.7) -> str:
        """
        Envía una conversación al LLM y devuelve la respuesta completa.
        Usado por el módulo de Chat para las respuestas del tutor.
        """
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content

    def generate_json(self, messages: list[dict], max_tokens: int = 2048) -> dict | None:
        """
        Pide al LLM que genere JSON estricto. Usado para crear actividades.
        Devuelve el dict parseado, o None si falla el parseo.
        """
        resp = self._client.chat.completions.create(
            model=self.model,
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
