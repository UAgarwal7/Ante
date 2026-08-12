# Ante

A personal AI daily briefing agent built on [OpenClaw](https://openclaw.ai). Ante runs on my own machine, connects to my personal Google account (Gmail, Calendar, Tasks) and curated news sources, and is meant to deliver a concise morning briefing and evening check-in to Discord — then stay available for on-demand tasks throughout the day.

**Status: in development. It does not run end to end yet.** The section below is the design target; [What works today](#what-works-today) is the honest current state, and [STATUS.md](STATUS.md) has the details.

---

## The idea

Every morning at 10:30 AM, Ante pulls from four sources and sends a single, actionable summary to Discord:

- **Gmail** — flags important emails from professors, recruiters, and key senders, and surfaces anything with urgent keywords
- **Google Calendar** — summarizes the day's events, flags conflicts, and automatically blocks study time when deadlines are approaching
- **Google Tasks** — triages overdue and upcoming tasks by priority, factoring in calendar load and deadline type
- **News digest** — 3 bullets covering ML/AI research, tech startups, and university CS news from sources like Hacker News, arxiv, TechCrunch, and The Batch

At 10:30 PM, a lighter evening check-in reviews what got done, previews tomorrow, and recaps any urgent emails from the day.

Beyond the scheduled briefings, Ante is available on-demand in Discord at any time — ask it what's due, reschedule an event, or add a task.

---

## What works today

| Piece | State |
|---|---|
| Google OAuth for all three APIs | ✅ Working and verified |
| Calendar — read events | ✅ Working (`get_events`) |
| Calendar — create events | ✅ Working (`create_event`) |
| Gmail — read and flag recent mail | ✅ Working (`get_flagged_emails`) |
| Google Tasks | ❌ Not started — no code yet |
| News digest | ❌ Not started — no code yet |
| Briefing assembler (combining the pillars into one message) | ❌ Not started |
| Scheduled morning / evening runs | ❌ **No cron is configured.** Nothing runs automatically. |
| Conflict detection, study blocking, event rescheduling | ❌ Not started |

So the scheduled briefings described above don't happen yet, and the pillars aren't wired together. Reading calendar events and flagging recent email both work when run by hand.

---

## Permissions

Ante's Google access is deliberately narrow. [`scripts/ante_auth.py`](scripts/ante_auth.py) is the intended single source of truth for the scope list, so the individual scripts can't drift apart — the granted token carries exactly these:

| Service | Access | Scope |
|---|---|---|
| Gmail | **read-only** | `gmail.readonly` |
| Calendar | read/write events | `calendar.events` |
| Calendar | read-only | `calendar.calendarlist.readonly` |
| Tasks | read/write | `tasks` |

**Gmail is read-only and stays that way.** Ante can't send, draft, archive, or label — the granted token itself can't do it, so it isn't a promise in code that a bug could break. Ante reads content that anyone can send you, and it's an LLM with shell access; read-only means the worst case of a malicious email is a bad summary rather than mail leaving the account. Google has no draft-without-send scope, so drafting would mean granting send. Ante writes suggested replies into Discord instead, and you paste them yourself.

Calendar and Tasks are read/write because blocking study time and managing tasks require it.

⚠️ **Two caveats, both being fixed in the current migration:** `scripts/gmail.py` and `scripts/gcalendar.py` haven't been moved onto `ante_auth.py` yet — they still declare their own scope lists and their own browser-consent fallback. And `gcalendar.py` still contains a `delete_event` function, which the no-deletion policy removes. The scopes above are what's actually granted; the migration is what makes the code match. See [STATUS.md](STATUS.md).

---

## Why I built this

I was spending too much time each morning context-switching between Gmail, Google Calendar, Google Tasks, and various news sources just to figure out what my day looked like. Ante replaces that with one message I can actually respond to.

---

## Built with

- [OpenClaw](https://openclaw.ai) — agent framework and runtime
- [Discord](https://discord.com) — delivery channel and interaction interface
- Google APIs — Gmail, Google Calendar, Google Tasks
- Claude (Haiku 4.5) — LLM backend for reasoning and summarization
- *Planned:* Hacker News, arxiv, TechCrunch, The Batch, Import AI, MIT Technology Review, Hugging Face blog, and campus news as digest sources — not yet integrated

---

## Project status

**In active development.** Current engineering state, open problems, and design decisions live in [STATUS.md](STATUS.md).

- [x] Phase 1 — OpenClaw installed and connected to Discord
- [x] Google OAuth — scopes locked down and verified across all three APIs
- [ ] Phase 2 — Google Calendar: read and create work; guardrails and migration in progress
- [ ] Phase 3 — Gmail read path built; Google Tasks not started
- [ ] Phase 4 — Morning briefing cron and news digest
- [ ] Phase 5 — Evening check-in, smart triggers, study block logic

---

## Setup

Setup guide coming once the project is stable. Built for personal use — currently configured for my own Google account and Discord server.

---

## Notes

This is a personal project and a learning exercise. API keys and OAuth tokens are not committed to this repo. See `.gitignore`.

Project spec can be found under [docs/product-summary.md](docs/product-summary.md) — note that it's the original spec and is aspirational in places.
