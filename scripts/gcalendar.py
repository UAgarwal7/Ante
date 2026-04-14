import datetime
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = os.path.expanduser('~/.openclaw/google_credentials.json')
TOKEN_FILE = os.path.expanduser('~/.openclaw/google_token.json')

def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def get_events(days=1):
    service = get_calendar_service()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    end = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=days)).isoformat()
    
    all_events = []
    calendars = service.calendarList().list().execute().get('items', [])
    
    for calendar in calendars:
        events_result = service.events().list(
            calendarId=calendar['id'],
            timeMin=now,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        for event in events:
            all_events.append({
                'calendar': calendar['summary'],
                'title': event.get('summary', 'No title'),
                'start': event['start'].get('dateTime', event['start'].get('date')),
                'end': event['end'].get('dateTime', event['end'].get('date')),
                'location': event.get('location', ''),
                'description': event.get('description', '')
            })
    
    all_events.sort(key=lambda x: x['start'])
    return all_events

def create_event(title, start_time, end_time, description='', location=''):
    service = get_calendar_service()
    event = {
        'summary': title,
        'location': location,
        'description': description,
        'start': {
            'dateTime': start_time,
            'timeZone': 'America/Detroit',
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'America/Detroit',
        },
    }
    event = service.events().insert(calendarId='primary', body=event).execute()
    return event.get('htmlLink')

if __name__ == '__main__':
    # Test reading
    events = get_events(days=1)
    print(json.dumps(events, indent=2))
    