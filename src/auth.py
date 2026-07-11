import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

def connect_youtube():
    flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
    creds = flow.run_local_server(port=0)
    
    os.makedirs(os.path.expanduser('~/.studysuite'), exist_ok=True)
    with open(os.path.expanduser('~/.studysuite/yt_token.pickle'), 'wb') as f:
        pickle.dump(creds, f)
    return creds

def load_credentials():
    path = os.path.expanduser('~/.studysuite/yt_token.pickle')
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(path, 'wb') as f:
            pickle.dump(creds, f)
    return creds

def get_video_metadata(video_id, creds):
    yt = build('youtube', 'v3', credentials=creds)
    resp = yt.videos().list(part='snippet,contentDetails', id=video_id).execute()
    if not resp.get('items'):
        raise ValueError("Video not found or access denied")
        
    item = resp['items'][0]
    title = item['snippet']['title']
    channel = item['snippet']['channelTitle']
    duration = item['contentDetails']['duration']  
    description = item['snippet']['description']
    
    return {
        'title': title, 
        'channel': channel, 
        'duration': duration, 
        'description': description
    }
