"""
Configuración central del proyecto.
Lee todos los valores desde variables de entorno (archivo .env).
Nunca escribas contraseñas ni API keys directamente en el código.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- PostgreSQL ---
    POSTGRES_USER: str = "tutor"
    POSTGRES_PASSWORD: str = "tutor"
    POSTGRES_DB: str = "tutor"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    # Railway (y otros PaaS) inyectan una sola URL completa. Si está
    # definida, tiene prioridad sobre las variables POSTGRES_* de arriba.
    DATABASE_URL: str = ""

    # --- ChromaDB ---
    CHROMA_HOST: str = "chroma"
    CHROMA_PORT: int = 8000

    # --- Together AI ---
    TOGETHER_API_KEY: str = ""
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct-Turbo"

    # --- Modelo fine-tuned (Modal) — A/B por grado, objetivo específico 3 de tesis ---
    # Vacío = feature apagada (nadie se enruta al fine-tuned). Ver app/llm/client.py.
    MODAL_FINETUNED_URL: str = ""
    MODAL_FINETUNED_MODEL_NAME: str = "tutor-finetuned"
    MODAL_FINETUNED_API_KEY: str = ""
    # IDs de grado (separados por coma) que se enrutan al fine-tuned, p. ej. "3".
    MODAL_FINETUNED_GRADOS: str = ""
    MODAL_FINETUNED_TIMEOUT_SEGUNDOS: float = 200.0

    # --- JWT ---
    SECRET_KEY: str = "cambia-esto-por-una-clave-larga-y-aleatoria"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Admin seed ---
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # --- Almacenamiento ---
    BOOKS_DIR: str = "/data/books"

    @staticmethod
    def _normalizar_esquema(url: str, driver: str) -> str:
        """
        Railway genera URLs con el esquema `postgres://`, pero SQLAlchemy
        necesita `postgresql://`. Además forzamos el driver correcto
        (asyncpg para la app, psycopg para Alembic).
        """
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            pass  # ya está bien
        # Si la URL ya trae un driver explícito (postgresql+algo://) la
        # dejamos tal cual; si no, insertamos el driver que toca.
        if url.startswith("postgresql://"):
            url = "postgresql+" + driver + "://" + url[len("postgresql://"):]
        return url

    @property
    def database_url_async(self) -> str:
        if self.DATABASE_URL:
            return self._normalizar_esquema(self.DATABASE_URL, "asyncpg")
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        if self.DATABASE_URL:
            return self._normalizar_esquema(self.DATABASE_URL, "psycopg")
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
