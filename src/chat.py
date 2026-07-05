import os
from typing import List, Dict
from src.llm_client import call_ollama_chat

class ChatSession:
    """Chat session for local Ollama chat over a folder of markdown notes."""

    def __init__(self, notes_dir: str, ollama_model: str = "llama3"):
        self.notes_dir = notes_dir
        self.ollama_model = ollama_model
        self.chat_history: List[Dict[str, str]] = []
        
        # Load all .md files once at initialization
        combined_text = ""
        if os.path.isdir(self.notes_dir):
            for file_name in os.listdir(self.notes_dir):
                if file_name.endswith(".md"):
                    file_path = os.path.join(self.notes_dir, file_name)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            combined_text += f"\n--- {file_name} ---\n"
                            combined_text += f.read() + "\n"
                    except Exception:
                        pass
        self.context_markdown = combined_text

    def send(self, user_message: str) -> str:
        """
        Send a chat message to the local Ollama instance with context.
        
        Args:
            user_message: The user's query.
            
        Returns:
            The generated response string.
        """
        messages = []
        
        system_prompt = (
            "You are an AI study assistant. Use the following notes to answer the user's questions.\n\n"
            f"NOTES:\n{self.context_markdown}"
        )
        messages.append({"role": "system", "content": system_prompt})
        
        # Add history
        messages.extend(self.chat_history)
            
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        response = call_ollama_chat(self.ollama_model, messages)
        
        # Update history
        self.chat_history.append({"role": "user", "content": user_message})
        self.chat_history.append({"role": "assistant", "content": response})
        
        return response
        
    def clear_history(self):
        """Clear the chat history."""
        self.chat_history.clear()
