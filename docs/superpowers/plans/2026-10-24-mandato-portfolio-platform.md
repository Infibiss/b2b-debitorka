# Mandato portfolio platform implementation plan

> **For agentic workers:** Apply superpowers:subagent-driven-development or superpowers:executing-plans task by task; independent file ownership is declared below. The user explicitly requested planning followed immediately by implementation, tests and updating the existing server, without an additional plan approval stop.

**Goal:** Ship a unified evidence-based receivables audit, usable external-system adapters, bounded negotiation and cash forecasting, with Mandato branding, preserving existing customers and financial history.

**Architecture:** Keep FastAPI/PostgreSQL and React. Add tenant-scoped modules through the existing `initialize_schema(connection)` and `create_router(ctx)` extension points. Imported source facts do not become confirmed ledger payments or legally established invoices without preview and approval. Outbound negotiation requires explicit account policy and current mandate; court filing and concessions exceeding policy require human review. Unknown or unavailable registry data are never reported as a clean check. Bank embedding is a read-only, scoped and revocable partner interface, not an assertion of a bank partnership.

**Tech Stack:** Existing Python/FastAPI/psycopg/LangGraph/Yandex, TypeScript/React, native SVG, pytest/Playwright. CPU-first baseline forecasting; no synthetic-data-trained model presented as production ML.

## Evidence and boundaries

- Existing acceptance and evidence: `docs/report-mvp-acceptance.md`, `docs/release-verification.md`, `docs/research/2026-10-24-product-review.md`.
- Source financial scenarios: accounting 62 balances vs documents; partial and combined payments; unidentified cash; returns/offsets; missing primary documents; delivery/payment-term ambiguity; disputed/VIP debtors; expiring limitation period requiring legal confirmation; incoming payment after an approved action; stale/unavailable registry lookup.
- Obtain official API documentation for each adapter before implementation. No arbitrary network URLs, scraping around CAPTCHA, or fabricated provider responses in production. Test fixtures are labelled in tests only. Credentials and external sandboxes are requested asynchronously; unavailable live verification must remain explicit in release evidence.
- Do not change SSH ingress, budget, service credentials, Docker project/volume names, or session cookie while renaming the customer-facing product.

## 1. Shared integration points — owner root

- [x] Register `portfolio`, `integrations`, `forecasting`, `negotiation`, `partner` modules in `server/main.py`, `server/database.py`, `server/storage_pg.py` using existing hooks; additive tables only.
- [x] Add tenant-isolation tests for every new route and compatibility tests for existing SQLite/PostgreSQL data.
- [x] Preserve exact money units, idempotency, financial snapshot checks, CSRF and source approval.

## 2. Unified portfolio audit — owner root

Files: new `server/portfolio.py`, `tests/test_portfolio.py`, `web/src/components/PortfolioDesk.tsx`, `web/src/components/portfolio.css`, `e2e/portfolio.spec.ts`; modify `Workspace.tsx`.

- [x] Define tests first for empty/partial portfolios, OSV discrepancy without invented invoice, missing contract/performance/due basis, disputed/held/paid debt, broken promise, unmatched bank cash, stale document and missing registry facts.
- [x] Persist immutable audit runs with as-of time, input snapshot, invoice/counterparty findings, severity, evidence and suggested next step. Refresh creates a new run; historical run cannot silently change.
- [x] Include current ledger plus approved accounting reconciliation, legal evidence, promises and registry checks. Store an explicitly provisional review date for limitation risk; never automatically assert legal limitation expiry from invoice issue date.
- [x] Produce actionable groups: reconcile money, obtain documents, check debtor, contact, lawyer review, wait for confirmed promise, stop. No uncalibrated probability or guaranteed recovery.
- [x] Provide portfolio intake by reusing current invoice import and OSV mapping, audit refresh/history, search/severity filter, readable detail, CSV export with spreadsheet-injection protection, and links to existing workspaces.
- [x] Test desktop/mobile flow, real server calculations, stale refresh and cross-tenant access.

## 3. External systems — isolated connector owner

Files owned: `server/integrations.py`, `server/integration_providers.py`, `server/bank_exchange.py`, `tests/test_integrations.py`, `tests/test_bank_exchange.py`, `docs/integrations.md`. Do not modify shared app/storage/UI files.

