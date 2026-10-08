from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    openrouter_api_key: str
    openrouter_model: str = "anthropic/claude-haiku-5.5"
    database_url: str
    style_path: Path = Path("style.md")
