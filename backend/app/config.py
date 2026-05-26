from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    minimax_api_key: str = ""
    glm_api_key: str = ""
    openai_model: str = "gpt-4o"
    claude_model: str = "claude-3-5-sonnet-20241022"
    deepseek_model: str = "deepseek-v4-flash"
    gemini_model: str = "gemini-3.5-flash"
    minimax_model: str = "MiniMax-M2.7"
    glm_model: str = "glm-5.1"
    database_url: str = "sqlite+aiosqlite:///./data/agenthub.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
