# Mandato cash scenarios and bounded negotiation

All amounts are **integer kopeks**; discount bounds use integer basis points (100 bps = 1%). Routes require the existing authenticated tenant session. Writes require the existing CSRF header. Both modules use the normal SQLite/PostgreSQL connection and transaction contract and additive extension hooks.

## Cash forecast API and data contract

`GET /api/forecast` returns the current business date, UTC observation cutoff, `method=empirical_due_cohort_v1`, `status=available|abstained`, `unit=kopeks`, 7/30/60-day `horizons`, `coverage`, source `evidence`, and per-invoice coverage reasons. Each horizon contains `expected_amount`, `low_scenario`, and `high_scenario`. An abstention returns **null**, never a fabricated zero prediction. Amounts refer only to `coverage.covered_balance`; uncovered balances remain explicit. `as_of` may only equal the current business date. Historical inference is rejected with 422 because immutable historical invoice and counterparty snapshots are unavailable.

This is a transparent empirical cash scenario, **not a trained ML model, calibrated probability, collection score, or promise of recovery**. The minimum/maximum scenarios are observed cohort extrema, not statistical confidence intervals. No synthetic customer data, generic downloaded models, new ML libraries, random train/test split, or LLM arithmetic are used.

The entity is an invoice within its authenticated tenant. For each eligible current invoice:

1. Set its age relative to contractual due date, including negative ages for invoices not yet due.
2. Find historical invoices in the same tenant, issued before the corresponding age anchor, whose full anchor-to-60-day window has elapsed by the exact observation cutoff. A window ending later today is still censored and is excluded. Restrict due dates to the preceding 730 days. Include unpaid historical invoices, avoiding a paid-only survivor sample.
3. Require the invoice record to have been observed by that historical anchor. Backfilled old invoices observed today cannot pretend to have been known then. Current original amount/dates are usable only when there is no opening payment, manual payment, financial adjustment, or approved source revision that prevents reconstruction. Current disputed/held states never filter historical cohorts using a later outcome.
4. Reconstruct the outstanding amount at the historical anchor using only confirmed bank allocations and dated reversals whose effective dates and observation times were then available. Both bank-source and allocation observation times are checked. Label net receipts in `(anchor, anchor+horizon]`, using only facts observed by the current cutoff. Future effective or observation dates do not enter labels. Materialized `reversed_amount` is deliberately not used to rewrite past receipts using a later return.
5. Require at least five mature positive-exposure invoices and three confirmed bank allocations in that comparable cohort. These are conservative product coverage gates, not evidence of statistical calibration.
6. For each horizon, calculate each historical invoice's net receipt fraction, bounded to `[0,1]`. The amount-weighted cohort fraction multiplies the current eligible outstanding balance. Integer arithmetic rounds down to kopeks. Low/high scenarios use the minimum/maximum historical fraction.

Refunds reduce the cumulative **net** receipt label in the window of their effective date; net scenarios can decrease across horizons. Cash returned after a historical window never retroactively reduces that window's label. Opening paid amounts and manual payments are not bank evidence. Partially paid invoices contribute their actual receipt fractions, never an assumption of full payment. Predictions use same-age tenant cohorts rather than an invented counterparty risk score; industry/size matching and macroeconomic effects are not modelled.

Current held, disputed, paused, non-contactable, future/unobserved invoices and unreconstructible histories are excluded. A materialized current balance affected by a payment/return beyond the cutoff is also excluded, preventing future facts from entering indirectly through `paid_amount`. A young or sparse tenant usually receives an abstention. Source ID lists are tenant scoped and contain no bank credentials.

`coverage` includes `open_balance`, `eligible_balance`, `covered_balance`, `excluded_balance`, `uncovered_balance`, `training_invoices`, and observed `bank_allocations`. Evidence identifies cohort invoice IDs, allocation IDs, cutoff and gate settings. No forecast writes financial balances.

### Evaluation and operational limit

Decision owner: the tenant's finance operator; the result supports short-term cash planning. Unacceptable errors are invented bank cash, full-payment extrapolation from partial cash, cross-tenant evidence and future leakage. Capability/regression gates are executable tests for those cases, unpaid cohort members, returned funds, backfills, sparse history and temporal materialized-balance leakage. Fixture history is explicitly labelled as test data.

No live out-of-time accuracy/calibration claim has been measured. Before using these scenarios for financing, lending, or a trained-model promotion, retain immutable production prediction snapshots and delayed labels, perform rolling time-window evaluation on real tenant data, compare with zero-cash and simple cash-rate baselines, report amount MAE/bias and coverage by age/tenant/history depth, and review errors. No model is promoted by this change. Fallback is abstention; rollback removes the forecast extension without changing the ledger. A narrow historical sample or tenant-level pooling can remain biased even when all software correctness gates pass.

## Negotiation policy API

- `GET /api/negotiation/policy`: current version, or version 0 with `enabled=false`, `auto_accept=false`.
- `PUT /api/negotiation/policy`: full bounded policy plus `expected_version`. Concurrent/stale updates return 409. Each success appends a version; earlier policy rows remain unchanged.
- `GET /api/negotiation/policy/history`: tenant policy versions with actor and timestamp.

