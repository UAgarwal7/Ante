"""Google Calendar access for Ante.

Auth comes from ante_auth. This module must never open a browser: a briefing run
has no one to show a consent screen to, and the old browser fallback here would
silently re-grant broader scopes than the scope policy allows. See ante_auth.

There is deliberately NO delete_event(). The calendar.events scope permits
events.delete, so "Ante never deletes calendar events" is not enforced by Google
-- it is enforced by this file not having the function. Do not add one back
without changing the scope policy in ante_auth.py at the same time.
"""

import datetime
import re
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ante_auth


def LOCAL_TZ():
    """Resolved from the primary calendar, not hardcoded. See ante_auth."""
    return ante_auth.local_timezone()


# Event descriptions are unbounded and can be enormous -- a single invite pulled
# ~4KB of marketing copy in testing. Two reasons to cap them: they would dominate
# the briefing's token budget, and anyone who can send a calendar invite controls
# that text, which then reaches an LLM with shell access. Same untrusted-input
# position as email, so treat it the same way.
MAX_DESCRIPTION_CHARS = 500


def _window(days, mode, now=None):
    """Return (start, end) as aware datetimes in LOCAL_TZ.

    'calendar' -- local midnight today through the end of the last day in range.
                  This is what a briefing means by "today".
    'rolling'  -- now through now + days*24h.

    The two diverge sharply in the evening: at 9pm 'rolling' is mostly tomorrow,
    which is why a briefing should not use it to say "today".
    """
    now = now or datetime.datetime.now(LOCAL_TZ())
    if mode == 'rolling':
        return now, now + datetime.timedelta(days=days)
    if mode == 'calendar':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + datetime.timedelta(days=days)
    raise ValueError(f"unknown window mode {mode!r} (want 'calendar' or 'rolling')")


def get_events(days=1, mode='calendar'):
    """Events across every calendar in the window.

    Returns (events, report). The report exists because an empty event list
    means nothing on its own -- a permission error, a failed calendar, and a
    genuinely free day all produce []. report tells you how many calendars were
    actually queried and which ones failed, so callers can tell "you have
    nothing on" from "this is broken".
    """
    service = ante_auth.get_service('calendar')
    start, end = _window(days, mode)

    report = {
        'window_mode': mode,
        'window_start': start.isoformat(),
        'window_end': end.isoformat(),
        'calendars_found': 0,
        'calendars_queried': 0,
        'duplicates_collapsed': 0,
        'failures': [],
    }

    try:
        calendars = service.calendarList().list().execute().get('items', [])
    except Exception as exc:
        # Without calendar.calendarlist.readonly this 403s, and every calendar
        # silently disappears. Surface it instead of returning an empty day.
        report['failures'].append({'calendar': '*', 'error': f'{type(exc).__name__}: {exc}'})
        return [], report

    report['calendars_found'] = len(calendars)

    all_events = []
    for calendar in calendars:
        try:
            events_result = service.events().list(
                calendarId=calendar['id'],
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy='startTime',
            ).execute()
        except Exception as exc:
            # One inaccessible calendar must not zero out the others.
            report['failures'].append({
                'calendar': calendar.get('summary', calendar['id']),
                'error': f'{type(exc).__name__}: {exc}',
            })
            continue

        report['calendars_queried'] += 1
        for event in events_result.get('items', []):
            description = event.get('description', '') or ''
            all_events.append({
                'id': event['id'],
                'calendar': calendar.get('summary', ''),
                # Needed to update the event later -- an event ID is only
                # meaningful together with the calendar it lives on, and most of
                # these are not on 'primary'.
                'calendar_id': calendar['id'],
                'title': event.get('summary', 'No title'),
                'start': event['start'].get('dateTime', event['start'].get('date')),
                'end': event['end'].get('dateTime', event['end'].get('date')),
                'location': event.get('location', ''),
                'description': description[:MAX_DESCRIPTION_CHARS],
                'description_truncated': len(description) > MAX_DESCRIPTION_CHARS,
            })

    # The same event often lands on two calendars (a shared calendar plus a
    # personal copy of the invite), which would double it in the briefing.
    # Collapse on time+title and record how many were merged, so a collapse is
    # visible rather than silent.
    deduped, seen = [], set()
    for event in all_events:
        key = (event['title'], event['start'], event['end'])
        if key in seen:
            report['duplicates_collapsed'] += 1
            continue
        seen.add(key)
        deduped.append(event)

    deduped.sort(key=lambda x: x['start'])
    return deduped, report


VALID_BYDAY = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')


def weekly_rrule(days, until):
    """Build the RRULE for a class that meets the same days every week.

    days:  ['MO','WE','FR'] or 'MO,WE,FR' -- iCalendar two-letter codes
    until: 'YYYY-MM-DD', the last day the class meets (inclusive)

    Returns a list suitable for create_event(recurrence=...).

    UNTIL must be UTC when the event carries a timezone, so the local
    end-of-day is converted rather than formatted verbatim. Getting this
    wrong silently drops or adds a final week -- exactly the class of error
    that put every event three hours off before.
    """
    if isinstance(days, str):
        days = [d.strip() for d in days.split(',') if d.strip()]
    days = [d.upper() for d in days]
    bad = [d for d in days if d not in VALID_BYDAY]
    if bad:
        raise ValueError(
            f'Unknown day code(s): {bad}. Use two-letter codes from '
            f'{VALID_BYDAY} -- e.g. Tuesday is TU, Thursday is TH.')
    if not days:
        raise ValueError('weekly_rrule needs at least one day')

    try:
        last = datetime.date.fromisoformat(until)
    except ValueError:
        raise ValueError(f'until must be YYYY-MM-DD, got {until!r}')

    end_local = datetime.datetime.combine(
        last, datetime.time(23, 59, 59), tzinfo=LOCAL_TZ())
    end_utc = end_local.astimezone(datetime.timezone.utc)
    return [f'RRULE:FREQ=WEEKLY;BYDAY={",".join(days)};'
            f'UNTIL={end_utc.strftime("%Y%m%dT%H%M%SZ")}']


