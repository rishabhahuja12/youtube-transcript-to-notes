import json
import urllib.request
import urllib.error
from typing import List, Dict, Tuple

OLLAMA_URL = "http://localhost:11434/api/chat"

class LocalChatClient:
    """Client for local Ollama chat."""

    def __init__(self, model_name: str = "llama3"):
        self.model_name = model_name

    def chat(
        self,
        context_markdown: str,
        user_message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> str:
        """
        Send a chat message to the local Ollama instance.
        
        Args:
            context_markdown: The markdown notes to use as context.
            user_message: The user's query.
            chat_history: The history of previous messages (excluding system prompt).
            
        Returns:
            The generated response string.
            
        Raises:
            ConnectionError: If Ollama is not reachable or returns an error.
        """
        if chat_history is None:
            chat_history = []
            
        messages = []
        # Inject the context as a system prompt
        system_prompt = (
            "You are an AI study assistant. Use the following notes to answer the user's questions.\n\n"
            f"NOTES:\n{context_markdown}"
        )
        messages.append({"role": "system", "content": system_prompt})
        
        # Add history
        for msg in chat_history:
            messages.append(msg)
            
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False
        }
        
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                return res_data.get("message", {}).get("content", "")
        except urllib.error.URLError as e:
            is_refused = isinstance(e.reason, ConnectionRefusedError)
            has_refused_str = hasattr(e.reason, 'strerror') and 'refused' in str(e.reason).lower()
            if is_refused or has_refused_str:
                raise ConnectionError("Please start Ollama to use Chat.") from e
            raise ConnectionError(f"Failed to connect to Ollama: {str(e.reason)}") from e
        except Exception as e:
            raise ConnectionError(f"An error occurred while communicating with Ollama: {str(e)}") from e
