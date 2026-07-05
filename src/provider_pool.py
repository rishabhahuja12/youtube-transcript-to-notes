import json
from dataclasses import dataclass, asdict

@dataclass
class ProviderConfig:
    """A single API configuration entry in the pool."""
    provider: str        # e.g. "Gemini", "Groq", "OpenRouter", "Ollama"
    endpoint_url: str    # e.g. "https://generativelanguage.googleapis.com/..."
    api_key: str         # The API key (masked in logs)
    model_name: str      # e.g. "gemini-3.5-flash", "llama-3.3-70b"
    capability: str = "text"  # "text" or "vision"


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
        """Human-readable label for logging, e.g. 'Config 2/3 (Groq)'."""
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
                # Provide default capability if missing
                if "capability" not in item:
                    item["capability"] = "text"
                configs.append(ProviderConfig(**item))
            return ProviderPool(configs)
        except Exception:
            return ProviderPool([])
        
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
            
        config = ProviderConfig(
            provider=provider or "Groq",
            endpoint_url=endpoint_url,
            api_key=api_key or "",
            model_name=model_name,
            capability="text"
        )
        return ProviderPool([config])
