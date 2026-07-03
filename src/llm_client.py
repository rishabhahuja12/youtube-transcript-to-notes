"""
LLM HTTP client for making requests to Ollama and OpenAI-compatible endpoints.

Includes an adaptive rate limiter that proactively paces requests to stay
within provider-specific RPM/TPM limits.
"""
import json
import time
import threading
from collections import deque
import urllib.request
import urllib.error

APP_VERSION = "2.0.0"
LLM_TIMEOUT_SECONDS = 180  # Max seconds to wait for a single LLM response

# ─────────────────────── Provider Rate Limit Presets ───────────────────────

PROVIDER_PRESETS = {
    "Groq": {"rpm": 25, "tpm": 5000, "label": "Groq Free (25 RPM, 5K TPM)"},
    "OpenRouter": {"rpm": 18, "tpm": 50000, "label": "OpenRouter Free (18 RPM)"},
    "Gemini": {"rpm": 15, "tpm": 1000000, "label": "Gemini AI Studio (15 RPM)"},
    "Ollama": {"rpm": 9999, "tpm": 999999, "label": "Ollama Local (no limits)"},
}


def estimate_tokens(text: str) -> int:
    """Estimate token count from text using word-count heuristic.
    
    Most LLM tokenizers produce ~1.3 tokens per English word.
    We use 1.4 as a safety margin.
    """
    return max(1, int(len(text.split()) * 1.4))


# ─────────────────────── Adaptive Rate Limiter ────────────────────────────

class AdaptiveRateLimiter:
    """Token-bucket rate limiter that proactively paces LLM requests.
    
    Instead of hitting 429 errors and reacting, this limiter:
    1. Tracks requests-per-minute and tokens-per-minute in sliding windows
    2. Pre-emptively waits before sending if limits would be exceeded
    3. Supports cancel-aware waiting (won't block forever)
    """
    
    def __init__(self, rpm: int = 30, tpm: int = 6000):
        self.rpm_limit = rpm
        self.tpm_limit = tpm
        self.request_timestamps = deque()
        self.token_log = deque()  # (timestamp, token_count)
        self.lock = threading.Lock()
    
    @classmethod
    def for_provider(cls, provider: str) -> "AdaptiveRateLimiter":
        """Create a rate limiter with appropriate limits for a known provider."""
        preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS.get("Groq"))
        return cls(rpm=preset["rpm"], tpm=preset["tpm"])
    
    def _clean_old_entries(self):
        """Remove entries older than 60 seconds from the sliding window."""
        now = time.time()
        cutoff = now - 60
        while self.request_timestamps and self.request_timestamps[0] < cutoff:
            self.request_timestamps.popleft()
        while self.token_log and self.token_log[0][0] < cutoff:
            self.token_log.popleft()
    
    @property
    def current_rpm(self) -> int:
        """Current requests in the last 60 seconds."""
        with self.lock:
            self._clean_old_entries()
            return len(self.request_timestamps)
    
    @property
    def current_tpm(self) -> int:
        """Current tokens in the last 60 seconds."""
        with self.lock:
            self._clean_old_entries()
            return sum(t[1] for t in self.token_log)
    
    def wait_if_needed(self, estimated_tokens: int, cancel_event: threading.Event = None,
                       on_log: callable = None) -> bool:
        """Block until the request can proceed within limits.
        
        Returns True if ready to proceed, False if cancelled.
        """
        log = on_log or (lambda msg: None)
        
        if estimated_tokens > self.tpm_limit:
            log(f"WARNING: Estimated tokens ({estimated_tokens}) exceeds TPM limit ({self.tpm_limit}). Clamping to limit.")
            estimated_tokens = self.tpm_limit
            
        while True:
            if cancel_event and cancel_event.is_set():
                return False
            
            with self.lock:
                self._clean_old_entries()
                current_rpm = len(self.request_timestamps)
                current_tpm = sum(t[1] for t in self.token_log)
                
                rpm_ok = current_rpm < self.rpm_limit
                tpm_ok = (current_tpm + estimated_tokens) <= self.tpm_limit
                if rpm_ok and tpm_ok:
                    # Record this request
                    now = time.time()
                    self.request_timestamps.append(now)
                    self.token_log.append((now, estimated_tokens))
                    return True
                
                # Calculate how long to wait
                if not rpm_ok and self.request_timestamps:
                    oldest = self.request_timestamps[0]
                    wait_rpm = 60 - (time.time() - oldest) + 1
                else:
                    wait_rpm = 0
                
                if not tpm_ok and self.token_log:
                    # Find when enough tokens expire
                    needed = (current_tpm + estimated_tokens) - self.tpm_limit
                    cumulative = 0
                    wait_tpm = 60  # worst case
                    for ts, tc in self.token_log:
                        cumulative += tc
                        if cumulative >= needed:
                            wait_tpm = 60 - (time.time() - ts) + 1
                            break
                else:
                    wait_tpm = 0
                
                wait_time = max(wait_rpm, wait_tpm, 1)
            
            reason = []
            if not rpm_ok:
                reason.append(f"RPM: {current_rpm}/{self.rpm_limit}")
            if not tpm_ok:
                reason.append(f"TPM: {current_tpm + estimated_tokens}/{self.tpm_limit}")
            
            log(f"⏳ Rate limit pacing ({', '.join(reason)}). Waiting {wait_time:.0f}s...")
            
            # Interruptible wait
            if cancel_event:
                if cancel_event.wait(wait_time):
                    return False
            else:
                time.sleep(wait_time)
    
    def record_actual_tokens(self, actual_tokens: int):
        """Adjust the last logged token count with actual usage from API response."""
        with self.lock:
            if self.token_log:
                ts, _ = self.token_log.pop()
                self.token_log.append((ts, actual_tokens))


