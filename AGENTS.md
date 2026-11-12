# Working with the owner

Mandato is the product: a B2B service for Russian small and medium businesses that automates debt recovery from the first reminder through court and bailiffs. This repository is the product itself. Notes that carry the work between sessions live in `agent/status/` (not tracked by git):

- `STATE.md` — the current plan as a checklist.
- `DECISIONS.md` — what the owner has decided.
- `HANDOFF.md` — a note to the next session.

Templates are in `agent/templates/`. If `agent/status/` doesn't exist yet, create it from them.

The owner writes in Russian or English; answer in the language of their last message.

## Starting a session

Read `agent/status/` (if present) and briefly say where things stand. If `STATE.md` is empty or every item is done, offer to draft a new plan with the owner before starting work.

Don't read the whole product up front. Start from what the owner or the handoff points to, and check which branch is current. Delegate broad searches to subagents.

## Defaults worth keeping

- **Check, don't recall.** When something can be verified in files or code, look before answering. Treat older notes and other agents' conclusions as hints.
- **Owner decides forks.** For product or architecture choices, do the legwork, then bring options with a recommendation, numbered so the owner can reply "1 A, 2 ok". Small technical calls are yours.
- **Log decisions as they happen** in `DECISIONS.md`, in the owner's words. Mark your own suggestions as proposals until confirmed.
- **Plain language.** Avoid internal shorthand; when you reference a file, section or code, add a few words on what it is.
- **Be clear about what you actually did:** read in full vs. skimmed, tested vs. not, pushed vs. local.
- **Keep scope as agreed.** If you think it should grow or shrink, ask. Prefer a general rule over special-case patches.
- **Look at the screen, not only the tests.** For any visual change, take screenshots at several widths (390, 768, 1024, 1440) and look at them before calling it done.

## Keeping notes current

Tick items in `STATE.md` as you go. Before `/compact`, `/clear`, or when the owner says "save" («сохрани»), update `STATE.md` and `HANDOFF.md`. If the context is getting large or you notice you're losing track, suggest a handoff and a fresh session.

## Subagents

Give them a self-contained brief: they don't see this conversation. Keep each one's job small enough to fit comfortably in context. Avoid destructive commands (`rm`, `kill`, `git clean`) in background agents, and have them save results as they go. For important results, a fresh agent that didn't do the work makes a good reviewer — for example, one playing a small-business client reading the site.

## Project facts

- **Stack:** FastAPI (`server/`), React 19 + TypeScript + Vite (`web/`), SQLite locally and PostgreSQL in production (`server/storage_pg.py`). Money is stored in integer kopeks.
- **Text:** Russian is the source language. Every UI string goes through `t('…')`; English lives in `web/src/i18n/en.json`.
- **Public pages** are prerendered for search engines by `scripts/prerender.mjs` (part of `npm run build`); `server/main.py` serves `web/dist/_pages/<route>/index.html`.
- **Checks before a push:** `python -m pytest -q`, `npx tsc --noEmit`, `npm run build`, `npx playwright test` (on Windows set `E2E_CHANNEL=msedge` and `E2E_PYTHON` to the venv Python), `npx prettier --check web/src e2e`. New database code also runs against PostgreSQL (Docker, `DATABASE_URL`).
- **Deploy:** push to `main` → GitHub CI (`.github/workflows/ci.yml`) → the server pulls the exact `main` commit every 5 minutes once CI is green. Check the live site after it lands.
- **Server names:** paths, Docker project, database and system user on the server are still called `agentpay`; renaming them needs SSH access and a migration with a backup.
- **Windows git:** four infra scripts show mode-only changes; use `git -c core.fileMode=false …` and leave them unstaged.

## Git and secrets

Commit and push when the owner asks. Say where the result lives (branch, commit, live or not). Secrets belong in `.env` or `/etc/agentpay/production.env` on the server, never in chat or in git.
