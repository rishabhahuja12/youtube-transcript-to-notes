import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open

from src.auth import (
    connect_youtube,
    load_credentials,
    TOKEN_JSON_PATH,
    LEGACY_TOKEN_PICKLE_PATH,
    STUDYSUITE_DIR
)
from gateway.content_service import disconnect_youtube_endpoint
import google.auth.exceptions

@patch("src.auth.InstalledAppFlow")
@patch("src.auth.os.replace")
@patch("src.auth.tempfile.mkstemp")
@patch("src.auth.os.fdopen")
@patch("src.auth.os.makedirs")
def test_token_json_written_atomically(mock_makedirs, mock_fdopen, mock_mkstemp, mock_replace, mock_flow):
    # Setup mocks
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "test"}'
    mock_flow_instance = MagicMock()
    mock_flow_instance.run_local_server.return_value = mock_creds
    mock_flow.from_client_secrets_file.return_value = mock_flow_instance
    
    mock_mkstemp.return_value = (1, "/tmp/temp_token.json")
    mock_file = MagicMock()
    mock_fdopen.return_value.__enter__.return_value = mock_file
    
    # Run
    connect_youtube()
    
    # Verify
    mock_mkstemp.assert_called_with(dir=STUDYSUITE_DIR)
    mock_file.write.assert_called_with('{"token": "test"}')
    mock_replace.assert_called_with("/tmp/temp_token.json", TOKEN_JSON_PATH)

@patch("src.auth.os.path.exists")
@patch("src.auth.Credentials")
def test_load_json_token_preferred(mock_credentials, mock_exists):
    # Both paths exist
    def exists_side_effect(path):
        if path == TOKEN_JSON_PATH: return True
        if path == LEGACY_TOKEN_PICKLE_PATH: return True
        return False
    mock_exists.side_effect = exists_side_effect
    
    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_credentials.from_authorized_user_file.return_value = mock_creds
    
    creds = load_credentials()
    
    assert creds == mock_creds
    mock_credentials.from_authorized_user_file.assert_called_once_with(TOKEN_JSON_PATH, ['https://www.googleapis.com/auth/youtube.readonly'])

@patch("src.auth.os.path.exists")
@patch("builtins.open", new_callable=mock_open)
@patch("src.auth.pickle.load")
@patch("src.auth.tempfile.mkstemp")
@patch("src.auth.os.fdopen")
@patch("src.auth.os.replace")
@patch("src.auth.os.remove")
@patch("src.auth.os.makedirs")
def test_pickle_migrated_to_json(mock_makedirs, mock_remove, mock_replace, mock_fdopen, mock_mkstemp, mock_pickle_load, mock_open_file, mock_exists):
    def exists_side_effect(path):
        if path == TOKEN_JSON_PATH: return False
        if path == LEGACY_TOKEN_PICKLE_PATH: return True
        return False
    mock_exists.side_effect = exists_side_effect
    
    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds.to_json.return_value = '{"migrated": true}'
    mock_pickle_load.return_value = mock_creds
    
    mock_mkstemp.return_value = (1, "/tmp/temp_migrate.json")
    mock_out_file = MagicMock()
    mock_fdopen.return_value.__enter__.return_value = mock_out_file
    
    creds = load_credentials()
    
    assert creds == mock_creds
    mock_pickle_load.assert_called_once()
    mock_out_file.write.assert_called_with('{"migrated": true}')
    mock_replace.assert_called_once_with("/tmp/temp_migrate.json", TOKEN_JSON_PATH)
    mock_remove.assert_called_once_with(LEGACY_TOKEN_PICKLE_PATH)

@patch("src.auth.os.path.exists")
@patch("src.auth.Credentials")
def test_malformed_json_returns_disconnected(mock_credentials, mock_exists):
    mock_exists.side_effect = lambda path: path == TOKEN_JSON_PATH
    # from_authorized_user_file raises an exception for malformed JSON
    mock_credentials.from_authorized_user_file.side_effect = ValueError("Malformed JSON")
    
    creds = load_credentials()
    assert creds is None

@patch("src.auth.os.path.exists")
@patch("src.auth.Credentials")
def test_revoked_token_returns_disconnected(mock_credentials, mock_exists):
    mock_exists.side_effect = lambda path: path == TOKEN_JSON_PATH
    
    mock_creds = MagicMock()
    mock_creds.expired = True
    mock_creds.refresh_token = "some_token"
    mock_creds.refresh.side_effect = google.auth.exceptions.RefreshError("Token revoked")
    
    mock_credentials.from_authorized_user_file.return_value = mock_creds
    
    creds = load_credentials()
    assert creds is None

@pytest.mark.asyncio
@patch("gateway.content_service.os.path.exists")
@patch("gateway.content_service.os.remove")
async def test_disconnect_removes_both_paths(mock_remove, mock_exists):
    # Setup exists to return True for both paths
    mock_exists.return_value = True
    
    result = await disconnect_youtube_endpoint()
    
    assert result == {"connected": False}
    # Verify both paths were removed
    assert mock_remove.call_count == 2
    mock_remove.assert_any_call(TOKEN_JSON_PATH)
    mock_remove.assert_any_call(LEGACY_TOKEN_PICKLE_PATH)
