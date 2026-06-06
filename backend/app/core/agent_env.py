import json


BLOCKED_AGENT_ENV_KEYS = {
    "API_KEY",
}

CODEX_ALLOWED_SENSITIVE_ENV_KEYS = {
    "AGENTHUB_CODEX_API_KEY",
}


def allowed_sensitive_env_keys_for_cli(cli_tool: str | None) -> set[str]:
    if cli_tool == "codex":
        return set(CODEX_ALLOWED_SENSITIVE_ENV_KEYS)
    return set()


def clean_cli_agent_env(
    raw: dict[str, str] | str | None,
    *,
    allowed_sensitive_keys: set[str] | None = None,
) -> dict[str, str]:
    """Return user-visible CLI env overrides with sensitive keys removed."""
    env = _decode_env(raw)
    allowed = {key.strip().upper() for key in (allowed_sensitive_keys or set())}
    return {
        key: value
        for key, value in env.items()
        if value and not is_blocked_agent_env_key(key, allowed_sensitive_keys=allowed)
    }


def encode_cli_agent_env(
    raw: dict[str, str] | str | None,
    *,
    allowed_sensitive_keys: set[str] | None = None,
) -> str:
    return json.dumps(
        clean_cli_agent_env(raw, allowed_sensitive_keys=allowed_sensitive_keys),
        ensure_ascii=False,
    )


def is_blocked_agent_env_key(
    key: str,
    *,
    allowed_sensitive_keys: set[str] | None = None,
) -> bool:
    normalized = str(key).strip().upper()
    if normalized in {item.strip().upper() for item in (allowed_sensitive_keys or set())}:
        return False
    return normalized in BLOCKED_AGENT_ENV_KEYS or normalized.endswith("_API_KEY")


def _decode_env(raw: dict[str, str] | str | None) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        return {}
    return {str(k).strip(): str(v) for k, v in parsed.items() if str(k).strip()}
