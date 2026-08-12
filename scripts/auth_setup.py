"""One-time interactive Google authorization for Ante.

Opens a browser, walks the consent screen, and writes ~/.openclaw/google_token.json.
Run this by hand -- never from a scheduled briefing.

Before running, confirm the OAuth consent screen is set to Production in the
Google Cloud console. In Testing mode Google expires refresh tokens after 7
days and this will all break again next week.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ante_auth


def main():
    print('Ante will request these scopes:\n')
    for service, scopes in ante_auth.SERVICE_SCOPES.items():
        for scope in scopes:
            access = 'read-only' if scope.endswith('.readonly') else 'READ/WRITE'
            print(f'  {service:<9} {access:<10} {scope}')
    print()

    if os.path.exists(ante_auth.TOKEN_FILE):
        backup = ante_auth.TOKEN_FILE + '.bak'
        shutil.copy2(ante_auth.TOKEN_FILE, backup)
        os.remove(ante_auth.TOKEN_FILE)
        print(f'Existing token backed up to {backup} and cleared.')

    print('Opening browser for consent...\n')
    creds = ante_auth.authorize()

    granted = set(creds.scopes or [])
    requested = set(ante_auth.SCOPES)

    print(f'\nToken written to {ante_auth.TOKEN_FILE}\n')
    print('Granted scopes:')
    for scope in sorted(granted):
        print(f'  {scope}')

    missing = requested - granted
    extra = granted - requested
    if missing:
        print('\nMISSING (consent was not fully granted):')
        for scope in sorted(missing):
            print(f'  {scope}')
    if extra:
        print('\nUNREQUESTED extra scopes granted by Google:')
        for scope in sorted(extra):
            print(f'  {scope}')

    if not missing:
        print('\nAll requested scopes granted. Verify with: ./scripts/run_auth_check.sh')
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
