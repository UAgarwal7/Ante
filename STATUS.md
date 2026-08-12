# Ante — Status

**Last updated:** 2026-08-12

Current engineering state. [docs/product-summary.md](docs/product-summary.md) is the original spec
(April 2026) and is aspirational in places — where the two disagree, this file is right.

> Account identifiers, channel IDs, and the Cloud project ID are deliberately **not** in this file.
> They live in `~/.openclaw/openclaw.json` and `~/.openclaw/google_credentials.json`, outside the repo.

---

## TL;DR

Google auth is **fixed and verified** — all three APIs respond. Scope policy is decided and
centralized. Nothing else has been touched yet: `gcalendar.py` and `gmail.py` are still on their
original per-file auth and still contain write functions that need removing.

**Next action:** the script cutover (see "Next steps" below). Everything else waits on it.

---

## Architecture (as it actually is)

| Thing | Reality |
|---|---|
| Config | `~/.openclaw/openclaw.json`. **`config/config.yaml` in this repo is empty (0 bytes)** and unused. |
| Brain / system prompt | `~/.openclaw/workspace/` — `BOOTSTRAP.md`, `SOUL.md`, `AGENTS.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`. **There is no `system.md`.** |
| Skills the agent loads | `~/.openclaw/workspace/skills/{gcalendar,gmail}/SKILL.md` — **untracked by this repo** |
| Skills in this repo | `skills/gcalendar.md` has content but is **dead** (nothing reads it). `skills/morning-briefing.md`, `skills/evening-checkin.md`, `skills/news-fetch.md` are all **0 bytes**. |
| Model | Claude Haiku 4.5 (`anthropic/claude-haiku-4-5-20251001`) |
| Delivery | Discord (app + channel IDs in local config, not here) |
| Google Cloud | Desktop OAuth client (project ID in local config, not here) |
| Google account | Personal Gmail — **not** the university account |

⚠️ **Two sources of truth for skills.** The repo copy and the workspace copy have already diverged
(the workspace calendar skill has a "Deleting events" section the repo copy lacks). Collapse these
into one during the cutover — generate or symlink the workspace skills from the repo.

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
| No task deletion | **Our code** — `tasks` permits it; `tasks.py` just won't expose it |

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

## Live data as of 2026-08-12

| Pillar | State |
|---|---|
| Calendar | **0 events** next 24h (4 calendars; university calendar shared in with `writer` access ✅) |
| Tasks | **0 open** in the default list (1 task list) |
| Gmail | 2 flagged /24h, 8 /7d, out of ~100 messages/7d |

⚠️ **Two of three pillars have no data to prove themselves with.** August, summer break — plausibly
correct, not evidence of breakage. But with zero rows you **cannot distinguish "working" from
"silently broken."** For the first real test run: widen Calendar to 7 days, list all task lists, and
add one throwaway task. If all three appear, assembly is genuinely proven.

Other measurements worth not re-deriving:
- **40% of mail (16/40 sampled) is HTML-only with no usable `text/plain`.** `get_email_body()` only
  reads `text/plain` and only scans top-level parts, so it returns `''` for all of them. Not
  currently biting because `get_flagged_emails()` uses `format='metadata'` + Gmail's server-side
  `snippet`, which works fine for HTML mail. It fails totally for image-only email (snippet is blank
  too) — that's where a vision path would come in, since Haiku 4.5 is multimodal.
- Gmail categories are a weak filter here — `-category:promotions -category:social` only removed 11
  of 100 messages.

---

## ⚠️ Live footgun — do not run these two scripts

`scripts/gmail.py` and `scripts/gcalendar.py` still carry their **own** `SCOPES` lists (gmail's
includes `gmail.modify`) and their own `InstalledAppFlow` fallback. If either runs against an expired
token, that fallback fires and **overwrites the good read-only token with a write-capable one**,
silently undoing the whole scope decision.

Until the cutover: don't run `run_gmail.sh` or `run_calendar.sh`. Use `run_auth_check.sh` for
testing — it goes through `ante_auth` and is safe.

---

## Next steps

1. **Script cutover** ← everything is blocked on this
   - Point `gcalendar.py` and `gmail.py` at `ante_auth`; delete their local `SCOPES` and browser-flow
     fallback (kills the footgun above)
   - Remove `delete_event` from `gcalendar.py`; keep `create_event`
   - Remove `archive_email` and `label_email` from `gmail.py`
   - Rework `is_important()` into an override rather than a gate (see decision above)
   - Add HTML fallback + recursive part-walking to `get_email_body()`
   - Collapse repo skills and workspace skills into one source of truth
2. **`scripts/tasks.py`** — mirrors `gmail.py`; read + add + complete, **no delete**
3. **Briefing assembler** — one message combining all three pillars
4. **Restart the gateway**, confirm Discord actually connects (see below), fire one briefing by hand
5. Later: university forwarding setup; news fetch; cron scheduling

---

## Known problems not yet fixed

- **Discord liveness unverified.** The `openclaw-gateway` process has been up since Aug 1, but its
  log dies mid-reconnect on **Aug 5 10:28** with `ENOTFOUND discord.com` — the machine was offline.
  Network is fine now (Discord API returns 200). It's been wedged ~6 days and needs a restart.
- **`~/.openclaw/openclaw.json` has a trailing comma** on line 9 — invalid strict JSON. OpenClaw
  parses it leniently; any tool that doesn't will hard-fail on the whole config.
- `get_events(days=1)` fetches a **rolling `now → now+24h`**, not "today" — at 9pm you get tomorrow
  morning.
- README and `docs/product-summary.md` still advertise email drafting and archive/label, which the
  read-only Gmail decision removes. README has been corrected; the product summary is kept as the
  original spec.