def _check_start_matches_rrule(start_time, recurrence):
    """A DTSTART that is not itself on a BYDAY day produces a stray event.

    Google emits the DTSTART instance regardless of BYDAY, so a Monday-Wednesday
    class whose start_time lands on a Sunday quietly gains a Sunday meeting.
    Catch it here rather than discovering it in the calendar grid.
    """
    if not recurrence:
        return
    byday = set()
    for rule in recurrence:
        m = re.search(r'BYDAY=([A-Z,]+)', rule)
        if m:
            byday.update(m.group(1).split(','))
    if not byday:
        return
    start_code = VALID_BYDAY[datetime.datetime.fromisoformat(start_time).weekday()]
    if start_code not in byday:
        raise ValueError(
            f'start_time falls on {start_code} but the rule only covers '
            f'{sorted(byday)}. Google would add a stray {start_code} meeting. '
            f'Move start_time to the first real meeting of the term.')


def create_event(title, start_time, end_time, description='', location='',
                 recurrence=None):
    """Create an event on the primary calendar. Times are ISO 8601, local tz.

    recurrence: list of RRULE strings, e.g. from weekly_rrule(). One
    recurring event beats hundreds of singles -- Ante cannot delete, so a
    mistake spread over 200 events has to be cleaned up by hand, while a
    mistake in one recurring event is a single update_event call.
    """
    _check_start_matches_rrule(start_time, recurrence)
    service = ante_auth.get_service('calendar')
    event = {
        'summary': title,
        'location': location,
        'description': description,
        'start': {'dateTime': start_time, 'timeZone': str(LOCAL_TZ())},
        'end': {'dateTime': end_time, 'timeZone': str(LOCAL_TZ())},
    }
    if recurrence:
        event['recurrence'] = list(recurrence)
    created = service.events().insert(calendarId='primary', body=event).execute()
    return created.get('htmlLink')


def update_event(event_id, calendar_id='primary', title=None, start_time=None,
                 end_time=None, description=None, location=None,
                 recurrence=None):
    """Change an existing event. Only the fields you pass are touched.

    This is what "reschedule my 3pm to tomorrow" runs. It is a patch, not a
    delete-and-recreate, so the event keeps its ID, its guests and their RSVPs.
    Recreating instead would lose all of that -- and Ante cannot delete anyway.

    `calendar_id` matters: most events are not on 'primary'. Pass the
    `calendar_id` from get_events(); the default is only right for events Ante
    created itself.

    Passing start_time without end_time keeps the original duration, which is
    what a reschedule almost always means.
    """
    service = ante_auth.get_service('calendar')
    body = {}

    if title is not None:
        body['summary'] = title
    if description is not None:
        body['description'] = description
    if location is not None:
        body['location'] = location
    if recurrence is not None:
        body['recurrence'] = list(recurrence)

    if start_time and not end_time:
        existing = service.events().get(
            calendarId=calendar_id, eventId=event_id).execute()
        old_start = existing['start'].get('dateTime')
        old_end = existing['end'].get('dateTime')
        if not old_start or not old_end:
            raise ValueError(
                'Cannot shift an all-day event by time. Pass both start_time '
                'and end_time, or edit it in Google Calendar.')
        duration = (datetime.datetime.fromisoformat(old_end)
                    - datetime.datetime.fromisoformat(old_start))
        new_start = datetime.datetime.fromisoformat(start_time)
        end_time = (new_start + duration).isoformat()

    if start_time:
        body['start'] = {'dateTime': start_time, 'timeZone': str(LOCAL_TZ())}
    if end_time:
        body['end'] = {'dateTime': end_time, 'timeZone': str(LOCAL_TZ())}

    if not body:
        raise ValueError('update_event called with nothing to change')

    updated = service.events().patch(
        calendarId=calendar_id, eventId=event_id, body=body).execute()
    return {
        'id': updated['id'],
        'title': updated.get('summary', ''),
        'start': updated['start'].get('dateTime', updated['start'].get('date')),
        'end': updated['end'].get('dateTime', updated['end'].get('date')),
        'location': updated.get('location', ''),
        'link': updated.get('htmlLink', ''),
    }


if __name__ == '__main__':
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    mode = sys.argv[2] if len(sys.argv) > 2 else 'calendar'
    events, report = get_events(days=days, mode=mode)
    print(json.dumps({'report': report, 'events': events}, indent=2))
    # Non-zero exit when a calendar failed, so a broken run is not mistaken for
    # a free day by anything checking the exit code.
    sys.exit(1 if report['failures'] else 0)