def get_rate_limit_info(provider: str) -> str:
    """Get a human-readable description of rate limits for a provider."""
    preset = PROVIDER_PRESETS.get(provider)
    if preset:
        return preset["label"]
    return f"Unknown provider '{provider}' — using conservative limits"


def estimate_pipeline_time(total_words: int, num_chapters: int, provider: str) -> dict:
    """Estimate how long the pipeline will take based on provider limits.
    
    Returns dict with:
        - estimated_input_tokens: total estimated input tokens
        - estimated_output_tokens: total estimated output tokens  
        - estimated_minutes: estimated wall-clock minutes
        - pacing_delay_per_chapter: seconds between chapters
        - info: human-readable summary
    """
    preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS.get("Groq"))
    rpm = preset["rpm"]
    tpm = preset["tpm"]
    
    input_tokens = int(total_words * 1.4)
    output_tokens = num_chapters * 800  # ~800 tokens per chapter output
    total_tokens = input_tokens + output_tokens
    
    # Time limited by RPM
    rpm_minutes = num_chapters / rpm if rpm < 9999 else 0
    
    # Time limited by TPM
    avg_tokens_per_call = total_tokens / max(num_chapters, 1)
    calls_per_minute_by_tpm = tpm / avg_tokens_per_call if avg_tokens_per_call > 0 else 9999
    tpm_minutes = num_chapters / calls_per_minute_by_tpm if calls_per_minute_by_tpm < 9999 else 0
    
    # LLM generation time (~5s for cloud, ~15s for local per chapter)
    if provider == "Ollama":
        gen_minutes = (num_chapters * 15) / 60
    else:
        gen_minutes = (num_chapters * 5) / 60
    
    estimated_minutes = max(rpm_minutes, tpm_minutes) + gen_minutes
    pacing_delay = 60 / rpm if rpm < 9999 else 0
    
    info = (
        f"Estimated: ~{input_tokens:,} input tokens, ~{output_tokens:,} output tokens\n"
        f"Provider: {preset['label']}\n"
        f"Estimated time: ~{estimated_minutes:.1f} minutes ({num_chapters} chapters)\n"
    )
    if pacing_delay > 1:
        info += f"Pacing: ~{pacing_delay:.0f}s between chapters to stay within limits\n"
    
    return {
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_minutes": estimated_minutes,
        "pacing_delay_per_chapter": pacing_delay,
        "info": info,
    }


# ─────────────────────── Core LLM Call ────────────────────────────────────

def call_llm(provider, endpoint_url, api_key, model_name, system_prompt, user_prompt):
    """Make raw POST HTTP call to Ollama or OpenAI compatible endpoint."""
    url = endpoint_url.strip()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"YT-Transcriptor/{APP_VERSION} (Python)"
    }    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    
    if provider == "Ollama":
        # Normalize Ollama native URL or OpenAI compatible URL
        if not (url.endswith("/api/chat") or url.endswith("/v1/chat/completions") or "/api/" in url or "/v1/" in url):
            url = url.rstrip("/") + "/api/chat"
            
        if "/api/chat" in url:
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": False
            }
        else:
            payload = {
                "model": model_name,
                "messages": messages
            }
    else:
        # OpenAI Compatible
        if not (url.endswith("/chat/completions") or "/v1" in url):
            url = url.rstrip("/") + "/v1/chat/completions"
        elif url.endswith("/v1") or url.endswith("/v1/"):
            url = url.rstrip("/") + "/chat/completions"
            
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        payload = {
            "model": model_name,
            "messages": messages
        }
        
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if "choices" in res_data:
                return res_data["choices"][0]["message"]["content"]
            elif "message" in res_data:
                return res_data["message"]["content"]
            elif "response" in res_data:
                return res_data["response"]
            else:
                return str(res_data)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        raise ConnectionError(f"HTTP {e.code} Error: {e.reason}\nResponse: {err_msg}") from e
    except Exception as e:
        raise ConnectionError(f"Connection failure: {str(e)}") from e

