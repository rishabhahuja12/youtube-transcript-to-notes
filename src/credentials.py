"""
Secure credential storage using the system keyring.

On Windows, this uses Windows Credential Manager.
Credentials are stored/retrieved by service name 'yt-transcriptor'.
"""
import os

SERVICE_NAME = "yt-transcriptor"

# Keys stored in keyring
KEY_API_KEY = "api_key"
KEY_ENDPOINT_URL = "endpoint_url"
KEY_MODEL_NAME = "model_name"
KEY_PROVIDER = "provider"
KEY_PROVIDER_POOL = "provider_pool"


def _get_keyring():
    """Lazy import keyring to avoid ImportError if not installed."""
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def is_keyring_available() -> bool:
    """Check if keyring library is installed and functional."""
    kr = _get_keyring()
    if kr is None:
        return False
    try:
        # Quick test to make sure the backend works
        kr.get_password(SERVICE_NAME, "__test__")
        return True
    except Exception:
        return False


def store_credential(key: str, value: str) -> bool:
    """Store a credential in the system keyring.
    Returns True on success, False on failure."""
    kr = _get_keyring()
    if kr is None:
        return False
    try:
        if not value:
            try:
                kr.delete_password(SERVICE_NAME, key)
            except Exception:
                pass
            return True
        kr.set_password(SERVICE_NAME, key, value)
        return True
    except Exception:
        return False


def get_credential(key: str) -> str:
    """Retrieve a credential from the system keyring.
    Returns the value or empty string if not found."""
    kr = _get_keyring()
    if kr is None:
        return ""
    try:
        val = kr.get_password(SERVICE_NAME, key)
        return val or ""
    except Exception:
        return ""


def delete_credential(key: str) -> bool:
    """Delete a credential from the system keyring."""
    kr = _get_keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE_NAME, key)
        return True
    except Exception:
        return False


def store_all_credentials(provider: str, endpoint_url: str, api_key: str, model_name: str) -> bool:
    """Store all LLM credentials at once."""
    results = [
        store_credential(KEY_PROVIDER, provider),
        store_credential(KEY_ENDPOINT_URL, endpoint_url),
        store_credential(KEY_API_KEY, api_key),
        store_credential(KEY_MODEL_NAME, model_name),
    ]
    return all(results)


def get_all_credentials() -> dict:
    """Retrieve all stored LLM credentials.
    Returns dict with keys: provider, endpoint_url, api_key, model_name.
    Values are empty strings if not found."""
    return {
        "provider": get_credential(KEY_PROVIDER),
        "endpoint_url": get_credential(KEY_ENDPOINT_URL),
        "api_key": get_credential(KEY_API_KEY),
        "model_name": get_credential(KEY_MODEL_NAME),
    }


def has_stored_credentials() -> bool:
    """Check if any credentials are stored."""
    creds = get_all_credentials()
    return bool(creds["endpoint_url"] and creds["model_name"])


def get_llm_config_from_keyring() -> tuple:
    """Get LLM config from keyring, matching the signature of config.get_llm_config.
    Returns (provider, endpoint_url, api_key, model_name)."""
    creds = get_all_credentials()
    return (
        creds["provider"] or "Groq",
        creds["endpoint_url"],
        creds["api_key"],
        creds["model_name"],
    )


def store_provider_pool(pool_json: str) -> bool:
    """Store the serialized pool JSON in keyring."""
    return store_credential(KEY_PROVIDER_POOL, pool_json)


def get_provider_pool() -> str:
    """Retrieve the pool JSON from keyring."""
    return get_credential(KEY_PROVIDER_POOL)


def get_provider_pool_or_legacy() -> "ProviderPool":
    """Try loading the pool first. If empty, fall back to legacy single-config.
    Returns ProviderPool."""
    import os
    from src.provider_pool import ProviderPool
    from src.config import get_llm_config
    
    pool_json = get_provider_pool()
    if pool_json:
        pool = ProviderPool.from_json(pool_json)
        if pool.total > 0:
            return pool
    
    # Fallback to legacy (keyring then .env via get_llm_config)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(script_dir, ".env")
    prov, ep, key, mod = get_llm_config(env_path)
    return ProviderPool.from_legacy(prov, ep, key, mod)
