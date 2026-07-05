import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from src.chat import ChatSession

def test_chat_session_loads_folder_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create dummy md files
        with open(os.path.join(tmpdir, "note1.md"), "w", encoding="utf-8") as f:
            f.write("Content of note 1")
        with open(os.path.join(tmpdir, "note2.md"), "w", encoding="utf-8") as f:
            f.write("Content of note 2")
            
        session = ChatSession(tmpdir, "llama3")
        context = session._get_combined_context()
        
        assert "note1.md" in context
        assert "Content of note 1" in context
        assert "note2.md" in context
        assert "Content of note 2" in context

@patch("src.chat.call_ollama_chat")
def test_chat_session_history_and_clear(mock_call_ollama):
    mock_call_ollama.return_value = "Mocked AI Response"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        session = ChatSession(tmpdir, "llama3")
        
        # Initial chat
        response1 = session.chat("Hello")
        assert response1 == "Mocked AI Response"
        assert len(session.chat_history) == 2
        assert session.chat_history[0] == {"role": "user", "content": "Hello"}
        assert session.chat_history[1] == {"role": "assistant", "content": "Mocked AI Response"}
        
        # Second chat
        response2 = session.chat("How are you?")
        assert len(session.chat_history) == 4
        
        # Verify history passed to LLM
        args, _ = mock_call_ollama.call_args
        messages = args[0]
        # System prompt + 4 history messages (2 from before, + user msg added inside chat())
        assert len(messages) == 4  # Wait, in the second call: 1 system, 2 history, 1 new user message = 4
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "How are you?"
        
        # Test clear history
        session.clear_history()
        assert len(session.chat_history) == 0
