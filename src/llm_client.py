"""
LLM HTTP client for making requests to Ollama and OpenAI-compatible endpoints.
"""
import json
import urllib.request
import urllib.error

APP_VERSION = "2.0.0"
LLM_TIMEOUT_SECONDS = 180  # Max seconds to wait for a single LLM response


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
