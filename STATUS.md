# Ante — Status

**Last updated:** 2026-08-12

Current engineering state. [docs/product-summary.md](docs/product-summary.md) is the original spec
(April 2026) and is aspirational in places — where the two disagree, this file is right.

> Account identifiers, channel IDs, and the Cloud project ID are deliberately **not** in this file.
> They live in `~/.openclaw/openclaw.json` and `~/.openclaw/google_credentials.json`, outside the repo.

---

## TL;DR

Google auth is **fixed and verified**, and the **script cutover is done** (2026-08-12). Both
`gcalendar.py` and `gmail.py` now go through `ante_auth`, the browser-consent footgun is gone, write
functions that contradicted the scope policy are removed, the keyword filter is inverted from a gate
to a floor, and skills have one source of truth. Calendar and Gmail both run clean and return real
data.

`scripts/tasks.py` is now built and verified too — **all three pillars run clean and return real
data**, each with a `report` and a non-zero exit on partial failure.

The two write functions the spec promised but never had — `update_event` (reschedule) and
`update_task` (change a due date) — are now built and verified. **Google functionality is complete**
as scoped.

**Next action:** the briefing assembler, then OpenClaw wiring.

---

## Architecture (as it actually is)

| Thing | Reality |
|---|---|
| Config | `~/.openclaw/openclaw.json`. **`config/config.yaml` in this repo is empty (0 bytes)** and unused. |
| Brain / system prompt | `~/.openclaw/workspace/` — `BOOTSTRAP.md`, `SOUL.md`, `AGENTS.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`. **There is no `system.md`.** |
| Skills the agent loads | `~/.openclaw/workspace/skills/{gcalendar,gmail,tasks}` are **copies** of `skills/*/SKILL.md`, written by `scripts/sync_skills.sh`. ⚠️ **Do not symlink** — OpenClaw refuses symlinks that escape the skills root (`reason=symlink-escape`) and the agent then loads *no* skills, with only a stderr warning. Re-run the sync after editing skills, then restart the gateway. Editing the tracked file changes agent behavior directly; they can no longer diverge. Pre-cutover copies backed up at `~/.openclaw/workspace/skills.backup-2026-08-12`. |
| Skills in this repo | `skills/gcalendar/SKILL.md`, `skills/gmail/SKILL.md` and `skills/tasks/SKILL.md` are live. `skills/morning-briefing.md`, `skills/evening-checkin.md`, `skills/news-fetch.md` are TODO placeholders (they were 0 bytes, which read as "done"). |
| Model | Claude Haiku 4.5 (`anthropic/claude-haiku-4-5-20251001`) |
| Delivery | Discord (app + channel IDs in local config, not here) |
| Google Cloud | Desktop OAuth client (project ID in local config, not here) |
| Google account | Personal Gmail — **not** the university account |

✅ **Skill divergence is resolved.** Before the cutover the workspace copy documented `delete_event`,
`archive_email` and `label_email` — all of which are now gone from the code. The symlink means that
class of drift can't recur.

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

## What's done and verified

`./scripts/run_auth_check.sh` passes — all four scopes granted, all three APIs responding
(calendar: 4 calendars, gmail: profile OK, tasks: 1 task list).

**New files:**

- [scripts/ante_auth.py](scripts/ante_auth.py) — single source of truth for scopes + shared auth.
  `load_credentials()` deliberately **never opens a browser**; it refreshes or raises `AuthError`, so
  a scheduled briefing fails loudly instead of hanging on an invisible consent screen.
- [scripts/auth_setup.py](scripts/auth_setup.py) — interactive consent flow; backs up the old token,
  diffs granted vs requested afterward.
- [scripts/auth_check.py](scripts/auth_check.py) — prints token scopes, then makes one real read-only
  call per API (a correctly-scoped token still fails if an API was never enabled).
- `scripts/run_auth_setup.sh`, `scripts/run_auth_check.sh` — venv wrappers.

**Google Cloud console:** OAuth consent screen set to **Production**. This is what prevents the
7-day refresh-token expiry that killed the previous token (`invalid_grant`, dead since ~2026-04-15).
If auth dies again, check publishing status before anything else — `ante_auth.py`'s error message
says so explicitly.

---

## Live data as of 2026-08-12 (post-cutover)

