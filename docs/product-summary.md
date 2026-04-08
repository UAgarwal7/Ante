# OpenClaw Morning Briefing — Product Summary

**Project Name:** Ante
**Author:** Utsav
**Version:** 0.3
**Last Updated:** April 2026

---

## Overview

A personal AI daily briefing agent built on OpenClaw. The agent runs automatically twice a day — a full morning briefing at 10:30 AM and a lighter evening check-in at 10:30 PM — delivering summaries and prompts via Discord. It pulls from Gmail, Google Calendar, Google Tasks, and curated news sources, synthesizes everything into a concise briefing, and remains available on-demand throughout the day for any follow-up actions or queries.

The agent operates in two modes:

- **Scheduled** — automatic morning briefing and evening check-in at set times
- **On-demand** — available at any point during the day to answer questions, fetch summaries, or take actions across any of the connected pillars

The agent maintains a neutral tone with no custom personality — focused purely on utility.

---

## Informal Summary

A bot that messages you on Discord every morning and night to keep you on top of your life. It checks your email, calendar, and to-do list, tells you what actually matters, and pulls in tech news so you're not completely out of the loop. You can text it back to get things done — move a meeting, draft an email, add a task — without opening a bunch of different apps. It also does some thinking for you, like automatically blocking study time when you have a project or exam coming up. A personal assistant that lives in Discord and runs on your own computer.

---

## Technologies

- **OpenClaw** — the agent framework that ties everything together, handles scheduling, channel delivery, and tool orchestration
- **Discord** — the interface you interact through, both for receiving briefings and sending commands
- **Google Workspace APIs** — Gmail, Google Calendar, and Google Tasks for reading and writing your productivity data
- **Claude / LLM backend** — the AI model powering the agent's reasoning, summarization, and prioritization logic
- **OpenClaw cron** — handles the 10:30 AM and 10:30 PM scheduled triggers
- **News sources** — fetched on a schedule via web scraping or RSS (see News & Research Digest pillar)

---

## Delivery

- **Channel:** Discord
- **Morning Briefing:** Every day at 10:30 AM via OpenClaw cron
- **Evening Check-in:** Every day at 10:30 PM via OpenClaw cron
- **Catch-up:** Message the agent "catch me up" at any time to get a summary of anything urgent from the last 24 hours

---

## Scheduled Briefings

### Morning Briefing (10:30 AM)

Covers all four pillars in sequence: email highlights, today's schedule, task triage, and news digest. After delivery, the agent remains in an interactive conversational state — you can reply directly in Discord to take any action listed under each pillar.

### Evening Check-in (10:30 PM)

A lighter, forward-looking summary covering:

- **Task review** — what you completed today, what remains open, and anything now overdue. Prompts you to update your task list or mark things complete if needed.
- **Tomorrow preview** — a summary of tomorrow's calendar with any comments worth flagging (heavy day, early start, back-to-back blocks, deadlines within 48 hours). Prompts you to add any events or adjustments needed.
- **Urgent email recap** — anything flagged as urgent that arrived during the day that you haven't acted on yet.

The evening check-in is also interactive — you can reply to reschedule, add tasks, or ask follow-up questions.

---

## Pillars

### 1. Gmail — Email Highlights

Scans your inbox each morning and surfaces only what matters. The sender and keyword lists are configurable and can be expanded over time as needed.

**What counts as "important":**
- Emails from: @umich.edu, Canvas, Gradescope
- Emails containing keywords: "deadline", "interview", "offer", "urgent", "action required"

**What it tells you:**
- Sender, subject, and a one-line summary of each flagged email
- Whether any email requires a reply or action from you

**Urgent email alerts:**
- When the agent blocks study time on your calendar — whether during the morning briefing or triggered throughout the day — it simultaneously surfaces any urgent emails as an alert in Discord

**What it can do (on request):**
- Draft a reply for your review — no sending without explicit approval
- Archive or label emails
- Flag an email as a follow-up reminder in Google Tasks

---

### 2. Google Calendar — Daily Schedule Summary

Gives you a clear picture of what your day looks like before it starts.

**What it tells you:**
- All events for today, with times and locations
- Any conflicts or back-to-back blocks
- Prep reminders for events (e.g. "you have an interview at 2 PM — here's what to know")
- Any automatically blocked study time added since the last briefing, with an explanation of why

**Automatic triggers:**
- **30 minutes before any event** — sends a reminder to Discord
- **Conflict detection** — flags conflicts when an event is created, and again in the morning briefing
- **Heavy day alert** — if tomorrow has 3+ events or a major deadline, alerts you the evening before and again in the morning briefing
- **Exam/project deadline proximity** — flags when an exam or task with "project" or "exam" in the name is within 48 hours
- **Automatic study block** — when a project deadline or exam is approaching and dead time exists in your calendar (30+ minute gaps), the agent silently blocks study time and notifies you in the next briefing or alert

**What it can do (on request):**
- Reschedule or move events
- Block focus time in open slots
- Add prep time before important meetings
- No calendar deletions — edits only

---

### 3. Google Tasks — Task Triage

Surfaces what's due, what's overdue, and what to actually focus on — not just a flat list.

**What it tells you:**
- Any overdue tasks (always flagged as urgent)
- Tasks due today or within 3 days
- A suggested priority order based on deadlines and calendar load

**Prioritization logic:**
- Overdue → always surface first
- Due today with a packed calendar → flagged as "needs attention"
- Due this week with a light calendar → lower urgency
- Anything related to job search → always high priority
- Any task with "project" in the name → assumed high workload and high priority

**What it can do (on request):**
- Add new tasks ("add 'review leetcode' to my tasks due Friday")
- Mark tasks complete
- Break a large task into subtasks
- Adjust priority or due dates

---

### 4. News & Research Digest

Keeps you informed on topics relevant to your interests and career. Runs in the morning briefing only — not available on-demand, as stories would go stale throughout the day.

**Topics, in priority order:**
1. Machine learning / AI research
2. New startups and funding rounds in tech
3. University of Michigan / CSE department news
4. Data science tooling and new libraries — only included if fewer than 5 ML/startup stories surfaced that day

**Sources:**
- Hacker News — top stories, strong general CS signal
- arxiv (ML, CS, AI categories) — raw source for research papers
- TechCrunch — startup funding and launches
- The Batch (deeplearning.ai) — weekly ML digest
- Import AI (Jack Clark) — AI research and policy depth
- MIT Technology Review — longer-form trend analysis
- Hugging Face blog — new models, datasets, and tooling
- Michigan Daily / UMich CSE news — campus and department updates

**Format:** 3 bullet points max, each with a headline, one-line summary, and a link

---

## Interaction & On-Demand Use

The agent is available at any time throughout the day via Discord — not just during scheduled briefings. You can ask for a summary of any pillar, or request any action, at any point.

**Example on-demand commands:**
- "What's on my calendar tomorrow?"
- "Do I have anything due this week?"
- "Catch me up on anything urgent from today"
- "Reschedule my 3pm to tomorrow morning"
- "Draft a reply to [SENDER]'s email"
- "Add 'finish EECS 281 project' to tasks due Sunday"
- "Block some study time for my exam on Friday"

The agent always asks for confirmation before:
- Sending any email (drafts only without explicit approval)
- Significantly restructuring calendar events

---

## Out of Scope (v0.1)

- Multi-agent coordination
- Slack or other work integrations
- Automatic email sending without explicit confirmation
- Calendar event deletion
- Automatic task creation from emails without prompting
- Voice interaction
- On-demand news digest

---