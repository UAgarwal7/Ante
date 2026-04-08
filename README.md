# Ante 🦞

A personal AI daily briefing agent built on [OpenClaw](https://openclaw.ai). Ante runs on my own machine, connects to my Google Workspace and curated news sources, and delivers a concise morning briefing and evening check-in to Discord every day — then stays available for on-demand tasks throughout the day.

---

## What it does

Every morning at 10:30 AM, Ante pulls from four sources and sends a single, actionable summary to Discord:

- **Gmail** — flags important emails from professors, recruiters, and key senders, and surfaces anything with urgent keywords
- **Google Calendar** — summarizes the day's events, flags conflicts, and automatically blocks study time when deadlines are approaching
- **Google Tasks** — triages overdue and upcoming tasks by priority, factoring in calendar load and deadline type
- **News digest** — 3 bullets covering ML/AI research, tech startups, and UMich CS news from sources like Hacker News, arxiv, TechCrunch, and The Batch

At 10:30 PM, a lighter evening check-in reviews what got done, previews tomorrow, and recaps any urgent emails from the day.

Beyond the scheduled briefings, Ante is available on-demand in Discord at any time — ask it what's due, have it draft an email, reschedule an event, or add a task.

---

## Why I built this

I was spending too much time each morning context-switching between Gmail, Google Calendar, Google Tasks, and various news sources just to figure out what my day looked like. Ante replaces that with one message I can actually respond to.

---

## Built with

- [OpenClaw](https://openclaw.ai) — agent framework and runtime
- [Discord](https://discord.com) — delivery channel and interaction interface
- Google Workspace APIs — Gmail, Google Calendar, Google Tasks
- Claude (Haiku 4.5) — LLM backend for reasoning and summarization
- Hacker News, arxiv, TechCrunch, The Batch, Import AI, MIT Technology Review, Hugging Face blog, Michigan Daily — news sources

---

## Project status

🚧 **In active development** — built over one week as a first OpenClaw project.

- [x] Phase 1 — OpenClaw installed and connected to Discord
- [ ] Phase 2 — Google Calendar integration
- [ ] Phase 3 — Gmail and Google Tasks integration
- [ ] Phase 4 — Morning briefing cron and news digest
- [ ] Phase 5 — Evening check-in, smart triggers, study block logic

---

## Docs

- [Product spec](docs/product_summary.md) — full breakdown of what Ante does and why

---

## Setup

Setup guide coming once the project is stable. Built for personal use — currently configured for my own Google account and Discord server.

---

## Notes

This is a personal project and a learning exercise. API keys and OAuth tokens are not committed to this repo. See `.gitignore`.