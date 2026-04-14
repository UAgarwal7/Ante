import os
import json
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.modify'
]
CREDENTIALS_FILE = os.path.expanduser('~/.openclaw/google_credentials.json')
TOKEN_FILE = os.path.expanduser('~/.openclaw/google_token.json')

IMPORTANT_SENDERS = ['umich.edu', 'canvas', 'gradescope']
IMPORTANT_KEYWORDS = ['deadline', 'interview', 'offer', 'urgent', 'action required', 'application', 'midterm', 'exam']

def get_gmail_service():
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
    return build('gmail', 'v1', credentials=creds)

def get_email_body(service, msg_id):
    message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = message.get('payload', {})
    parts = payload.get('parts', [])
    body = ''
    if parts:
        for part in parts:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    break
    else:
        data = payload.get('body', {}).get('data', '')
        if data:
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    return body[:500]

def is_important(sender, subject, snippet):
    sender_lower = sender.lower()
    subject_lower = subject.lower()
    snippet_lower = snippet.lower()
    for s in IMPORTANT_SENDERS:
        if s in sender_lower:
            return True
    for k in IMPORTANT_KEYWORDS:
        if k in subject_lower or k in snippet_lower:
            return True
    return False

def get_flagged_emails(max_results=20):
    service = get_gmail_service()
    results = service.users().messages().list(
        userId='me',
        q='newer_than:1d',
        maxResults=max_results
    ).execute()
    messages = results.get('messages', [])
    flagged = []
    for msg in messages:
        message = service.users().messages().get(
            userId='me',
            id=msg['id'],
            format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']
        ).execute()
        headers = {h['name']: h['value'] for h in message['payload']['headers']}
        sender = headers.get('From', '')
        subject = headers.get('Subject', '')
        date = headers.get('Date', '')
        snippet = message.get('snippet', '')
        if is_important(sender, subject, snippet):
            flagged.append({
                'id': msg['id'],
                'from': sender,
                'subject': subject,
                'date': date,
                'snippet': snippet
            })
    return flagged

def archive_email(email_id):
    service = get_gmail_service()
    service.users().messages().modify(
        userId='me',
        id=email_id,
        body={'removeLabelIds': ['INBOX']}
    ).execute()
    return f"Email {email_id} archived."

def label_email(email_id, label_name):
    service = get_gmail_service()
    labels = service.users().labels().list(userId='me').execute()
    label_id = None
    for label in labels.get('labels', []):
        if label['name'].lower() == label_name.lower():
            label_id = label['id']
            break
    if not label_id:
        new_label = service.users().labels().create(
            userId='me',
            body={'name': label_name}
        ).execute()
        label_id = new_label['id']
    service.users().messages().modify(
        userId='me',
        id=email_id,
        body={'addLabelIds': [label_id]}
    ).execute()
    return f"Email {email_id} labeled as {label_name}."

if __name__ == '__main__':
    emails = get_flagged_emails()
    print(json.dumps(emails, indent=2))