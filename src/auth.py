import os
import json
from google.oauth2.credentials import Credentials
from typing import Any, Dict, Optional
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

def connect_youtube() -> Any:
    """Connect to YouTube API using OAuth and save credentials.
    
    Returns:
        Any: Google OAuth credentials object.
    """
    secret_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'client_secret.json')
    flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
    creds = flow.run_local_server(port=0)
    
    os.makedirs(os.path.expanduser('~/.studysuite'), exist_ok=True)
    with open(os.path.expanduser('~/.studysuite/yt_token.json'), 'w') as f:
        f.write(creds.to_json())
    return creds

def load_credentials() -> Optional[Any]:
    """Load saved YouTube API credentials from file, refreshing if necessary.
    
    Returns:
        Optional[Any]: Google OAuth credentials object if found and valid, None otherwise.
    """
    path = os.path.expanduser('~/.studysuite/yt_token.json')
    if not os.path.exists(path):
        return None
    try:
        creds = Credentials.from_authorized_user_file(path, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, 'w') as f:
                f.write(creds.to_json())
        return creds
    except Exception as e:
        raise ValueError("metadata_failed: Connect YouTube")


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