Policy fields: `enabled`, `auto_accept`, `allowed_kinds`, `max_promise_days` (1–365), `max_installments` (1–60), `max_discount_bps` (0–10000). Enabling the policy alone leaves automatic acceptance disabled. Existing counterparty contact/hold rules, explicit `agent_promises_allowed`, maximum promise days/installments, and mandate expiry further restrict the policy.

## Structured business proposals

`POST /api/negotiation/proposals` accepts:

```json
{
  "invoice_id": "tenant-invoice-id",
  "kind": "installment",
  "amount": 30000,
  "due_on": "2026-11-10",
  "installments": [
    {"date": "2026-11-03", "amount": 10000},
    {"date": "2026-11-10", "amount": 20000}
  ],
  "ambiguous": false,
  "confirmed_by_operator": true,
  "evidence": "Authenticated operator checked the proposed partial schedule against its source",
  "expires_on": "2026-11-01",
  "idempotency_key": "incoming-offer-unique-reference"
}
```

Dates in this example are illustrative and must be current when used. `kind` is one of `promise`, `installment`, `discount`, `document_request`, `dispute`, `payment_claim`. Promise/installment require an amount and complete due date; installment dates must be unique, positive amounts must sum exactly, and the last schedule date must equal `due_on`. Discount requires `discount_bps`.

`confirmed_by_operator` defaults to false. An authenticated operator must explicitly verify the structured terms; nonempty evidence and client-supplied `ambiguous=false` alone are insufficient. This confirms an operator review, **not independent authentication of a debtor or a binding signed agreement**. Incoming LLM extraction is untrusted. An extraction must still be reviewed by an operator before entering this bounded acceptance path. No route infers sender authenticity or negotiates over a live channel.

The response includes `id`, `invoice_id`, `kind`, `status`, immutable `terms`, `policy_version`, financial `snapshot_hash`, `reasons`, `outcome` and append-only `events`. Initial status is:

- `expired` when the offer has expired;
- `handoff` for disabled policy, unverified/ambiguous terms, missing mandate, holds, closed/disputed debt, disallowed kinds or outside-bound terms;
- `review_required` for valid terms with automatic acceptance disabled;
- `accepted` for operator-confirmed terms within explicitly enabled automatic-acceptance bounds.

`GET /api/negotiation/proposals` lists up to 200 recent tenant proposals; `GET /api/negotiation/proposals/{id}` includes durable events. Cross-tenant IDs return 404. Resubmitting identical terms and idempotency key returns the same proposal; changed terms with the same key return 409. Revisions are new proposals with new keys; accepted facts are not silently edited.

`POST /api/negotiation/proposals/{id}/review` takes `decision=approve|reject` and a reason. Approving a valid reviewable proposal records `accepted`; rejection records `rejected`. Handoff/expired/rejected/executed proposals cannot bypass the gate through approval. Correct terms or authority first, then submit a new proposal.

`POST /api/negotiation/proposals/{id}/execute` with `{}` performs only an **internal action** for an accepted proposal. Under the same database write transaction it reloads the latest tenant policy, financial snapshot, current business date, balance, counterparty hold/contact authorization and mandate. A payment, policy revision, revocation, stop-list change, expired schedule or offer causes 409 and a durable handoff/expiry event. Repeated execution of an already executed proposal returns its existing outcome without repeating the action, including after a later policy change.

### Internal outcomes and LangGraph boundary

The actual compiled LangGraph runs `current_authority → deterministic_bounds → business_decision` at proposal creation and again at review/execution. Authenticated business DB policy/proposal/event rows are the durable authority; the graph does not accept a resume payload as permission. The existing incoming-message extraction graph remains separate. This extension adds structured, reviewable business proposals; it does not claim autonomous debtor conversations or a newly connected outbound channel.

| Kind | Internal result | Financial effect |
| --- | --- | --- |
| promise / installment | Record the accepted partial promise/schedule through the existing finance service | `promised_amount` is separate from debt; no receipt or write-off; active older schedule is replaced using existing service semantics |
| discount | Record bounded concession terms for review | No adjustment/write-off; separate approval remains necessary |
| payment_claim | `verify_payment` work item/event | No confirmed bank cash or paid amount |
| document_request | `request_documents` work item/event | No external document request is sent |
| dispute | Record disputed status through the existing finance service | No amount change; subsequent contact/acceptance is blocked |

No email/SMS/call, external document signature, court filing, ledger concession or bank verification is performed. Events retain actor/time, policy version and snapshot evidence. Revoking policy/mandate prevents new execution; previously recorded outcomes remain auditable.

## Reproducible checks

```sh
.venv/bin/python -m pytest tests/test_forecasting.py tests/test_negotiation.py tests/test_agent_finance.py tests/test_finance.py -q
```

The new tests exercise actual authenticated HTTP routes, transactional SQLite ledger writes and compiled LangGraph checks without external provider calls. The host's full release suite must additionally verify PostgreSQL and UI integration; the targeted check does not assert those outcomes.
