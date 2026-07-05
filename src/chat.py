import os
from typing import List, Dict
from src.llm_client import call_ollama_chat

class ChatSession:
    """Chat session for local Ollama chat over a folder of markdown notes."""

    def __init__(self, folder_path: str, model_name: str = "llama3"):
        self.folder_path = folder_path
        self.model_name = model_name
        self.chat_history: List[Dict[str, str]] = []

    def _get_combined_context(self) -> str:
        """Read all .md files in the folder and combine them."""
        combined_text = ""
        if not os.path.isdir(self.folder_path):
            return combined_text
            
        for file_name in os.listdir(self.folder_path):
            if file_name.endswith(".md"):
                file_path = os.path.join(self.folder_path, file_name)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        combined_text += f"\n--- {file_name} ---\n"
                        combined_text += f.read() + "\n"
                except Exception:
                    pass
        return combined_text

    def chat(self, user_message: str) -> str:
        """
        Send a chat message to the local Ollama instance with context.
        
        Args:
            user_message: The user's query.
            
        Returns:
            The generated response string.
        """
        messages = []
        context_markdown = self._get_combined_context()
        
        system_prompt = (
            "You are an AI study assistant. Use the following notes to answer the user's questions.\n\n"
            f"NOTES:\n{context_markdown}"
        )
        messages.append({"role": "system", "content": system_prompt})
        
        # Add history
        messages.extend(self.chat_history)
            
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        response = call_ollama_chat(messages, self.model_name)
        
        # Update history
        self.chat_history.append({"role": "user", "content": user_message})
        self.chat_history.append({"role": "assistant", "content": response})
        
        return response
        
    def clear_history(self):
        """Clear the chat history."""
        self.chat_history.clear()
