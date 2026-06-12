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
    agenthub_cloud_runtime_seconds: int = 600
    agenthub_cloud_concurrent_runs: int = 4
    agenthub_cloud_memory_mb: int = 1024
    agenthub_cloud_disk_mb: int = 1024
    agenthub_runner_provider: str = "local_dev"
    agenthub_runtime_image: str = "agenthub/default-cli:phase15"
    agenthub_runtime_images: str = ""
    agenthub_deployment_provider: str = "static_site"
    agenthub_deployment_root: str = "./data/deployments"
    agenthub_deployment_public_base_url: str = ""
    agenthub_deployment_max_bytes: int = 20 * 1024 * 1024
    agenthub_runner_region: str = "local"
    agenthub_runner_network_policy: str = "bridge"
    agenthub_runner_cpu: float = 1.0
    agenthub_runner_docker_binary: str = "docker"
    agenthub_runner_docker_host: str = ""
    agenthub_runner_ssh_host: str = ""
    agenthub_runner_ssh_port: int = 22
    agenthub_runner_ssh_user: str = "root"
    agenthub_runner_ssh_password: str = ""
    agenthub_runner_ssh_workspace_root: str = "/tmp/agenthub/workspaces"
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
