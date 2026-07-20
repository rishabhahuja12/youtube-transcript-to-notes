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


def store_provider_pool(pool_json: str) -> bool:
    """Store the serialized pool JSON in keyring."""
    return store_credential(KEY_PROVIDER_POOL, pool_json)


def get_provider_pool() -> str:
    """Retrieve the pool JSON from keyring."""
    return get_credential(KEY_PROVIDER_POOL)


def get_provider_pool_or_legacy() -> "ProviderPool":
    """Load the provider pool from keyring.
    Returns an empty ProviderPool if nothing is stored."""
    from src.provider_pool import ProviderPool

    pool_json = get_provider_pool()
    if pool_json:
        return ProviderPool.from_json(pool_json)

    # Attempt legacy migration if no pool exists
    legacy_key = get_credential(KEY_API_KEY)
    if legacy_key:
        provider = get_credential(KEY_PROVIDER) or "groq"
        url = get_credential(KEY_ENDPOINT_URL)
        model = get_credential(KEY_MODEL_NAME)
        
        pool = ProviderPool.from_legacy(provider, url, legacy_key, model)
        # Save immediately to the new format so we don't need to migrate again
        store_provider_pool(pool.to_json())
        return pool

    return ProviderPool([])

