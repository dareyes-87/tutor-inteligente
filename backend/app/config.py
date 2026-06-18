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

    # --- ChromaDB ---
    CHROMA_HOST: str = "chroma"
    CHROMA_PORT: int = 8000

    # --- Together AI ---
    TOGETHER_API_KEY: str = ""
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct-Turbo"

    # --- JWT ---
    SECRET_KEY: str = "cambia-esto-por-una-clave-larga-y-aleatoria"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Admin seed ---
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # --- Almacenamiento ---
    BOOKS_DIR: str = "/data/books"

    @property
    def database_url_async(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
