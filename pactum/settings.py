from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    database_url: str = "postgresql://pactum:pactum@localhost:5432/pactum"

    model_config = {"env_file": ".env"}

    @model_validator(mode="after")
    def check_groq_api_key_is_set(self) -> "Settings":
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set in .env")
        return self


settings = Settings()
