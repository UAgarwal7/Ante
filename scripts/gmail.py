"""Gmail access for Ante. READ-ONLY BY CONSTRUCTION.

Auth comes from ante_auth, which grants gmail.readonly and nothing else. Sending,
drafting, archiving and labelling are therefore not merely unimplemented -- the
token cannot perform them. archive_email() and label_email() used to live here;
they were removed because they contradicted the scope policy and would now fail
at runtime anyway.

This module must never open a browser. The old InstalledAppFlow fallback would
fire on any refresh failure and silently replace the read-only token with a
write-capable one, undoing the containment boundary with no visible symptom.

Ante reads content that anyone can send it, and it runs with shell access, so
read-only IS the containment boundary. Do not add write functions here without
revisiting the scope decision in ante_auth.py first.
"""

import base64
import datetime
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ante_auth

# These are a FLOOR, not a gate. Anything matching is guaranteed to reach the
# briefing; everything else is still fetched and left to the model to judge.
# The previous version used these as a hard filter and dropped 92% of mail,
# including real signal -- see STATUS.md. Adding a term here widens what is
# guaranteed; it never narrows what is seen.
ALWAYS_SURFACE_SENDERS = ['umich.edu', 'canvas', 'gradescope']
ALWAYS_SURFACE_KEYWORDS = [
    'deadline', 'interview', 'offer', 'urgent', 'action required',
    'application', 'midterm', 'exam',
]


def always_surface(sender, subject, snippet):
    """Must this message reach the briefing regardless of model judgement?

    False does NOT mean "drop it" -- it means "no guarantee, let the model
    decide". Never use this to filter before the model sees the message.
    """
    haystacks = (sender.lower(), subject.lower(), snippet.lower())
    if any(s in haystacks[0] for s in ALWAYS_SURFACE_SENDERS):
        return True
    return any(k in haystacks[1] or k in haystacks[2] for k in ALWAYS_SURFACE_KEYWORDS)


def _walk_parts(payload):
    """Yield every part in a MIME tree, depth first.

    Real mail nests -- multipart/mixed wrapping multipart/alternative wrapping
    the content is routine -- so a flat scan of top-level parts misses the body
    entirely on a large fraction of messages.
    """
    yield payload
    for part in payload.get('parts') or []:
        yield from _walk_parts(part)


def _decode(part):
    data = part.get('body', {}).get('data')
    if not data:
        return ''
    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')


def _html_to_text(markup):
    text = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', markup)
    text = re.sub(r'(?is)<br\s*/?>', '\n', text)
    text = re.sub(r'(?is)</(p|div|tr|h[1-6])>', '\n', text)
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()


def get_email_body(service, msg_id, max_chars=2000):
    """Return (text, source) where source is 'plain', 'html', or 'none'.

    'none' is returned for image-only mail, which has no text anywhere -- not in
    the parts and not in Gmail's snippet. Handling that needs the vision path,
    which does not exist yet. The source field is here so an empty body is
    distinguishable from a body that failed to parse.
    """
    message = service.users().messages().get(
        userId='me', id=msg_id, format='full').execute()
    payload = message.get('payload', {})

    plain, markup = [], []
    for part in _walk_parts(payload):
        mime = part.get('mimeType', '')
        if mime == 'text/plain':
            if (chunk := _decode(part)):
                plain.append(chunk)
        elif mime == 'text/html':
            if (chunk := _decode(part)):
                markup.append(chunk)

    if plain:
        return '\n'.join(plain)[:max_chars], 'plain'
    if markup:
        return _html_to_text('\n'.join(markup))[:max_chars], 'html'
    return '', 'none'


def get_recent_emails(hours=24, max_results=50):
    """Every message from the last `hours`, annotated -- not filtered.

    Returns (messages, report). Each message carries always_surface so the
    briefing can guarantee inclusion without anything being dropped here.

    Returns a report for the same reason gcalendar does: an empty list is
    ambiguous between "no mail" and "broken", and the two need to be
    distinguishable.
    """
    service = ante_auth.get_service('gmail')
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)

    report = {
        'window_hours': hours,
        'cutoff': cutoff.isoformat(),
        'scanned': 0,
        'always_surface': 0,
        'failures': [],
        'truncated': False,
    }

    listed = service.users().messages().list(
        userId='me',
        q=f'after:{int(cutoff.timestamp())}',
        maxResults=max_results,
    ).execute()
    ids = listed.get('messages', [])
    report['truncated'] = bool(listed.get('nextPageToken'))

    messages = []
    for msg in ids:
        try:
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date'],
            ).execute()
        except Exception as exc:
            report['failures'].append({
                'id': msg['id'], 'error': f'{type(exc).__name__}: {exc}'})
            continue

        headers = {h['name']: h['value'] for h in message['payload']['headers']}
        sender = headers.get('From', '')
        subject = headers.get('Subject', '')
        snippet = message.get('snippet', '')
        flagged = always_surface(sender, subject, snippet)
        report['scanned'] += 1
        report['always_surface'] += int(flagged)

        messages.append({
            'id': msg['id'],
            'from': sender,
            'subject': subject,
            'date': headers.get('Date', ''),
            'snippet': snippet,
            'always_surface': flagged,
        })

    return messages, report


if __name__ == '__main__':
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    messages, report = get_recent_emails(hours=hours)
    print(json.dumps({'report': report, 'messages': messages}, indent=2))
    sys.exit(1 if report['failures'] else 0)
