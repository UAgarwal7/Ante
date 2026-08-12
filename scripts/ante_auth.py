"""Central Google OAuth for Ante.

All three services share one token file, so the scope list has to be defined in
exactly one place -- if two scripts disagree, google-auth rejects the token and
you get a silent re-auth loop.

Scope policy (deliberate, per service):

  Calendar  read/write   Two narrow scopes instead of full 'calendar':
                           calendar.events              read/write events only
                           calendar.calendarlist.readonly   enumerate calendars

                         events is what backs study blocks and focus time.
                         calendarlist.readonly is required separately --
                         calendarList.list is NOT covered by calendar.events,
                         and without it get_events() cannot discover the shared
                         UMich calendar. Read-only, so Ante can see the calendar
                         list but not subscribe or unsubscribe.

                         Neither scope grants ACL changes, calendar creation or
                         deletion, or settings access, which full 'calendar'
                         would. Deletion of events is still reachable at the API
                         level under calendar.events, so the no-delete guardrail
                         lives in the code -- see gcalendar.py.
  Gmail     read-only    Hard constraint. No send, no archive, no label, no
                         inbox mutation of any kind.
  Tasks     read/write   Backs "add a task", "mark complete", "change the due
                         date" from the product spec. The Tasks API has no
                         granular scopes -- 'tasks' is the only write option and
                         it also permits deleting tasks and whole task lists.
                         Expose task deletion only if that is a deliberate
                         choice; the scope will not stop you.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CREDENTIALS_FILE = os.path.expanduser('~/.openclaw/google_credentials.json')
TOKEN_FILE = os.path.expanduser('~/.openclaw/google_token.json')

SERVICE_SCOPES = {
    'calendar': [
        'https://www.googleapis.com/auth/calendar.events',
        'https://www.googleapis.com/auth/calendar.calendarlist.readonly',
    ],
    'gmail': ['https://www.googleapis.com/auth/gmail.readonly'],
    'tasks': ['https://www.googleapis.com/auth/tasks'],
}

# The single token covers every service, so it carries the union.
SCOPES = [scope for scopes in SERVICE_SCOPES.values() for scope in scopes]

_API_VERSIONS = {'calendar': 'v3', 'gmail': 'v1', 'tasks': 'v1'}


class AuthError(RuntimeError):
    """Raised when the stored token is unusable and needs a manual re-auth."""


def load_credentials():
    """Return valid credentials, refreshing if needed.

    Never launches a browser -- a background briefing run must fail loudly
    rather than block forever on a consent screen it cannot show. Run
    scripts/auth_setup.py by hand to (re)authorize.
    """
    if not os.path.exists(TOKEN_FILE):
        raise AuthError(
            f'No token at {TOKEN_FILE}. Run: ./scripts/run_auth_setup.sh'
        )

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise AuthError(
                f'Token refresh failed ({exc}). This usually means the OAuth '
                'consent screen is still in Testing mode, which expires refresh '
                'tokens after 7 days. Set it to Production in the Google Cloud '
                'console, then run: ./scripts/run_auth_setup.sh'
            ) from exc
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        return creds

    raise AuthError(
        f'Token at {TOKEN_FILE} is invalid and has no refresh token. '
        'Run: ./scripts/run_auth_setup.sh'
    )


def get_service(name):
    """Build an API client for 'calendar', 'gmail', or 'tasks'."""
    if name not in _API_VERSIONS:
        raise ValueError(f'Unknown service {name!r}')
    return build(name, _API_VERSIONS[name], credentials=load_credentials())


def authorize():
    """Run the interactive consent flow. Requires a browser."""
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, 'w') as token:
        token.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)
    return creds
