import os
import json
import pickle
import tempfile
from google.oauth2.credentials import Credentials
from typing import Any, Dict, Optional
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


STUDYSUITE_DIR = os.path.join(os.path.expanduser("~"), ".studysuite")
TOKEN_JSON_PATH = os.path.join(STUDYSUITE_DIR, "token.json")
LEGACY_TOKEN_PICKLE_PATH = os.path.join(STUDYSUITE_DIR, "token.pickle")

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

def connect_youtube() -> Any:
    """Connect to YouTube API using OAuth and save credentials.
    
    Returns:
        Any: Google OAuth credentials object.
    """
    secret_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'client_secret.json')
    flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
    creds = flow.run_local_server(port=0)
    
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
