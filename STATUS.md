# Ante — Status

**Last updated:** 2026-08-16

Current engineering state. [docs/product-summary.md](docs/product-summary.md) is the original spec
(April 2026) and is aspirational in places — where the two disagree, this file is right.

> Account identifiers, channel IDs, and the Cloud project ID are deliberately **not** in this file.
> They live in `~/.openclaw/openclaw.json` and `~/.openclaw/google_credentials.json`, outside the repo.

---

## TL;DR

**Ante works.** It answers questions in Discord and writes real data to Google — a natural-language
request created a correctly-dated task on 2026-08-13. Gateway, Discord, model auth, identity, skills
and all three Google pillars are live and verified.

What's missing is the *scheduled* half: nothing assembles a briefing, and nothing runs on a timer.

**Next action:** use it for a few days, then build the briefing assembler.

---

## Architecture (as it actually is)

| Thing | Reality |
|---|---|
| Config | `~/.openclaw/openclaw.json` (strict JSON since 2026-08-13). **`config/config.yaml` in this repo is empty (0 bytes)** and unused. |
| Brain / system prompt | `~/.openclaw/workspace/` — `BOOTSTRAP.md`, `SOUL.md`, `AGENTS.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, `HEARTBEAT.md`. **There is no `system.md`.** Snapshotted to `workspace/` (gitignored) by `scripts/backup_workspace.sh`. |
| Skills the agent loads | `~/.openclaw/workspace/skills/{gcalendar,gmail,tasks}` are **copies** of `skills/*/SKILL.md`, written by `scripts/sync_skills.sh`. ⚠️ **Never symlink** — OpenClaw refuses symlinks that escape the skills root (`reason=symlink-escape`) and the agent silently loads *no* skills. Re-run the sync after editing, then restart the gateway. |
| Skills in this repo | `skills/{gcalendar,gmail,tasks}/SKILL.md` are live. `skills/morning-briefing.md`, `skills/evening-checkin.md`, `skills/news-fetch.md` are TODO placeholders. |
| Model | Claude Haiku 4.5 (`anthropic/claude-haiku-4-5-20251001`) |
| Delivery | Discord, `#general` guild channel. Owner's sender id is allowlisted in `channels.discord.guilds."*".users`. |
| Gateway | launchd `ai.openclaw.gateway`, loopback port 18789, Control UI at `http://127.0.0.1:18789/` |
| OpenClaw version | `2026.4.12` — **`2026.7.1-2` is available** |
| Google account | Personal Gmail — **not** the university account |

---

## Decisions made (and why)

### Scope policy — read-only except where deliberately not

Defined once in [scripts/ante_auth.py](scripts/ante_auth.py) as `SERVICE_SCOPES`; `SCOPES` is derived
as the union so the three scripts can't drift.

| Service | Access | Scope |
|---|---|---|
| Calendar | read/write events | `calendar.events` |
| Calendar | read-only | `calendar.calendarlist.readonly` |
| Gmail | **read-only** | `gmail.readonly` |
| Tasks | read/write | `tasks` |

- `calendar.calendarlist.readonly` is **required, not optional** — `calendarList.list()` is not
  authorized by `calendar.events`, and without it `get_events()` can't discover the shared
  university calendar at all.
- Chose narrow calendar scopes over full `calendar`: no ACL changes, no calendar create/delete, no
  settings access.
- Tasks has **no granular scopes** — `tasks` is the only write option and it also permits deletion.

### Gmail stays read-only — there is no draft-without-send scope

Investigated adding draft creation. **`gmail.drafts.create` is not a real scope** (verified against
Google's live Gmail discovery doc — it's the *method* ID, not a scope). Every scope that authorizes
`drafts.create` — `gmail.compose`, `gmail.modify`, `mail.google.com` — **also authorizes
`messages.send`**. Google does not sell the draft half separately.

Decision: stay `gmail.readonly`. Ante writes reply text into Discord; you copy it into Gmail
yourself. Reasoning: Ante reads attacker-controllable content (any email anyone sends you) and is an
LLM with shell access. Read-only, the worst case of a malicious email is a bad summary. With
`gmail.compose`, the worst case is mail leaving the account under your name.

### Where each guardrail lives

| Guarantee | Enforced by |
|---|---|
| No email send / draft / archive / label | **Google** — the token cannot do it |
| No calendar deletion | **Our code** — `calendar.events` permits `events.delete`; only removing `delete_event` stops it |
| No task deletion | **Our code** — `tasks` permits it; `tasks.py` has no delete function ✅ |

The two code-level ones are exactly what the cutover has to deliver.

### University email — forward with source-side filtering, no auto-delete

University mail is **not currently reaching** the personal account. Forwarding is not restricted by
the university; the objection was inbox mess and storage.

Plan:
1. University side → forward to the personal account, with a filter so only LMS / grading /
   faculty / keyword mail leaves
2. ⚠️ Set the copy behavior to **"keep the copy in the Inbox"** — the dropdown also offers
   *delete the copy*, which would destroy the originals as they forward
3. Personal side → filter on the incoming address: **Skip Inbox**, apply a label, never mark important

**No auto-deletion.** Measured: current inbox growth is ~0.44 GB/year; filtered forwarding adds
roughly **40 MB/year**, ~0.3% of the free 15 GB. A scheduled destructive job over the mailbox isn't
worth 40 MB — a typo'd label in a `GmailApp.search()` silently widens the match. Revisit in six
months.

Rejected alternatives: Apps Script → shared Sheet (zero footprint but **irreversibly lossy** — an
image-only email becomes sender + subject + nothing, and a Drive-OCR bolt-on makes it more complex
than forwarding while still lossy); POP fetch (same storage as forwarding, solves nothing); dedicated
sink account (extra account + token to maintain).

#### Strict maybe: AgentMail as the forwarding sink

**Not decided. Revisit when step 5 (forwarding) actually happens — do not adopt before then.**

[AgentMail](https://www.agentmail.to/) is an API-first email provider that **provisions new
agent-owned inboxes**. It cannot connect to an existing Gmail account, so it is **not** a replacement
for the Gmail read path — that stays Google OAuth + `gmail.readonly` regardless.

What it *would* replace is the forwarding sink above. Forward university mail into an AgentMail inbox
instead of into personal Gmail, and the original objection (inbox mess + storage) goes to literally
zero: no filter, no `UMich` label, no Skip-Inbox rule, no 40 MB/year. It also ships an MCP server, so
it could attach to OpenClaw as a tool instead of another Python script to maintain.

Cost is not the blocker: free tier is 3 inboxes / 3,000 emails per month / 100 per day, no card.
Filtered university mail is well inside that. Realistic spend is **$0**; paid starts at $20/mo.

Why it stays a maybe:
- **Dependency risk.** It's a Series-A startup (~$6M, Mar 2026). A Gmail label is durable in a way
  someone's free tier is not. If it folds or repositions, the forwarding target evaporates.
- **It reopens the send question.** An agent-owned address defuses the *identity* half of the
  read-only Gmail decision — mail leaves as `ante@…`, not under your name. It does **not** defuse
  prompt injection: Ante would read attacker-controllable mail and hold a send button. Smaller blast
  radius, not zero. If adopted, keep send disabled by default.
- **Wrong time.** It solves none of the current blockers (cutover, Tasks, assembler, cron, gateway).
  Adding a third-party dependency before the thing assembles one briefing is backwards.

Decide it head-to-head against "Gmail filter + label" at step 5, not before.

### Keyword filter becomes a hint, not a gate

`is_important()` currently gates what Ante sees. Measured over 7 days: **8 of 100 messages passed**,
and the discards included multiple genuine recruiting emails — real signal, dropped because they
contained no listed keyword. Meanwhile an unrelated marketing email *did* pass, on a coincidental
substring match. The list is both too narrow and too loose.

Cost of not filtering, at Haiku 4.5's $1.00/MTok input: all mail metadata is ~990 tokens/day →
**$0.36/year** vs $0.03 filtered. 0.5% of Haiku's 200K context. Not a constraint.

The real cost is **latency**: [scripts/gmail.py](scripts/gmail.py) does one serial `messages.get` per
message, so 100 messages ≈ 15s per briefing. Fix with Gmail's batch endpoint, not by dropping mail.

New design:
1. Fetch everything from the last 24h (~14 messages)
2. Let Haiku judge what's briefing-worthy
3. Keep `IMPORTANT_SENDERS` / `IMPORTANT_KEYWORDS` as an **always-surface override**, so the
   university domain and words like "deadline" can never be judged away

Tradeoff accepted: Ante then reads every email including attacker-controlled ones. Gmail is read-only
so nothing can be sent, but Calendar has write access — a malicious email could in principle induce a
calendar event. Low stakes, noted deliberately.

---
---

## What works today (verified)

| Piece | Evidence |
|---|---|
| Google auth | `run_auth_check.sh` passes; 4 scopes, all three APIs respond |
| Calendar read | 4 calendars queried, 0 failures; real event found on the shared university calendar |
| Calendar write | `create_event` + `update_event`; reschedule preserves duration; all-day guard fires |
| Gmail read | 16–19 messages scanned per 24h, 0 failures; body extraction 40/40 (72% plain, 27% HTML fallback) |
| Tasks read/write | add → complete → reopen → complete; overdue canary; date validation rejects `'next tuesday'` |
| Gateway | running, RPC probe ok |
| Discord | `running, connected, bot:@Ante` |
| Identity | owner's sender id allowlisted; Ante acts for him in `#general`, refuses for others |
| Skills | 3/3 `✓ ready` from `openclaw-workspace` |
| End to end | *"make a task tomorrow to do my Codesignal Assessment"* → `'Do my Code Signal assessment' due=2026-08-14` |

**Cost, measured.** On Haiku a full Discord exchange is **~2.7¢** (4 API calls, ~0.7¢ each). The same
question on Sonnet 4.6 was **9.3¢**. `openclaw configure` silently switched the model to Sonnet while
setting a credential — check `agents.defaults.model.primary` after any interactive setup.

Cost is dominated by a **~10K-token system prompt** re-sent on every call (55 registered skills, of
which 13 are ready and 3 are ours, plus workspace files and tool definitions). Output is ~3% of spend.
Trimming unused bundled skills is the next real lever.

---

## Open problems

**Blocked / needs a decision**

- **The CLI is paired `operator.read` only.** Every `cron.*` and `gateway call` RPC fails with
  `pairing required` — a scope error wearing a pairing message. Approve the upgrade in the Control UI
  (`http://127.0.0.1:18789/`); the pending request expires quickly, so open the UI *before*
  triggering it. This blocks OpenClaw-native scheduling.
- **OpenClaw is 3 months behind.** Upgrade separately from other changes, and expect the LaunchAgent
  to need reinstalling (the plist hardcodes version and node paths). ⚠️ `reset_session.py` writes
  OpenClaw's private state — re-verify it after any upgrade.

**Not built**

- Briefing assembler, news fetch, cron scheduling, university forwarding
- Conflict detection, study blocking, prep time
- Vision path for image-only email (no text in parts, blank snippet)

**Known constraints, handled but worth remembering**

- **Heartbeat is disabled (`0m`)**, so a cron job with `--session main` would be scheduled and never
  fire — those run "on the next heartbeat". Use `--session isolated`.
- **Exec preflight refuses chained interpreter invocations** (`cd … && source venv/bin/activate &&
  python3 …`). The wrappers exist for this reason. Skill write commands still use inline `python -c`;
  task creation worked on 2026-08-13, but confirm that's the intended route rather than luck.
- **Google Tasks due dates are date-only** — the time is silently discarded. Timed reminders are
  calendar events. Watch that Ante *says* so rather than silently dropping the hour.
- **Calendar event descriptions are untrusted input** — anyone who can send an invite controls text
  that reaches the model. Capped at 500 chars; the skill says not to follow instructions in them.
  That's a prompt-level mitigation, not a boundary.
- **For the assembler:** calendars carry their own timezones (`Family` is UTC). Render everything
  through `ante_auth.local_timezone()`, never raw offsets.
- **No Gmail batching** — one serial `messages.get` per message. Fine at ~16/day; fix with the batch
  endpoint before widening the window.
- `docs/product-summary.md` still describes email drafting and archive/label. Kept deliberately as
  the original spec, with a banner explaining the divergence.

---

## Resolved (do not re-investigate)

| Was | Outcome |
|---|---|
| OAuth dead 4 months (`invalid_grant`) | Consent screen was in Testing mode (7-day refresh expiry). Now Production. |
| Browser-consent fallback could re-grant write scopes | Removed; all auth via `ante_auth`, which never opens a browser |
| Scope lists duplicated across scripts | Centralised in `ante_auth.SERVICE_SCOPES` |
| `delete_event` / `archive_email` / `label_email` | Removed |
| Keyword filter dropped 92% of mail | Inverted to an always-surface floor |
| `get_email_body()` returned `''` | Recursive MIME walk + HTML fallback; 0/40 empty |
| Timezone hardcoded to Detroit, calendars are Pacific | Resolved at runtime from the primary calendar, 1h TTL cache |
| Symlinked skills loaded nothing | Copies via `sync_skills.sh` |
| Workspace docs advertised removed capabilities | `BOOTSTRAP`/`TOOLS`/`USER`/`AGENTS` corrected 2026-08-13 |
| Discord channel stopped, bot offline | Gateway restart; now `running, connected` |
| "Anthropic credential dead" (HTTP 401) | Red herring — the *usage/billing* endpoint needs an admin key. Inference was fine. |
| Ante refused to act in `#general` | Correct behaviour; allowlist was empty. Owner's sender id now allowlisted. |
| `openclaw.json` trailing comma | Now strict JSON |
| Workspace brain files had no backup | `scripts/backup_workspace.sh` → `workspace/` (gitignored) |
| `/new` can't be scripted | It's a chat-surface intercept. `reset_session.py` reproduces it on disk. |

Full root-cause history for all of these is in `DEVLOG.md` (private, gitignored) — 31 entries.

---

## Next steps

1. **Use it for a few days.** Four things are unbuilt; observation beats guessing at which you want.
2. **Confirm the nightly reset fired** — installed 2026-08-17 at 04:00 local. Check
   `~/.openclaw/logs/session-reset.log` after the first night; a `skip … already fresh` line is a
   pass, not a failure.
3. **Briefing assembler** — combine the three pillars; surface `report.failures` rather than
   rendering a broken pillar as "nothing today"
4. **Approve the CLI scope**, if you want OpenClaw-native cron
5. Later: news fetch, university forwarding, the upgrade
