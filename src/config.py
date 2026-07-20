"""
Configuration loading utilities for the YouTube Transcript to Notes Pipeline.
"""
import os
import json


def get_script_dir():
    """Return the directory containing the main application script."""
    return os.path.dirname(os.path.abspath(__file__))


def get_llm_config(env_path):
    """Load LLM configuration. Keys must only come from keyring.

    Args:
        env_path: Ignored.

    Returns:
        Tuple of (provider, endpoint_url, api_key, model_name).
    """
    from src.credentials import get_llm_config_from_keyring
    
    return get_llm_config_from_keyring()

