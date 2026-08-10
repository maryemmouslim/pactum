import pytest
from pydantic import ValidationError

from pactum.settings import Settings


def test_settings_raises_when_groq_api_key_missing() -> None:
    with pytest.raises(ValidationError, match="GROQ_API_KEY is not set"):
        Settings(_env_file=None, groq_api_key="")


def test_settings_succeeds_when_groq_api_key_present() -> None:
    settings = Settings(_env_file=None, groq_api_key="test-key")
    assert settings.groq_api_key == "test-key"


def test_settings_has_sensible_database_url_default() -> None:
    settings = Settings(_env_file=None, groq_api_key="test-key")
    assert settings.database_url == "postgresql+psycopg://pactum:pactum@localhost:5432/pactum"
