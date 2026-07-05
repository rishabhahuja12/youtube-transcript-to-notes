import json
import pytest
from src.provider_pool import ProviderPool, ProviderConfig

def test_provider_pool_single_config():
    config = ProviderConfig(provider="Groq", endpoint_url="http://a", api_key="k1", model_name="m1")
    pool = ProviderPool([config])
    
    assert pool.total == 1
    assert pool.current_index == 1
    assert pool.current_label() == "Config 1/1 (Groq)"
    
    # Rotation on single config exhausts it immediately
    assert pool.rotate() is False
    assert pool.current_index == 1

def test_provider_pool_multiple_configs():
    c1 = ProviderConfig(provider="Groq", endpoint_url="http://a", api_key="k1", model_name="m1")
    c2 = ProviderConfig(provider="Gemini", endpoint_url="http://b", api_key="k2", model_name="m2")
    pool = ProviderPool([c1, c2])
    
    assert pool.total == 2
    assert pool.current_index == 1
    assert pool.current.provider == "Groq"
    
    assert pool.rotate() is True
    assert pool.current_index == 2
    assert pool.current.provider == "Gemini"
    
    assert pool.rotate() is False
    assert pool.current_index == 1
    assert pool.current.provider == "Groq"

def test_provider_pool_reset_cycle():
    c1 = ProviderConfig(provider="Groq", endpoint_url="http://a", api_key="k1", model_name="m1")
    c2 = ProviderConfig(provider="Gemini", endpoint_url="http://b", api_key="k2", model_name="m2")
    pool = ProviderPool([c1, c2])
    
    pool.rotate() # goes to c2
    pool.rotate() # exhausts, back to c1
    
    assert pool.rotate() is False # Still exhausted
    
    pool.reset_cycle()
    assert pool.current.provider == "Groq"
    assert pool.rotate() is True # Can rotate again
    assert pool.current.provider == "Gemini"

def test_provider_pool_json_serialization():
    c1 = ProviderConfig(provider="Groq", endpoint_url="http://a", api_key="k1", model_name="m1")
    pool = ProviderPool([c1])
    
    json_str = pool.to_json()
    assert "Groq" in json_str
    
    pool_loaded = ProviderPool.from_json(json_str)
    assert pool_loaded.total == 1
    assert pool_loaded.current.api_key == "k1"

def test_provider_pool_legacy_migration():
    pool = ProviderPool.from_legacy("Gemini", "http://x", "key123", "gemini-1.5")
    
    assert pool.total == 1
    assert pool.current.provider == "Gemini"
    assert pool.current.endpoint_url == "http://x"
    assert pool.current.api_key == "key123"
    assert pool.current.model_name == "gemini-1.5"

def test_provider_pool_empty():
    pool = ProviderPool([])
    assert pool.total == 0
    assert pool.current_label() == "Empty Pool"
    assert pool.rotate() is False
    with pytest.raises(ValueError):
        _ = pool.current

def test_provider_pool_security():
    c1 = ProviderConfig(provider="Groq", endpoint_url="http://a", api_key="super_secret_key", model_name="m1")
    pool = ProviderPool([c1])
    label = pool.current_label()
    # Masking is handled by the UI, but current_label just shows config index and provider
    assert "super_secret_key" not in label
    assert "Groq" in label
