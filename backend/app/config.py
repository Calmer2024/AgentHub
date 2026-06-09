from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    database_url: str = "sqlite+aiosqlite:///./data/agenthub.db"
    agenthub_workspace_root: str = "./data/workspaces"
    agenthub_skill_roots: str = ""
    agenthub_secret_key: str = "agenthub-dev-secret"
    agenthub_cloud_runner_node_id: str = "local-dev-runner"
    agenthub_cloud_runtime_seconds: int = 30
    agenthub_cloud_concurrent_runs: int = 2
    agenthub_cloud_memory_mb: int = 1024
    agenthub_cloud_disk_mb: int = 512
    agenthub_edition: str = "local"
    agenthub_surface: str = "desktop"
    agenthub_api_base_url: str = "http://127.0.0.1:8000"
    agenthub_auth_required: bool = False
    agenthub_environment: str = "development"
    agenthub_auth_provider: str = "local_email"
    agenthub_dev_auth_enabled: bool = True
    agenthub_access_token_seconds: int = 15 * 60
    agenthub_refresh_token_days: int = 30
    agenthub_cookie_secure: bool = False
    agenthub_max_upload_bytes: int = 10 * 1024 * 1024
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
