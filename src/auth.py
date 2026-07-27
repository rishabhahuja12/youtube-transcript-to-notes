"""
YouTube Data API v3 OAuth2 Authentication and credential persistence.
"""
import os
import json
import pickle
import tempfile
from google.oauth2.credentials import Credentials
from typing import Any, Dict, Optional
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from runtime import application_root


STUDYSUITE_DIR = os.path.join(os.path.expanduser("~"), ".studysuite")
TOKEN_JSON_PATH = os.path.join(STUDYSUITE_DIR, "token.json")
LEGACY_TOKEN_PICKLE_PATH = os.path.join(STUDYSUITE_DIR, "token.pickle")

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

import threading
import logging
import webbrowser

_oauth_lock = threading.Lock()

def start_youtube_oauth() -> str:
    """Generate Google OAuth authorization URL and listen for callback in a daemon thread.
    
    Returns:
        str: Google authorization URL to open in browser.
    """
    secret_path = str(application_root() / 'client_secret.json')
    flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
    flow.redirect_uri = "http://localhost:8089/"
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

    def _run_server():
        with _oauth_lock:
            try:
                creds = flow.run_local_server(
                    host='localhost',
                    port=8089,
                    authorization_prompt_message='Please complete Google OAuth in your browser.',
                    success_message='Authorization successful! You may close this window.',
                    open_browser=False
                )
                if creds:
                    os.makedirs(STUDYSUITE_DIR, exist_ok=True)
                    fd, temp_path = tempfile.mkstemp(dir=STUDYSUITE_DIR)
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        f.write(creds.to_json())
                    os.replace(temp_path, TOKEN_JSON_PATH)
            except Exception as exc:
                logging.warning(f"OAuth server thread exception: {exc}")

    t = threading.Thread(target=_run_server, daemon=True)
    t.start()

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    return auth_url


def connect_youtube() -> Any:
    """Connect to YouTube API using OAuth and save credentials.
    
    Returns:
        Any: Google OAuth credentials object.
    """
    secret_path = str(application_root() / 'client_secret.json')
    flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
    creds = flow.run_local_server(
        host='localhost',
        port=0,
        authorization_prompt_message='Please complete Google OAuth authorization in your browser.',
        success_message='Authorization successful! You may close this browser tab.',
        open_browser=True
    )
    
    os.makedirs(STUDYSUITE_DIR, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=STUDYSUITE_DIR)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(creds.to_json())
    os.replace(temp_path, TOKEN_JSON_PATH)
    return creds

def load_credentials() -> Optional[Any]:
    """Load saved YouTube API credentials from file, refreshing if necessary.
    
    Returns:
        Optional[Any]: Google OAuth credentials object if found and valid, None otherwise.
    """
    creds = None
    
    if os.path.exists(TOKEN_JSON_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_JSON_PATH, SCOPES)
        except Exception:
            return None
    elif os.path.exists(LEGACY_TOKEN_PICKLE_PATH):
        try:
            with open(LEGACY_TOKEN_PICKLE_PATH, 'rb') as f:
                creds = pickle.load(f)
            if creds:
                os.makedirs(STUDYSUITE_DIR, exist_ok=True)
                fd, temp_path = tempfile.mkstemp(dir=STUDYSUITE_DIR)
                with os.fdopen(fd, 'w', encoding='utf-8') as f_out:
                    f_out.write(creds.to_json())
                os.replace(temp_path, TOKEN_JSON_PATH)
                os.remove(LEGACY_TOKEN_PICKLE_PATH)
        except Exception:
            return None
            
    if not creds:
        return None
        
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            fd, temp_path = tempfile.mkstemp(dir=STUDYSUITE_DIR)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
            os.replace(temp_path, TOKEN_JSON_PATH)
        except Exception:
            return None
            
    return creds


def get_video_metadata(video_id: str, creds: Any) -> Dict[str, Any]:
    """Fetch metadata for a YouTube video.
    
    Args:
        video_id (str): The ID of the YouTube video.
        creds (Any): Google OAuth credentials object.
        
    Returns:
        Dict[str, Any]: Dictionary containing video title, channel, duration, and description.
        
    Raises:
        ValueError: If video is not found or access is denied.
    """
    yt = build('youtube', 'v3', credentials=creds)
    resp = yt.videos().list(part='snippet,contentDetails', id=video_id).execute()
    if not resp.get('items'):
        raise ValueError("Video not found or access denied")
        
    item = resp['items'][0]
    title = item['snippet']['title']
    channel = item['snippet']['channelTitle']
    import isodate
    duration_str = item['contentDetails']['duration']
    duration = int(isodate.parse_duration(duration_str).total_seconds())
    description = item['snippet']['description']
    
    return {
        'title': title, 
        'channel': channel, 
        'duration': duration, 
        'description': description
    }


def disconnect_youtube() -> bool:
    """Disconnect YouTube by removing stored OAuth token files.

    Returns:
        bool: True if cleanup attempted without critical error.
    """
    if os.path.exists(TOKEN_JSON_PATH):
        try:
            os.remove(TOKEN_JSON_PATH)
        except OSError:
            pass
    if os.path.exists(LEGACY_TOKEN_PICKLE_PATH):
        try:
            os.remove(LEGACY_TOKEN_PICKLE_PATH)
        except OSError:
            pass
    return True
