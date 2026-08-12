"""Verify Google auth end to end: token validity plus one live call per service.

A token can carry the right scopes and still fail if an API is not enabled on
the Cloud project, so this makes a real (tiny, read-only) request to each one.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ante_auth


def check(name, call):
    try:
        detail = call()
    except Exception as exc:
        print(f'  FAIL  {name:<9} {type(exc).__name__}: {str(exc)[:160]}')
        return False
    print(f'  OK    {name:<9} {detail}')
    return True


def main():
    try:
        creds = ante_auth.load_credentials()
    except ante_auth.AuthError as exc:
        print(f'AUTH FAILED\n\n{exc}')
        return 1

    granted = set(creds.scopes or [])
    print('Token scopes:')
    for scope in sorted(granted):
        marker = ' ' if scope in ante_auth.SCOPES else ' <- UNEXPECTED'
        print(f'  {scope}{marker}')
    missing = set(ante_auth.SCOPES) - granted
    if missing:
        print('\nMISSING scopes:')
        for scope in sorted(missing):
            print(f'  {scope}')

    print('\nLive API calls:')
    results = [
        check('calendar', lambda: '%d calendars' % len(
            ante_auth.get_service('calendar').calendarList()
            .list().execute().get('items', []))),
        check('gmail', lambda: ante_auth.get_service('gmail').users()
              .getProfile(userId='me').execute().get('emailAddress', '?')),
        check('tasks', lambda: '%d task lists' % len(
            ante_auth.get_service('tasks').tasklists()
            .list().execute().get('items', []))),
    ]

    ok = all(results) and not missing
    print('\n' + ('ALL GOOD' if ok else 'SOMETHING IS BROKEN -- see above'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
