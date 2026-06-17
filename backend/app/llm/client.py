"""
Cliente del modelo de lenguaje (Together AI).

IMPORTANTE (reconciliación con la tesis):
El modelo se lee desde settings.LLM_MODEL. Hoy apunta al modelo BASE
(Qwen/Qwen2.5-7B-Instruct-Turbo). El día que subas tu adaptador LoRA propio
a Together AI, solo cambias LLM_MODEL en el .env. Ni una línea de código más.
"""
from together import Together

from app.config import settings


class LLMClient:
    def __init__(self) -> None:
        self.model = settings.LLM_MODEL
        self._client = Together(api_key=settings.TOGETHER_API_KEY)

    def hello(self) -> str:
        """Llamada de prueba: el 'hola mundo' del Sprint 0."""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un tutor escolar amable de un colegio de Guatemala. "
                        "Respondes en español, claro y breve."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Saluda a un estudiante de primaria y dile en una sola "
                        "frase que estás listo para ayudarlo a estudiar."
                    ),
                },
            ],
            max_tokens=120,
            temperature=0.7,
        )
        return resp.choices[0].message.content


# Instancia única reutilizable en toda la app
llm_client = LLMClient()
