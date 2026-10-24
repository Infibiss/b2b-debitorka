# Report MVP completion — implementation plan

> For agentic workers: execute in this session with independent module owners; review integration and tests before each release. The owner explicitly requested immediate implementation, without a planning approval stop.

**Goal:** Complete the software MVP on PDF pp.17–18 and the financial/mandate/negotiation controls needed to operate it; deploy a temporary Yandex VM after verification, within the approved 2,000 RUB/month ceiling.

**Architecture:** Keep the existing React/FastAPI product, add financial, legal and agent modules behind tenant-scoped API routers. Preserve SQLite for local work and support PostgreSQL for durable storage on the Yandex VM. Monetary and legal calculations stay deterministic. LangGraph persists the review/execution workflow; Langfuse records minimized observations and evals. Judicial submission, bank execution and legal representation are operator work in the report's first MVP and are represented by recorded cases/documents/statuses, not fictional automatic integrations.

**Stack:** Python/FastAPI, React/TypeScript, SQLite/PostgreSQL, LangGraph, Langfuse, YandexGPT, DOCX templates, pytest/Playwright, Docker/GitHub Actions/Yandex VM.

## 1. Financial contract and migration

Owner: financial worker; `server/database.py`, `server/main.py`, `server/models.py`, `server/csv_import.py`, new `server/finance*.py`, financial tests.

- [x] Define stable counterparties (INN where present, normalized identity otherwise), preserve legacy data and report conflicts; support equal company names with different INNs.
- [x] Import gross amount/paid/balance consistently; preview create/update/conflict; explicitly approve changes and invalidate stale actions.
- [x] Add bank payment identity and bounded allocations across invoices; idempotency and simultaneous allocation cannot exceed the source payment.
- [x] Add reasoned payment reversal, debt adjustments/returns/offsets, account-level holds/mandates, partial promises and installment schedule.
- [x] Test opening balances, repeated changed import, cross-tenant attempts, split payments, over-allocation, reversal/retry, stale draft/proposal, pause across all invoices, migration and rollbacks.

## 2. Legal calculations, documents and case operation

Owner: legal worker; new `server/legal*.py`, `tests/test_legal*.py`, `docs/research/legal-rules.md`.

- [x] Verify current primary legal sources: contractual penalty, Art.395 rate periods, arbitration court fees, court-order limits, pretrial period and procedural document contents.
- [x] Build Decimal/integer calculations with explicit dates, rate history, partial payments, transparent line items, caps and non-overlap rules.
- [x] Generate claim, court-order application and statement of claim DOCX from required factual fields; version, lawyer review, immutable approved snapshot and stale-finance checks.
- [x] Provide case stages/evidence/manual milestones and fee calculation on confirmed recovery; no fabricated court filing or delivery success.
- [x] Test thresholds, leap years/rate changes/payment boundaries, mutually exclusive sanctions, required fields, tenant access and DOCX contents.

## 3. LangGraph agent and Langfuse

Owner: agent worker; new `server/agent*.py`, agent tests/evals, observability configuration.

- [x] Implement Yandex structured extraction of intent, amount/date and exact evidence spans from submitted incoming correspondence.
- [x] Build actual StateGraph: ingest → extract → validate against ledger/mandate → propose → interrupt for review → idempotent execution → outcome.
- [x] Persist checkpoints and proposals in SQLite/PostgreSQL; restart/resume, reject, stale snapshot and duplicate execution gates.
- [x] A payment claim produces verification work, not a confirmed payment; no unapproved outbound communication, legal concession or balance mutation.
- [x] Integrate real Langfuse instrumentation with minimized metadata; configurable local/cloud host, actual trace delivery verification when configured; deterministic eval suite and optional real Yandex eval.
- [x] Test prompt injection, evidence mismatch, ambiguous date/amount, tenant mismatch, provider failure, resume after process recreation, approval expiry and execution idempotency.

## 4. Storage, UI and product integration

Owner: root; new PostgreSQL adapter and UI modules, shared API integration coordinated with financial owner.

- [x] Add tested PostgreSQL path with the same transaction/invariant contract; verify against a real temporary PostgreSQL container.
- [x] Add usable screens for reconciliations, bank allocations/corrections, counterparties/mandates, legal calculations/documents/cases, incoming-agent proposals and review.
- [x] Keep public product design coherent; describe actual released functionality without unsupported performance claims.
- [x] Add tenant export/backup and migration/restore instructions for the temporary hosting.

## 5. Verification and temporary Yandex deployment

- [x] Independent reviews against all report MVP rows and new financial/agent/legal invariants.
- [x] Full Python + PostgreSQL + browser workflows on desktop/mobile, real Yandex canary on synthetic input, document render/inspection, dependency audits and Docker build.
- [ ] Push tested code, wait for real GitHub Actions success.
- [ ] Deploy the approved 2 vCPU20% / 2GB / SSD30GB Yandex VM with private PostgreSQL and trusted HTTPS by IP; verify restart persistence and public workflow. SSH only from the operator IP, manual deploy, no GitHub SSH secrets; Langfuse stays off this VM.
- [ ] Connect permitted provider credentials without logging/exposing them. If an account permission/credential requires the owner, finish all unaffected work and request only the concrete final access step.
- [ ] Report the actual live URL, monthly cost and remaining operational requirements in chat/docs. Keep service UI focused on the user's work.

## Acceptance examples

1. A 1,000 RUB invoice with 400 already paid imports at 600 outstanding; a later approved snapshot of 500 paid shows 500 outstanding with traceable history.
2. One bank payment of 600 RUB can allocate 400+200 across two invoices; a simultaneous/duplicate third allocation cannot exceed 600.
3. A mistaken allocation can be reversed with a reason; history remains and obsolete approved documents/actions cannot execute.
4. A debtor-level contact hold blocks all its invoices and new correspondence. A 300 RUB promise does not label the entire balance promised.
5. The legal calculation splits rate/payment periods correctly and generates the selected document only with required facts; a reviewer approves the exact financial snapshot.
6. An incoming “we paid” creates a verification proposal; a promise can be reviewed and applied once after application restart. No external message is sent by inference alone.
7. Hosted restart retains tenants, invoices, allocations, documents and agent review state in PostgreSQL.

## Accepted changes during execution

The owner replaced free Render with Yandex VM, approved a 2,000 RUB/month ceiling excluding model requests, then explicitly chose SSH only from their IP and manual deploy. No CI private key is installed in GitHub. Langfuse is optional and verified locally; its full stack is excluded from the 2GB server. Current implementation/operational boundaries are recorded in `docs/report-mvp-acceptance.md`; release evidence is in `docs/release-verification.md`.
