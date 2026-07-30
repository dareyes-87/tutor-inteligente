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

    # --- Keep-warm de Modal (piloto, ventana acotada por presupuesto) ---
    # Apaga por defecto (false). Mientras esté activo, un ping liviano cada
    # MODAL_KEEPWARM_INTERVALO_SEGUNDOS evita el scale-to-zero de Modal
    # (scaledown_window=5min en serve.py). Diseño HÍBRIDO: se pinguea si
    # `ahora` cae en la ventana base (HORA_INICIO-HORA_FIN, garantizada) O si
    # hubo actividad real de un estudiante de la cohorte fine-tuned en los
    # últimos MODAL_KEEPWARM_EXTENSION_MINUTOS (ventana rodante, ver
    # app/workers/modal_keepwarm.py::registrar_actividad). Ambos casos quedan
    # acotados por FECHA_INICIO/FECHA_FIN. Fuera de esto, o con esta variable
    # en false, no se hace ningún ping y el fallback normal a Together AI
    # sigue operando igual que siempre.
    #
    # Todos como `str` (no bool/int): Railway puede tener estas variables
    # creadas pero VACÍAS (pasó justo eso — ver incidente 2026-07-29), y
    # pydantic-settings NO acepta "" para un campo bool/int (ValidationError
    # al arrancar, tumba toda la app). Como `str`, "" es válido y se parsea a
    # mano en modal_keepwarm.py, cayendo al default si viene vacío o inválido.
    MODAL_KEEPWARM_ENABLED: str = "false"
    MODAL_KEEPWARM_HORA_INICIO: str = "14"  # 2pm — ventana base garantizada
    MODAL_KEEPWARM_HORA_FIN: str = "15"  # 3pm (exclusivo) — ventana base garantizada
    MODAL_KEEPWARM_EXTENSION_MINUTOS: str = "15"  # rodante, por actividad real
    MODAL_KEEPWARM_FECHA_INICIO: str = ""  # "2026-08-03", vacío = sin límite
    MODAL_KEEPWARM_FECHA_FIN: str = ""  # "2026-08-09", vacío = sin límite
    MODAL_KEEPWARM_INTERVALO_SEGUNDOS: str = "180"  # 3 min (< 5 min de scaledown)

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
