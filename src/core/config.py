from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    POSTGRES_USER: str = "darkatlas"
    POSTGRES_PASSWORD: str = "darkatlas"
    POSTGRES_DB: str = "darkatlas"
    POSTGRES_PORT: int = 5433
    DATABASE_URL: str | None = None
    API_KEY: str

    def model_post_init(self, __context: object) -> None:
        if self.DATABASE_URL is None:
            self.DATABASE_URL = (
                f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@localhost:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )


def get_config() -> Config:
    return Config()