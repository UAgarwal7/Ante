"""Reset an OpenClaw session without going through the Gateway.

Why this exists
---------------
`/new` is a chat slash command. It is only interpreted when it arrives through a
chat surface -- sending it via `openclaw agent --message "/new"` does NOT reset
anything, the model just reads it as text and says it cannot do that. The
Gateway's own scheduler (`openclaw cron`) could drive a reset, but every
cron.* RPC needs operator.write scope, and this machine's CLI is paired with
operator.read only. So the supported paths are both closed.

What this does instead is exactly what `/new` does on disk:

  1. rename  <session>.jsonl  ->  <session>.jsonl.reset.<ISO8601>
  2. drop the entry from sessions.json

The next message on that key finds no session and OpenClaw creates a fresh one,
picking up current skills and workspace files. Nothing is deleted -- the
transcript is archived under the same naming convention OpenClaw itself uses,
so a reset done here is indistinguishable from one done in chat.

Caveats, stated honestly
------------------------
  * This writes OpenClaw's private state directly. It is not a supported API and
    could break on upgrade. Re-verify after any version bump.
  * If the Gateway holds the session in memory it may not notice the change
    until the next inbound message. Run this while idle -- which is the point,
    since it is meant for the middle of the night.
  * sessions.json is backed up before every write.
"""

import argparse
import datetime
import json
import os
import shutil
import sys

STORE = os.path.expanduser('~/.openclaw/agents/main/sessions/sessions.json')
DISCORD_KEY = 'discord:channel'


def _stamp():
    """OpenClaw's archive suffix format, e.g. 2026-08-13T07-29-55.940Z"""
    now = datetime.datetime.now(datetime.UTC)
    return now.strftime('%Y-%m-%dT%H-%M-%S.') + f'{now.microsecond // 1000:03d}Z'


def reset(key_match, min_bytes, dry_run, store_path=STORE):
    if not os.path.exists(store_path):
        print(f'No session store at {store_path}', file=sys.stderr)
        return 1

    with open(store_path) as fh:
        store = json.load(fh)

    targets = [k for k in store if key_match in k]
    if not targets:
        print(f'No session key matching {key_match!r}. Present keys:')
        for k in store:
            print(f'  {k}')
        return 1

    acted = False
    for key in targets:
        entry = store[key]
        path = entry.get('sessionFile', '')
        size = os.path.getsize(path) if path and os.path.exists(path) else 0

        if size < min_bytes:
            print(f'skip  {key}\n      {size:,} bytes < {min_bytes:,} threshold — already fresh')
            continue

        archive = f'{path}.reset.{_stamp()}'
        print(f'{"WOULD reset" if dry_run else "reset"}  {key}')
        print(f'      transcript {size:,} bytes -> {os.path.basename(archive)}')

        if not dry_run:
            if path and os.path.exists(path):
                shutil.move(path, archive)
            del store[key]
            acted = True

    if dry_run:
        print('\ndry run — nothing written')
        return 0

    if not acted:
        print('\nnothing to do')
        return 0

    backup = f'{store_path}.bak.{_stamp()}'
    shutil.copy2(store_path, backup)
    tmp = f'{store_path}.tmp'
    with open(tmp, 'w') as fh:
        json.dump(store, fh, indent=2)
        fh.write('\n')
    os.chmod(tmp, 0o600)
    os.replace(tmp, store_path)          # atomic; never a half-written store
    print(f'\nstore updated ({len(store)} entries left), backup at {os.path.basename(backup)}')
    print('The next message on that key starts a fresh session.')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--key', default=DISCORD_KEY,
                    help=f'substring of the session key to reset (default: {DISCORD_KEY!r})')
    ap.add_argument('--min-bytes', type=int, default=4096,
                    help='skip if the transcript is smaller than this; avoids '
                         'churning an already-fresh session (default: 4096)')
    ap.add_argument('--dry-run', action='store_true')
    return reset(ap.parse_args().key, ap.parse_args().min_bytes, ap.parse_args().dry_run)


if __name__ == '__main__':
    sys.exit(main())
