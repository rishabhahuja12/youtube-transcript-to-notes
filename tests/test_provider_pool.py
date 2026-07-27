import json
import pytest
from src.provider_pool import ProviderPool, ProviderConfig

def test_provider_pool_single_config():
    config = ProviderConfig(provider="Groq", endpoint_url="https://a", api_key="k1", model_name="m1")
    pool = ProviderPool([config])
    
    assert pool.total == 1
    assert pool.current_index == 1
    assert pool.current_label() == "Config 1/1 (Groq)"
    
    # Rotation on single config exhausts it immediately
    assert pool.rotate() is False
    assert pool.current_index == 1

def test_provider_pool_multiple_configs():
    c1 = ProviderConfig(provider="Groq", endpoint_url="https://a", api_key="k1", model_name="m1")
    c2 = ProviderConfig(provider="Gemini", endpoint_url="https://b", api_key="k2", model_name="m2")
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
    c1 = ProviderConfig(provider="Groq", endpoint_url="https://a", api_key="k1", model_name="m1")
    c2 = ProviderConfig(provider="Gemini", endpoint_url="https://b", api_key="k2", model_name="m2")
    pool = ProviderPool([c1, c2])
    
    pool.rotate() # goes to c2
    pool.rotate() # exhausts, back to c1
    
    assert pool.rotate() is False # Still exhausted
    
    pool.reset_cycle()
    assert pool.current.provider == "Groq"
    assert pool.rotate() is True # Can rotate again
    assert pool.current.provider == "Gemini"

def test_provider_pool_json_serialization():
    c1 = ProviderConfig(provider="Groq", endpoint_url="https://a", api_key="k1", model_name="m1")
    pool = ProviderPool([c1])
    
    json_str = pool.to_json()
    assert "Groq" in json_str
    
    pool_loaded = ProviderPool.from_json(json_str)
    assert pool_loaded.total == 1
    assert pool_loaded.current.api_key == "k1"

def test_provider_pool_legacy_migration():
    pool = ProviderPool.from_legacy("Gemini", "https://x", "key123", "gemini-1.5")
    
    assert pool.total == 1
    assert pool.current.provider == "gemini"
    assert pool.current.endpoint_url == "https://x"
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
    c1 = ProviderConfig(provider="Groq", endpoint_url="https://a", api_key="super_secret_key", model_name="m1")
    pool = ProviderPool([c1])
    label = pool.current_label()
    # Masking is handled by the UI, but current_label just shows config index and provider
    assert "super_secret_key" not in label
    assert "Groq" in label

def test_provider_pool_capability_filtering():
    c1 = ProviderConfig(provider="Groq", endpoint_url="https://a", api_key="k1", model_name="m1", capability="text")
    c2 = ProviderConfig(provider="Gemini", endpoint_url="https://b", api_key="k2", model_name="m2", capability="vision")
    c3 = ProviderConfig(provider="OpenRouter", endpoint_url="https://c", api_key="k3", model_name="m3", capability="text")
    
    pool = ProviderPool([c1, c2, c3])
    
    text_pool = pool.get_text_pool()
    assert text_pool.total == 2
    assert text_pool.configs[0].provider == "Groq"
    assert text_pool.configs[1].provider == "OpenRouter"
    
    vision_pool = pool.get_vision_pool()
    assert vision_pool.total == 1
    assert vision_pool.configs[0].provider == "Gemini"

def test_provider_pool_json_capability_default():
    # Simulate old JSON without capability
    old_json = '[{"provider": "Groq", "endpoint_url": "https://a", "api_key": "k1", "model_name": "m1"}]'
    pool = ProviderPool.from_json(old_json)
    
    assert pool.total == 1
    assert pool.configs[0].capability == "text"
    assert pool.configs[0].rpm_limit is None
    assert pool.configs[0].tpm_limit is None

def test_provider_config_rate_limits_validation():
    config = ProviderConfig(
        provider="groq",
        endpoint_url="https://api.groq.com/openai/v1",
        api_key="k1",
        model_name="llama-3.3-70b-versatile",
        rpm_limit=30,
        tpm_limit=12000
    )
    config.validate()
    assert config.rpm_limit == 30
    assert config.tpm_limit == 12000

    invalid_rpm = ProviderConfig(
        provider="groq",
        endpoint_url="https://api.groq.com/openai/v1",
        api_key="k1",
        model_name="m1",
        rpm_limit=-5
    )
    with pytest.raises(ValueError, match="RPM limit must be a positive number"):
        invalid_rpm.validate()

    invalid_tpm = ProviderConfig(
        provider="groq",
        endpoint_url="https://api.groq.com/openai/v1",
        api_key="k1",
        model_name="m1",
        tpm_limit=0
    )
    with pytest.raises(ValueError, match="TPM limit must be a positive number"):
        invalid_tpm.validate()

def test_provider_pool_json_rate_limits_roundtrip():
    config = ProviderConfig(
        provider="openrouter",
        endpoint_url="https://openrouter.ai/api/v1",
        api_key="k1",
        model_name="m1",
        rpm_limit=18,
        tpm_limit=50000
    )
    pool = ProviderPool([config])
    json_str = pool.to_json()
    
    pool_reloaded = ProviderPool.from_json(json_str)
    assert pool_reloaded.configs[0].rpm_limit == 18
    assert pool_reloaded.configs[0].tpm_limit == 50000

def test_adaptive_rate_limiter_for_config():
    from src.llm_client import AdaptiveRateLimiter
    
    config_default = ProviderConfig(
        provider="groq",
        endpoint_url="https://api.groq.com/openai/v1",
        api_key="k1",
        model_name="m1"
    )
    limiter_default = AdaptiveRateLimiter.for_config(config_default)
    assert limiter_default.rpm_limit == 30
    assert limiter_default.tpm_limit == 12000

    config_custom = ProviderConfig(
        provider="groq",
        endpoint_url="https://api.groq.com/openai/v1",
        api_key="k1",
        model_name="m1",
        rpm_limit=60,
        tpm_limit=25000
    )
    limiter_custom = AdaptiveRateLimiter.for_config(config_custom)
    assert limiter_custom.rpm_limit == 60
    assert limiter_custom.tpm_limit == 25000

