"""Google Tasks access for Ante.

Auth comes from ante_auth. Like the other two modules this must never open a
browser -- see ante_auth.load_credentials.

There is deliberately NO delete function, for tasks or for task lists. The Tasks
API has no granular scopes: 'tasks' is the only writable option and it also
permits deleting individual tasks and entire lists. So "Ante never deletes your
tasks" is not enforced by Google at all -- it is enforced by this file not having
the function, exactly like gcalendar.delete_event. Completing a task is the
reversible alternative and is what should always be used instead.

A note on due dates: the Tasks API stores `due` as RFC3339 but only honours the
DATE part. Times are silently discarded, so a task cannot be due at 3pm. Callers
pass YYYY-MM-DD and should not imply a time to the user.
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ante_auth


def LOCAL_TZ():
    """Resolved from the primary calendar, not hardcoded. See ante_auth."""
    return ante_auth.local_timezone()


DEFAULT_LIST = '@default'

# Distinguishes "argument not supplied" from an explicit None. update_task needs
# this because None is a meaningful value there -- it means "clear the due date".
_UNSET = object()


def _due_to_rfc3339(due):
    """'YYYY-MM-DD' -> RFC3339 UTC midnight, which is what the API expects."""
    if not due:
        return None
    try:
        day = datetime.date.fromisoformat(due)
    except ValueError as exc:
        raise ValueError(f'due must be YYYY-MM-DD, got {due!r}') from exc
    return f'{day.isoformat()}T00:00:00.000Z'


def _due_to_date(due):
    """RFC3339 from the API -> 'YYYY-MM-DD', or '' when unset."""
    return due[:10] if due else ''


def get_tasks(include_completed=False):
    """Open tasks across every task list.

    Returns (tasks, report). The report exists for the same reason it does in
    gcalendar and gmail: an empty list is ambiguous between "nothing due" and
    "this is broken", and a briefing needs to tell those apart.
    """
    service = ante_auth.get_service('tasks')
    today = datetime.datetime.now(LOCAL_TZ()).date()

    report = {
        'lists_found': 0,
        'lists_queried': 0,
        'open': 0,
        'overdue': 0,
        'include_completed': include_completed,
        'failures': [],
    }

    try:
        tasklists = service.tasklists().list().execute().get('items', [])
    except Exception as exc:
        report['failures'].append({'list': '*', 'error': f'{type(exc).__name__}: {exc}'})
        return [], report

    report['lists_found'] = len(tasklists)

    out = []
    for tasklist in tasklists:
        try:
            result = service.tasks().list(
                tasklist=tasklist['id'],
                showCompleted=include_completed,
                showHidden=include_completed,
                maxResults=100,
            ).execute()
        except Exception as exc:
            # One unreadable list must not silently empty the whole briefing.
            report['failures'].append({
                'list': tasklist.get('title', tasklist['id']),
                'error': f'{type(exc).__name__}: {exc}',
            })
            continue

        report['lists_queried'] += 1
        for task in result.get('items', []):
            due = _due_to_date(task.get('due'))
            overdue = bool(due and due < today.isoformat()
                           and task.get('status') != 'completed')
            if task.get('status') != 'completed':
                report['open'] += 1
            report['overdue'] += int(overdue)
            out.append({
                'id': task['id'],
                'list': tasklist.get('title', ''),
                'list_id': tasklist['id'],
                'title': task.get('title', '(untitled)'),
                'notes': (task.get('notes') or '')[:500],
                'due': due,
                'overdue': overdue,
                'status': task.get('status', ''),
            })

    # Undated tasks sort last -- they are real work, just unscheduled, so they
    # must not be dropped from the briefing.
    out.sort(key=lambda t: (t['due'] == '', t['due'], t['title'].lower()))
    return out, report


def add_task(title, due=None, notes='', tasklist=DEFAULT_LIST):
    """Create a task. `due` is YYYY-MM-DD; the API ignores any time component."""
    service = ante_auth.get_service('tasks')
    body = {'title': title}
    if notes:
        body['notes'] = notes
    if due:
        body['due'] = _due_to_rfc3339(due)
    created = service.tasks().insert(tasklist=tasklist, body=body).execute()
    return {
        'id': created['id'],
        'title': created.get('title', ''),
        'due': _due_to_date(created.get('due')),
        'status': created.get('status', ''),
    }


def update_task(task_id, tasklist=DEFAULT_LIST, title=None, due=_UNSET, notes=None):
    """Change an existing task. Only the fields you pass are touched.

    `due` distinguishes three cases, which is why it needs a sentinel rather
    than None:
        omitted        leave the due date alone
        due='2026-09-01'  set it
        due=None       clear it, making the task undated

    Without the sentinel, "clear the due date" and "don't touch it" would be the
    same call, and one of them would be unreachable.
    """
    service = ante_auth.get_service('tasks')
    body = {}

    if title is not None:
        body['title'] = title
    if notes is not None:
        body['notes'] = notes
    if due is not _UNSET:
        body['due'] = _due_to_rfc3339(due) if due else None

    if not body:
        raise ValueError('update_task called with nothing to change')

    updated = service.tasks().patch(
        tasklist=tasklist, task=task_id, body=body).execute()
    return {
        'id': updated['id'],
        'title': updated.get('title', ''),
        'due': _due_to_date(updated.get('due')),
        'notes': (updated.get('notes') or '')[:500],
        'status': updated.get('status', ''),
    }


def complete_task(task_id, tasklist=DEFAULT_LIST):
    """Mark a task complete. Reversible -- use this, never deletion."""
    service = ante_auth.get_service('tasks')
    updated = service.tasks().patch(
        tasklist=tasklist, task=task_id, body={'status': 'completed'}).execute()
    return {
        'id': updated['id'],
        'title': updated.get('title', ''),
        'status': updated.get('status', ''),
        'completed': updated.get('completed', ''),
    }


def reopen_task(task_id, tasklist=DEFAULT_LIST):
    """Undo a completion. Exists so completing is safe to do without confirming."""
    service = ante_auth.get_service('tasks')
    updated = service.tasks().patch(
        tasklist=tasklist, task=task_id,
        body={'status': 'needsAction', 'completed': None}).execute()
    return {
        'id': updated['id'],
        'title': updated.get('title', ''),
        'status': updated.get('status', ''),
    }


if __name__ == '__main__':
    include_completed = '--all' in sys.argv[1:]
    tasks, report = get_tasks(include_completed=include_completed)
    print(json.dumps({'report': report, 'tasks': tasks}, indent=2))
    sys.exit(1 if report['failures'] else 0)
