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

import datetime
import os
from zoneinfo import ZoneInfo

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


_LOCAL_TZ = None
_LOCAL_TZ_AT = None

# Re-resolve the timezone this often. Relocation is the only thing that changes
# it and that happens on the scale of months, so this is deliberately generous;
# the point is only that a long-lived process cannot pin the wrong zone forever.
_LOCAL_TZ_TTL = datetime.timedelta(hours=1)


def local_timezone():
    """The timezone the user actually sees their calendar in.

    Resolved from the primary calendar rather than hardcoded, because it *was*
    hardcoded to America/Detroit while every calendar on the account is
    America/Los_Angeles -- so every event Ante created landed three hours off,
    with a confirmation that read as correct. A student moves between term-time
    and internship timezones and will not remember to update a constant.

    Anchoring to the calendar's own setting also guarantees Ante can never
    disagree with what Google renders: "3pm" means the same instant in both.

    Cached with a TTL rather than forever. Every script today is a short-lived
    subprocess, so this never matters -- but if the OpenClaw gateway ever
    imports these modules into a long-running process, a permanent cache would
    pin a stale zone across a move until someone restarted it.

    A cached ZoneInfo is a zone, not an offset, so DST is still applied per date
    and needs no refresh. Only relocation does.

    Falls back to the system timezone if the lookup fails, which is still far
    better than a fixed guess.
    """
    global _LOCAL_TZ, _LOCAL_TZ_AT
    now = datetime.datetime.now(datetime.UTC)
    if _LOCAL_TZ is not None and now - _LOCAL_TZ_AT < _LOCAL_TZ_TTL:
        return _LOCAL_TZ

    resolved = None
    try:
        # calendarList.get is covered by calendar.calendarlist.readonly.
        # calendar.settings.readonly would be a new scope, so avoid it.
        tz = get_service('calendar').calendarList().get(
            calendarId='primary').execute().get('timeZone')
        resolved = ZoneInfo(tz) if tz else None
    except Exception:
        resolved = None
    if resolved is None:
        resolved = datetime.datetime.now().astimezone().tzinfo

    _LOCAL_TZ, _LOCAL_TZ_AT = resolved, now
    return _LOCAL_TZ


def authorize():
    """Run the interactive consent flow. Requires a browser."""
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, 'w') as token:
        token.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)
    return creds