- [x] Research official read contracts for 1C standard OData, Diadoc, a documented bank statement API and debtor registry provider. Record exact URLs and what credentials are necessary.
- [x] Implement fixed-endpoint, bounded timeout/size, no-redirect adapters; on-premise 1C requires operator-configured destination and credential binding, never a customer-supplied arbitrary URL.
- [x] Add 1C client-bank exchange import with encoding/date/money checks, account direction, idempotent source reference, incoming-only preview and approval into existing bank source tables. Never automatically distribute ambiguous payments.
- [x] External reads produce staged normalized source items with provenance and explicit mapping/approval; statuses distinguish unconfigured, unavailable, no match, completed and stale. No automatic invoice creation from aggregate balance.
- [x] Registry lookup validates exact INN, timestamps and status, and exposes coverage limits; unavailable bankruptcy/court/FSSP sources remain unverified.
- [x] EDI retrieves available documents/metadata, does not send or sign external documents without explicit user action. Tests cover provider failures, token redaction, tenant binding, duplicates and mismatched party identity.

## 4. Forecast and negotiation — isolated intelligence owner

Files owned: `server/forecasting.py`, `server/negotiation.py`, `tests/test_forecasting.py`, `tests/test_negotiation.py`, `docs/intelligence.md`. Do not modify shared app/storage/UI files.

- [x] Define a cash forecast contract (7/30/60-day cumulative expected receipts, bounds/scenarios, coverage, method, as-of, source evidence) and meaningful tests before implementation. Use actual historical dated bank allocations; exclude manual opening paid and future knowledge. Abstain on insufficient history; distinguish scenario from learned prediction.
- [x] Implement CPU empirical baseline using historical delay, amount-weighted partial receipts, comparable cohorts and uncertainty only when supported. Do not train on synthetic client data or download a generic model with no target correspondence.
- [x] Implement versioned tenant negotiation policy, explicit enablement, immutable proposal/review/execute events, current snapshot/hold/mandate checks. Handle payment promise, installment request, discount request, dispute, payment claim and document request. Policy can allow internal acceptance within configured bounds; beyond-bound, ambiguous or stale proposals require handoff. No LLM arithmetic, unapproved debt write-off, automatic external sending or court action.
- [x] Tests for no-policy default, revoked mandate, simultaneous payment, repeated execution, partial promise vs full debt, refused/expired offer, future history exclusion and tenant boundaries.

## 5. Mandato identity — isolated design owner

Files owned: `Brand.tsx`, `Landing.tsx`, `Auth.tsx`, `landing.css`, SVG/public brand assets, `web/index.html`, `web/public/site.webmanifest` if present. Do not modify Workspace.tsx, global styles shared by new screens, dependency lockfiles or infrastructure names.

- [x] Create a restrained geometric native SVG mark and `mandato` wordmark; readable in small favicon and monochrome, no imitation certification or registered trademark claim.
- [x] Replace customer-facing Mandato branding and metadata in owned files, preserve product visual system and responsive motion.
- [x] Keep only implemented functionality and qualified claims on marketing site; do not invent customers, metrics or completed banking connections.
- [x] Inspect browser rendering desktop/mobile, keyboard and reduced-motion behavior; provide standalone SVG and favicon.

## 6. Bank embedding and UI integration — owner root

Files: `server/partner.py`, `tests/test_partner.py`, new UI components for connections/intelligence, shared hooks above.

- [x] Add explicit tenant-owned partner grants, short-lived scoped tokens stored hashed, revoke and audit. Public registration never inherits access. Read-only summary/export with minimal data, no banking secrets or automatic credit decision.
- [x] No public iframe with a static token. Provide a documented authenticated partner API suitable for a bank-hosted client with a documented bearer request contract; actual bank SSO/contract requires partner onboarding. A standalone bank-hosted client is deferred until partner requirements exist.
- [x] Surface external-system connection health, registry refresh and staged data approval; expose forecast method/coverage and negotiation limits in plain Russian.

## 7. Release

- [x] Review all changes for financial correctness, provider coverage, auth and misleading success states; fix findings.
- [x] Run targeted tests, full Python suite with actual disposable PostgreSQL, TypeScript/build/format, desktop/mobile Playwright, dependency audits and production Docker build.
- [x] Record actual checks and remaining external prerequisites; update current acceptance, do not overwrite historical evidence.
- [x] Commit/push and wait for exact-SHA CI; manually deploy through existing pinned SSH helper after private backup. Preserve production .env and all persistent volumes.
- [x] Verify public HTTPS, Mandato assets, existing account/data continuity and new API/audit workflow. Copy a fresh approved private backup to Mac. Do not claim a live external connection or trained model without actual evidence.
