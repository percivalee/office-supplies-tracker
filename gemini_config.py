import json
import os
from pathlib import Path

from app_runtime import RUNTIME_DIR


GEMINI_CONFIG_PATH = Path(RUNTIME_DIR) / ".gemini_config.json"
DEFAULT_GEMINI_MODEL_NAME = "gemini-3.0-flash"
DEFAULT_GEMINI_TIMEOUT_SECONDS = 90
MIN_GEMINI_TIMEOUT_SECONDS = 10
MAX_GEMINI_TIMEOUT_SECONDS = 300


def _normalize_timeout(value) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = DEFAULT_GEMINI_TIMEOUT_SECONDS
    if timeout < MIN_GEMINI_TIMEOUT_SECONDS:
        return MIN_GEMINI_TIMEOUT_SECONDS
    if timeout > MAX_GEMINI_TIMEOUT_SECONDS:
        return MAX_GEMINI_TIMEOUT_SECONDS
    return timeout


def load_gemini_config() -> dict:
    if not GEMINI_CONFIG_PATH.exists():
        return {
            "api_key": "",
            "model_name": DEFAULT_GEMINI_MODEL_NAME,
            "request_timeout_seconds": DEFAULT_GEMINI_TIMEOUT_SECONDS,
        }
    try:
        raw = GEMINI_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("invalid config format")
        return {
            "api_key": str(data.get("api_key") or "").strip(),
            "model_name": str(data.get("model_name") or DEFAULT_GEMINI_MODEL_NAME).strip() or DEFAULT_GEMINI_MODEL_NAME,
            "request_timeout_seconds": _normalize_timeout(data.get("request_timeout_seconds")),
        }
    except (OSError, json.JSONDecodeError, ValueError):
        return {
            "api_key": "",
            "model_name": DEFAULT_GEMINI_MODEL_NAME,
            "request_timeout_seconds": DEFAULT_GEMINI_TIMEOUT_SECONDS,
        }


def save_gemini_config(config: dict) -> dict:
    current = load_gemini_config()
    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        api_key = current.get("api_key", "")

    model_name = str(config.get("model_name") or "").strip() or current.get("model_name") or DEFAULT_GEMINI_MODEL_NAME
    timeout = _normalize_timeout(config.get("request_timeout_seconds"))

    normalized = {
        "api_key": api_key,
        "model_name": model_name,
        "request_timeout_seconds": timeout,
    }

    GEMINI_CONFIG_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        GEMINI_CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
    return normalized


def public_gemini_config(config: dict) -> dict:
    model_name = str(config.get("model_name") or DEFAULT_GEMINI_MODEL_NAME).strip() or DEFAULT_GEMINI_MODEL_NAME
    timeout = _normalize_timeout(config.get("request_timeout_seconds"))
    has_api_key = bool(str(config.get("api_key") or "").strip())
    return {
        "configured": has_api_key,
        "has_api_key": has_api_key,
        "model_name": model_name,
        "request_timeout_seconds": timeout,
    }


def resolve_gemini_settings(api_key_override: str | None = None) -> tuple[str, str, int]:
    config = load_gemini_config()
    env_api_key = str(os.getenv("GEMINI_API_KEY") or "").strip()
    env_model_name = str(os.getenv("GEMINI_MODEL_NAME") or "").strip()
    env_timeout = os.getenv("GEMINI_REQUEST_TIMEOUT_SECONDS")

    override_key = str(api_key_override or "").strip()
    api_key = override_key or env_api_key or str(config.get("api_key") or "").strip()
    model_name = env_model_name or str(config.get("model_name") or DEFAULT_GEMINI_MODEL_NAME).strip() or DEFAULT_GEMINI_MODEL_NAME
    timeout = _normalize_timeout(env_timeout if env_timeout is not None else config.get("request_timeout_seconds"))
    return api_key, model_name, timeout
