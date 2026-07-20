import json
from dataclasses import dataclass, asdict

VALID_PROVIDERS = {"ollama", "gemini", "groq", "openrouter"}
VALID_CAPABILITIES = {"text", "vision"}

@dataclass
class ProviderConfig:
    """A single API configuration entry in the pool."""
    provider: str        # e.g. "gemini", "groq", "openrouter", "ollama"
    endpoint_url: str    # e.g. "https://generativelanguage.googleapis.com/..."
    api_key: str         # The API key (masked in logs)
    model_name: str      # e.g. "gemini-3.5-flash", "llama-3.3-70b"
    capability: str = "text"  # "text" or "vision"

    def validate(self):
        """Validate the provider configuration requirements."""
        self.provider = (self.provider or "").strip().lower()
        self.capability = (self.capability or "").strip().lower()
        self.endpoint_url = (self.endpoint_url or "").strip()
        self.model_name = (self.model_name or "").strip()
        self.api_key = (self.api_key or "").strip()

        if self.provider not in VALID_PROVIDERS:
            raise ValueError(f"Invalid provider: '{self.provider}'. Must be one of {VALID_PROVIDERS}")
            
        if self.capability not in VALID_CAPABILITIES:
            raise ValueError(f"Invalid capability: '{self.capability}'. Must be one of {VALID_CAPABILITIES}")
            
        if not self.endpoint_url:
            raise ValueError("Endpoint URL cannot be empty.")
            
        if not self.model_name:
            raise ValueError("Model name cannot be empty.")
            
        if self.provider != "ollama" and not self.api_key:
            raise ValueError(f"API key is required for provider '{self.provider}'.")
            
        url_lower = self.endpoint_url.lower()
        if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
            raise ValueError("Endpoint URL must start with http:// or https://")
            
        if self.provider == "ollama":
            is_loopback = url_lower.startswith("http://localhost") or url_lower.startswith("http://127.0.0.1")
            is_https = url_lower.startswith("https://")
            if not (is_loopback or is_https):
                raise ValueError("Plain HTTP is only permitted for loopback (localhost/127.0.0.1) Ollama endpoints.")
        else:
            if not url_lower.startswith("https://"):
                raise ValueError(f"HTTPS is required for remote provider '{self.provider}'.")


class ProviderPool:
    """Manages a pool of API configurations and rotates on rate-limit errors."""
    
    def __init__(self, configs: list[ProviderConfig]):
        """Initialize the pool with a list of configurations."""
        self._configs = configs
        self._current_idx = 0
        self._exhausted = False
        
    @property
    def configs(self) -> list[ProviderConfig]:
        """Return the underlying configs list."""
        return self._configs

    @property
    def current(self) -> ProviderConfig:
        """Return the currently active configuration."""
        if not self._configs:
            raise ValueError("Provider pool is empty.")
        return self._configs[self._current_idx]
        
    def rotate(self) -> bool:
        """Advance to the next config in the pool.
        Returns True if a fresh (untried) config is available.
        Returns False if all configs have been tried in this cycle."""
        if not self._configs:
            return False
        
        self._current_idx += 1
        if self._current_idx >= len(self._configs):
            self._current_idx = 0
            self._exhausted = True
            return False
            
        if self._exhausted:
            # We already cycled through everything in this run
            return False
            
        return True
        
    def reset_cycle(self) -> None:
        """Mark all configs as untried again (after a successful cooldown)."""
        self._exhausted = False
        self._current_idx = 0
        
    @property
    def total(self) -> int:
        """Total number of configs in the pool."""
        return len(self._configs)
        
    @property
    def current_index(self) -> int:
        """1-based index of the current config for display."""
        if not self._configs:
            return 0
        return self._current_idx + 1
        
    def current_label(self) -> str:
        """Human-readable label for logging, e.g. 'Config 2/3 (groq)'."""
        if not self._configs:
            return "Empty Pool"
        provider = self.current.provider
        return f"Config {self.current_index}/{self.total} ({provider})"

    def get_text_pool(self) -> "ProviderPool":
        """Return a new ProviderPool containing only text models."""
        return ProviderPool([c for c in self._configs if c.capability == "text"])

    def get_vision_pool(self) -> "ProviderPool":
        """Return a new ProviderPool containing only vision models."""
        return ProviderPool([c for c in self._configs if c.capability == "vision"])
        
    @staticmethod
    def from_json(json_str: str) -> "ProviderPool":
        """Deserialize a JSON string into a ProviderPool."""
        if not json_str:
            return ProviderPool([])
        try:
            data = json.loads(json_str)
            configs = []
            for item in data:
                if "capability" not in item:
                    item["capability"] = "text"
                
                # Normalize before instantiation
                item["provider"] = item.get("provider", "").lower()
                
                try:
                    config = ProviderConfig(**item)
                    config.validate()
                    configs.append(config)
                except Exception as e:
                    import logging
                    logging.warning(f"Skipping invalid provider config in pool: {e}")
            return ProviderPool(configs)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse provider pool JSON: {e}")
        
    def to_json(self) -> str:
        """Serialize the pool to a JSON string for storage."""
        data = [asdict(c) for c in self._configs]
        return json.dumps(data)
        
    @staticmethod
    def from_legacy(
        provider: str, endpoint_url: str, api_key: str, model_name: str
    ) -> "ProviderPool":
        """Create a single-config pool from legacy credential format.
        Ensures backward compatibility with existing .env/keyring setup."""
        if not endpoint_url or not model_name:
            return ProviderPool([])
            
        provider = (provider or "groq").lower()
        if provider == "openai":
             # Map legacy openai to something valid if needed, or openrouter
             provider = "openrouter"
             
        config = ProviderConfig(
            provider=provider,
            endpoint_url=endpoint_url,
            api_key=api_key or "",
            model_name=model_name,
            capability="text"
        )
        config.validate()
        return ProviderPool([config])
