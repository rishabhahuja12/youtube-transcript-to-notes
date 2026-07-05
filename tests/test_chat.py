import pytest
from unittest.mock import patch, MagicMock
import urllib.error
import json
from src.chat import LocalChatClient

def test_local_chat_success():
    client = LocalChatClient(model_name="test-model")
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "message": {"content": "This is a test response."}
    }).encode("utf-8")
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_response
        response = client.chat(
            context_markdown="These are notes.",
            user_message="What are the notes about?"
        )
        assert response == "This is a test response."
        
        # Verify the payload structure
        args, kwargs = mock_urlopen.call_args
        request_obj = args[0]
        assert request_obj.method == "POST"
        payload = json.loads(request_obj.data.decode("utf-8"))
        assert payload["model"] == "test-model"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert "These are notes." in payload["messages"][0]["content"]
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "What are the notes about?"

def test_local_chat_connection_error():
    client = LocalChatClient()
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_error = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        mock_urlopen.side_effect = mock_error
        
        with pytest.raises(ConnectionError, match="Please start Ollama to use Chat."):
            client.chat(
                context_markdown="Notes",
                user_message="Hello"
            )