| Pillar | State |
|---|---|
| Calendar | ✅ **Proven working.** 4 calendars found, 4 queried, 0 failures. 0 events in the next 24h but **1 event within 7 days** — on the shared university calendar, which confirms the share works end to end. 1 cross-calendar duplicate collapsed. |
| Gmail | ✅ **Proven working.** 16 messages scanned in 24h, 0 failures, not truncated. 1 matched `always_surface`. |
| Tasks | ✅ **Proven working.** 1 list found, 1 queried, 0 failures. Read, add, complete, reopen, overdue detection and due-date validation all exercised against live data. |

**Every pillar now has a non-empty fixture, which is what makes these greens meaningful.** Calendar
was widened to 7 days (at 24h it returned `[]`, which proved nothing); Tasks got a real task plus two
throwaway canaries. Nothing here is a pass-on-empty result any more.

The Tasks write path was verified end to end: add with a due date → complete → reopen → complete, plus
an overdue canary dated 11 days ago to confirm `overdue` computes correctly and clears on completion,
plus a rejected `due='next tuesday'` to confirm date validation. **Two completed canary tasks are
left in `My Tasks`** — Ante deliberately cannot delete them; remove them in the Google Tasks UI if
they bother you.

Note the Gmail numbers: **16 messages scanned, 1 flagged.** Under the old gate, the briefing would
have seen exactly 1 message and the other 15 would never have reached the model. That is the change
in concrete terms.

Other measurements worth not re-deriving:
- **Body extraction now succeeds on 40/40 sampled messages (0% empty).** Breakdown: 72% resolved from
  `text/plain`, 27% via the new HTML fallback.
- ⚠️ **Correction to an earlier figure.** This file previously claimed "40% of mail (16/40) is
  HTML-only with no usable `text/plain`." **That does not reproduce.** Measured directly by running
  the old extraction logic against a fresh 40-message sample: it returned empty for **2 of 40 (5%)**,
  not 16. The fix is still worth having — 5% → 0% — but the problem was roughly eight times smaller
  than recorded. The original number was almost certainly counting messages that *contain* an HTML
  part rather than messages that *lack usable plain text*. The methodology wasn't written down, so it
  couldn't be checked; record methodology with any measurement kept for later.
- Image-only email remains unsolved: no text in the parts and a blank `snippet`, so there is nothing
  to extract. `get_email_body()` reports `source: 'none'` for these. The real fix is a vision path,
  since Haiku 4.5 is multimodal. Not built.
- Gmail categories are a weak filter here — `-category:promotions -category:social` only removed 11
  of 100 messages.

---

## ✅ Cutover complete — the footgun is gone (2026-08-12)

