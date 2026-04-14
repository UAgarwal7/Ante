# Google Calendar

Use this skill whenever the user asks about their calendar, events, schedule, or wants to add/edit/move events.

## Reading events

To get the user's calendar events, run this command:

```bash
cd /Users/utsavagarwal/Ante && source venv/bin/activate && python3 scripts/gcalendar.py
```

This returns a JSON list of today's events. Parse the output and summarize it naturally for the user.

## Creating events

To create an event, run:

```bash
cd /Users/utsavagarwal/Ante && source venv/bin/activate && python3 -c "
from scripts.gcalendar import create_event
result = create_event('[TITLE]', '[START]', '[END]', '[DESCRIPTION]')
print(result)
"
```

Replace the placeholders with the actual values from the user's request. Use ISO 8601 format for times, e.g. 2026-04-15T15:00:00. Always use America/Detroit as the timezone.

## Guidelines

- Always confirm with the user before creating or editing events
- When summarizing events, use natural language — not raw JSON
- If no events exist for the day, tell the user their schedule is clear
- For event creation, confirm the details back to the user before running the command