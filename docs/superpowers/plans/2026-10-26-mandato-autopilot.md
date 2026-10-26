# Mandato Autopilot Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development. The human approved design and immediate execution; no additional plan approval is required.

**Goal:** Единое рабочее окно бухгалтера с агентом по правилам, согласованием руководителя, OCR, голосом и новой подачей продукта.

**Architecture:** Additive tenant-scoped modules integrate with the existing exact-money ledger and LangGraph. Provider calls remain server-side. UI presents cases grouped by counterparty/contract and keeps detailed tools accessible in context.

**Tech Stack:** Python/FastAPI, SQLite/PostgreSQL, LangGraph, Yandex APIs, React/TypeScript, CSS motion, pytest/Playwright.

## 1. Workflow backend and permissions
Files: server/workflow.py, tests/test_workflow.py; root wires main.py/database.py/storage_pg.py.
- [x] Write failing API tests for grouping, missing-contract identity, pause/payment-derived stages, manager/accountant permissions, policy versioning, invitations, contact-wide cooldown, stale/duplicate sends and inbox exceptions.
- [x] Run `.venv/bin/python -m pytest tests/test_workflow.py -q`; confirm missing routes fail before implementing.
- [x] Implement additive schema, role dependency, case endpoints, approved-policy automatic reminders, durable delivery claims, scheduled worker, authenticated inbound integration with idempotency. Money updates reuse finance functions.
- [x] Verify focused tests, including policy revoke before execution, and existing API/finance suites.

## 2. Yandex document and voice services
Files: server/yandex_services.py, tests/test_yandex_services.py, web/src/components/YandexDesk.tsx, web/src/components/yandex.css.
- [x] First test unsupported files, wrong tenant, quota, duplicate request, provider auth failure, STT/TTS bounds and read-only conversation.
- [x] Implement Vision OCR adapter and confirmed extraction view; SpeechKit PCM recording/transcription, audible reply and bounded session, actual provider availability status.
- [x] Run focused API tests and TypeScript. Record source documentation and actual live verification separately; never call mock tests live verification.

## 3. Brand and product landing
Files: web/src/components/Brand.tsx, Landing.tsx, landing.css; public SVG mark/logo/favicon; web/index.html.
- [x] Replace monogram with original ouroboros vector and update product proposition, CTA and coherent animated workflow. Preserve substantive pricing/FAQ and accessibility.
- [x] Verify mobile layout, keyboard, reduced motion, and lack of invented customer outcomes in browser.

## 4. Unified workspace and onboarding
Files: web/src/components/Workspace.tsx, WorkflowDesk.tsx, WorkflowOnboarding.tsx, workflow.css, web/src/api.ts; e2e/workflow.spec.ts.
- [x] Add failing browser test: optional first-run tour, skip/replay, compact navigation, case grouping, open invoice tools inside case, role-based approvals and error retry.
- [x] Implement desktop board/table, mobile stacked case cards, detail drawer with chronology and contextual tools, three operational summary queues and policy/team settings.
- [x] Provide help replay; tour state persisted per user. No synthetic ledger entries. Keep old workflows reachable through contextual tools and compact tools menu.
- [x] Run Playwright new scenarios and existing full suite, update selectors only for intentional navigation changes.

## 5. Integration access and operational release
Files: ConnectionsDesk.tsx, docs/integrations.md, infra/yandex, scripts/deploy_yandex_vm.sh, compose.production.yml, .env.example.
- [x] Surface credential and scope prerequisites, distinguish configured/verified/unavailable. Add judicial/executive source connection needs without fake credentials or undocumented scraping.
- [x] Run all pytest with disposable PostgreSQL, replay evals, TypeScript, formatting/build, Playwright desktop/mobile, audits and Docker build.
- [x] Review full diff for financial safety, permissions and provider secret leakage; repair failures.
- [ ] Commit/push, verify CI, fresh backup, manual exact-SHA deploy; verify HTTPS routes, authentication, new features and unchanged financial fingerprint. Retain rollback path and private backup.