Both scripts previously carried their own `SCOPES` (gmail's included `gmail.modify`) and their own
`InstalledAppFlow` fallback, which would have overwritten the read-only token with a write-capable one
on any refresh failure. Both now go through `ante_auth.load_credentials()`, which never opens a
browser. **`run_gmail.sh` and `run_calendar.sh` are safe to run.** Verified: token scopes unchanged
after running both.

What changed:

| Change | Where |
|---|---|
| Auth via `ante_auth`, no browser fallback | both scripts |
| `delete_event` removed | `gcalendar.py` |
| `archive_email`, `label_email` removed | `gmail.py` |
| `is_important()` → `always_surface()`, a floor not a gate | `gmail.py` |
| `get_email_body()` recursive MIME walk + HTML fallback | `gmail.py` |
| `mode='calendar'` vs `'rolling'` window | `gcalendar.py` |
| Descriptions capped at 500 chars | `gcalendar.py` |
| Cross-calendar duplicate events collapsed | `gcalendar.py` |
| Both scripts return a `report` alongside data | both |
| Skills symlinked from repo → workspace | `skills/` |

**The `report` object is the important structural change.** Every pillar now returns provenance
(`calendars_queried`, `scanned`, `failures`, `truncated`) next to its data, because an empty result
was previously ambiguous between "nothing to report" and "silently broken" — the single most
recurring failure shape in this project. The scripts also exit non-zero on partial failure.

---

## Next steps

1. **Briefing assembler** — one message combining all three pillars. Each pillar returns
   `(data, report)`; the assembler must surface `failures` rather than rendering a broken pillar as
   "nothing today", which is the whole point of the report objects.
2. **Restart the gateway**, confirm Discord actually connects (see below), fire one briefing by hand
3. Later: university forwarding setup; news fetch; cron scheduling

---

## Known problems not yet fixed

- 🔴 **The Discord channel is stopped, and the bot is offline.** Confirmed via
  `openclaw channels status`: `enabled, configured, stopped, disconnected, error: channel stop timed
  out after 5000ms` — residue from the failed Aug 5 reconnect. The gateway *process* is alive and
  port 18789 listens, which is why it looked healthy.
  ⚠️ **`openclaw health` is not sufficient to check this.** It reports `Discord: ok` because it can
  reach Discord's REST API; presence needs the gateway websocket, which is down. Use
  `openclaw channels status` — it's the only one that reports the channel's real state.
  Fix: `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`. Not `openclaw gateway`, which
  refuses while the LaunchAgent owns the process.
- 🔴 **The Anthropic credential is dead** — `Claude: HTTP 401: Invalid bearer token`. The configured
  model is `anthropic/claude-haiku-4-5-20251001`, so **Ante cannot answer anything** until this is
  re-authorized, even once Discord reconnects. Fix with `openclaw configure`. The `openai-codex`
  profile is healthy, so it's specifically Anthropic that expired.
- **The running gateway predates today's skill rewrite** (up since Aug 1). If it caches skills at
  startup it's still using the old ones referencing `delete_event`/`archive_email`. The restart is
  what loads the new skills.
- **`~/.openclaw/openclaw.json` has a trailing comma** on line 9 — invalid strict JSON. OpenClaw
  parses it leniently; any tool that doesn't will hard-fail on the whole config.
- ⚠️ **The timezone was hardcoded to `America/Detroit` while every calendar on the account is
  `America/Los_Angeles`.** Every event Ante created would have landed **3 hours off**, with a
  confirmation that read as correct. Now resolved at runtime from the primary calendar
  (`ante_auth.local_timezone()`), falling back to the system timezone. Verified: asking for 15:00 now
  stores 15:00−08:00 and displays as 15:00. Cached with a 1-hour TTL so a long-running OpenClaw
  process can't pin a stale zone after a relocation; DST needs no refresh since a `ZoneInfo` is a
  zone, not an offset.
- **For the assembler:** calendars can each carry their own timezone (`Family` is UTC here), and
  `get_events()` returns each event's raw offset. The assembler must render everything in
  `ante_auth.local_timezone()` rather than printing raw strings, or a UTC-calendar event will be
  displayed hours off.
- **Google Tasks due dates are date-only.** The API accepts RFC3339 but silently discards the time,
  so a task cannot be due at 3pm. `add_task()` takes `YYYY-MM-DD` and rejects anything else; the
  skill file tells the agent not to claim it set a time. Timed reminders are calendar events.
- **No Gmail batching.** `get_recent_emails()` still does one serial `messages.get` per message.
  Fine at current volume (16 messages ≈ 2s), but it scales linearly and the batch endpoint is the
  fix if a wider window is ever used.
- **Image-only email produces no text at all** — `get_email_body()` returns `source: 'none'`. Needs
  the vision path.
- **Calendar event descriptions are untrusted input.** Anyone who can send an invite controls text
  that reaches the model. Capped at 500 chars and the skill file says not to follow instructions in
  them, but that's a prompt-level mitigation, not a hard boundary.
- `docs/product-summary.md` still describes email drafting and archive/label. Kept deliberately as
  the original spec, with a banner explaining the divergence; README is corrected.

**Workspace brain files are now backed up.** `~/.openclaw/workspace/*.md` — `SOUL.md`, `AGENTS.md`,
`BOOTSTRAP.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, `HEARTBEAT.md` — held Ante's personality and
user context and existed in **exactly one place**, deleted by `openclaw reset`. Unlike the scripts
they can't be re-derived from anything. `scripts/backup_workspace.sh` snapshots them to `workspace/`
(gitignored — they can carry personal detail and this repo is public). Re-run it whenever they
change; the manifest stamps its own date so a stale snapshot is visible. Survives a reset, **not** a
lost disk.

**Fixed since last update:** the browser-consent footgun, scope duplication, `delete_event`,
`archive_email`/`label_email`, the keyword gate, `get_email_body()`, skill divergence, the
rolling-vs-calendar window, and the 0-byte skill placeholders.
