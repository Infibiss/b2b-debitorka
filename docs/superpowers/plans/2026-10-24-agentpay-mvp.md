# AgentPay MVP Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent tasks. Root owns integration, UI and final checks.

**Goal:** Deliver a working receivables product and polished Russian product website, ready for a real hosting deployment.

**Architecture:** React/TypeScript client and FastAPI API in a single Docker service. Persist tenant-isolated data in SQLite on a mounted disk. Send approved correspondence through optional SMTP; optional domestic LLM with deterministic fallback.

**Tech Stack:** React, Vite, TypeScript, lucide-react; Python, FastAPI, SQLite, Argon2, pytest, Playwright; GitHub Actions, Docker, Render.

## 1. Evidence and scope
- [x] Read all 25 pages of supplied report; inspect repository.
- [x] Research competition, data/ML, design from primary sources; write docs/research/*.md with caveats and source URLs.
- [x] Write product design; choose narrow actionable receivables flow and fail-closed external actions.

## 2. API and persistence (server/, tests/)
- [x] Start with failing pytest acceptance tests for auth, CSV import, payments, isolation and approval.
- [x] Build DB schema and tenant-scoped repository, auth/CSRF middleware, typed API.
- [x] Implement integer-money aging and priorities; immutable payment/audit events; transactional idempotent CSV import.
- [x] Implement drafts/edit/approve/send lifecycle, SMTP configuration check, safe LLM fallback.
- [x] Run `python3 -m pytest -q`: no failures. Review API contract against frontend.

## 3. Marketing site (web/src/components/Landing.tsx, landing.css)
- [x] Build original visual identity, responsive header/hero, scenario motion, editable cost calculator, pricing/FAQ and signup.
- [x] Use truthful product copy, real capabilities and no fabricated testimonials.
- [x] Verify keyboard access, reduced motion and mobile layout in browser.

## 4. Product UI (web/src/components/Workspace.tsx, app.css)
- [x] Auth forms with friendly validation and server sessions.
- [x] Overview, searchable/filterable debt table, invoice card, create/import, CSV export.
- [x] Draft/edit/approval, promise, partial/full payments, pause/dispute, event history, settings.
- [x] Cover loading, errors, empty states, save feedback and mobile navigation.
- [x] Run `npm run check` and `npm run build` successfully.

## 5. Delivery and operations (Dockerfile, render.yaml, .github/workflows/, docs/)
- [x] Pin dependencies; non-root container; health check; persistence, backups and restore.
- [x] Add GitHub Actions Python, TS/build and Playwright checks; gated optional deployment hook.
- [x] Document local run, SMTP/LLM, first customer setup, production config, transfer to RU hosting and limitations.

## 6. Independent review and end-to-end QA
- [x] Independent security/spec code review; resolve material findings.
- [x] Run production site locally; browser inspect desktop/mobile screenshots and all core actions.
- [x] Run full pytest/typecheck/build/e2e; inspect outputs and fix failures.
- [x] Check git diff for secrets and unintended files. Record exact verification evidence.
- [ ] Publish through the authenticated Render account; confirm cost/persistence, actual deploy status and live URL.
