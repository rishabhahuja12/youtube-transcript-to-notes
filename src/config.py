"""
Configuration loading utilities for the YouTube Transcript to Notes Pipeline.
"""
import os
import json


def get_script_dir():
    """Return the directory containing the main application script."""
    return os.path.dirname(os.path.abspath(__file__))


def parse_env_file(filepath):
    """Parse a .env file into a dictionary. Ignores comments and blank lines."""
    env_vars = {}
    if not os.path.exists(filepath):
        return env_vars
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        pass
    return env_vars


def get_llm_config(env_path):
    """Load LLM configuration. First checks system keyring, falls back to .env file.

    Args:
        env_path: Path to the .env file.

    Returns:
        Tuple of (provider, endpoint_url, api_key, model_name).
    """
    from src.credentials import has_stored_credentials, get_llm_config_from_keyring
    
    if has_stored_credentials():
        return get_llm_config_from_keyring()
        
    env = parse_env_file(env_path)
    provider = env.get("PROVIDER", "Ollama")
    endpoint_url = env.get("ENDPOINT_URL", "http://localhost:11434")
    api_key = env.get("API_KEY", "")
    model_name = env.get("MODEL_NAME", "llama3")
    return provider, endpoint_url, api_key, model_name
