# Mandato workflow

The workflow is additive: it does not replace invoice balances, manual payments,
bank allocations, promises, legal documents or existing sessions. Amounts remain
integer kopeks. A zero balance is labelled as obligations closed in the financial
register; it is not proof that the bank received money.

## Cases and authority

`GET /api/workflow/cases` returns `{items, summary}`. Explicit contracts group
invoices for the same counterparty. An invoice without a verified contract has a
separate `invoice:<id>` case; no contract is invented from the company name.
`POST /api/workflow/contracts` accepts
`{counterparty_id, number, invoice_ids}` and returns the contract and `case_id`.
Grouping invoices resets the merged case's automation authority; start it again
after review. Existing invoices are not rewritten.

Case detail is `GET /api/workflow/cases/<id>` with `invoices`, `events`,
`financial_events`, `messages`, `documents`, `exceptions` and urgent unresolved
`deadlines`. A legal review due within 14 days remains in the decision queue even
when the financial balance is zero. Status is derived from the ledger, disputes,
pauses, promises, unresolved issues and delivery history.

Organization creators and migrated existing users have explicit manager
memberships. Missing membership fails closed to accountant. The manager changes
versioned policy and issues invitations. Invitations contain random one-use
secrets; only their SHA-256 hash is stored. They expire after three days and
create an accountant account in the fixed tenant with an Argon2 password hash.
Existing accounts cannot silently move organizations. Acceptance returns
`login_required: true`; the new accountant then signs in normally.

Ordinary issue resolution is available to accountants and managers, with an
audit reason. Discounts, installments and legal escalation require manager
approval through the existing specialized tools. Resolving a workflow issue
never modifies money or concludes a legal action.

## Approved policy and worker

`GET|PUT /api/workflow/policy` uses optimistic `expected_version`. Policy includes
`enabled`, `cooldown_days`, `weekdays` (Monday=0), `start_hour`, `end_hour`,
`auto_record_promises` and `auto_record_disputes`. Contact hours use `APP_TIMEZONE`
(default Europe/Moscow). Enabling requires the fixed server SMTP connector bound
to this tenant by `SMTP_TENANT_ID`. No client supplies SMTP hosts or credentials.

An accountant can `POST /api/workflow/cases/<id>/start`, `/pause` or `/resume`
with `{reason?}`. Policy approval and a reviewed case authorize ordinary template
reminders without reviewing every message. Sending is limited to overdue cases.
A current future promise suppresses reminders for the whole case, including a
partial promise; a missed promise becomes an explicit follow-up. Hold, dispute,
expired mandate, missing contact, multiple recipients within one contract,
unresolved exceptions and urgent legal deadlines stop dispatch.

`python -m scripts.workflow_worker --once` executes one cycle. Without `--once` it
runs each minute. The API's lifecycle runs the same scheduler when
`WORKFLOW_WORKER_ENABLED=true` (production default true, development default
false). Multiple instances share durable unique jobs and recipient claims.

A prepared reminder stores policy version, exact financial snapshot, sender
settings and connector identity. The worker rechecks these facts immediately
before dispatch. A committed claim precedes SMTP. The final recheck and SMTP
exchange hold the existing financial write lock, so payment, pause or policy
revocation cannot commit between the check and dispatch. This bounded exchange
can briefly block other financial writes.

Cooldown uses the longer workflow/legacy setting and covers the entire
counterparty and recipient address, including legacy sent messages. SMTP failure
or process interruption after claiming is never automatically retried. An
operator must investigate mail logs and resolve the visible delivery issue.
Resolution is audited, preserves the failed/unknown outcome and starts a new
cooldown. A future eligible job has a new identity; the uncertain job is never
reused. SMTP acknowledgement is evidence of server acceptance, not inbox reading.

## Protected incoming correspondence

Configure all three server variables: `WORKFLOW_INBOUND_TOKEN`,
`WORKFLOW_INBOUND_TENANT_ID`, and `WORKFLOW_INBOUND_SOURCE`.
`POST /api/workflow/inbound` requires `Authorization: Bearer <token>` and
`{invoice_id, source, source_id, sender, text, received_at?}`. The fixed source, fixed tenant,
existing tenant-owned invoice and its verified contact email must all match.
The trusted connector is responsible for authenticating mailbox authorship
before forwarding; comparing a sender field alone is not email authentication.
The endpoint must never be connected to an unverified public email forwarder.

Source IDs are idempotent; reuse with different contents returns 409. New
correspondence is retained and immediately creates an operational issue, so a
crash during extraction remains visible and duplicates do not repeat billed
provider work. No worker retries incoming extraction automatically.

With an enabled case policy, configured/allowed Yandex provider and quotas, the
existing persistent LangGraph extracts and deterministically validates evidence.
Unambiguous promises and disputes may execute under the explicit
`workflow-policy:<version>` actor; the graph rechecks current policy, case state,
financial snapshot, expiry and counterparty mandate in the execution transaction.
A promise requires the existing explicit counterparty promise mandate. It never
creates money or changes contractual terms. Payment claims, ambiguity, missing
mandates, missing provider access and provider failures remain operational
exceptions for the accountant. Paid provider credentials stay server-side.

Trusted receipt time is stored separately from ingestion/audit time. Optional
`received_at` must include a timezone and cannot be in the future. Relative dates
such as «завтра» without a trusted source timestamp become an operational issue;
ingestion time never silently moves an old promise into the future.

## Verification scope

`tests/test_workflow.py` exercises tenant isolation, unknown/explicit contracts,
policy/version/role boundaries, invitation hashing/reuse/expiry, snapshot
invalidation, revocation, claims under concurrent workers, counterparty/recipient
cooldown, legacy uncertainty, calendar eligibility, verified graph processing,
operational resolution, deadlines and unchanged balances. SMTP and extraction
providers are replaced in these tests; passing them is not live provider or
email delivery verification. Real PostgreSQL coverage requires
`TEST_POSTGRES_URL` and the existing isolated-schema test fixture.

## Direct private mailbox connection

The scheduler can poll a dedicated authenticated IMAP SSL mailbox before
considering outbound reminders. Configure `IMAP_HOST`, `IMAP_USER`,
`IMAP_PASSWORD`, `IMAP_TENANT_ID` and `IMAP_AUTH_SERV_ID`; optional settings are
`IMAP_PORT` (993) and `IMAP_FOLDER` (INBOX). Host and credentials are operator
configuration, never browser inputs. Use a dedicated mailbox, because accepted
Mandato replies are marked read only after source and outcome are persisted.

The collector follows a durable UID range, including messages already marked
read by the accountant, and processes at most 20 messages per cycle, oldest first.
An outstanding backlog pauses reminders until later cycles finish draining it.
The server's trusted IMAP `INTERNALDATE` supplies receipt time, independently of
the untrusted email `Date` header. The collector uses a 10-second network timeout
and checks the 64 KiB message limit before
fetching a body. It requires an exact `In-Reply-To` matching a Message-ID stored
with a durable workflow delivery claim. Subject matching and guessed invoice
numbers do not establish attribution. The current registered sender must match
the original recipient, and the trusted receiving MTA must provide a single
passing, domain-aligned DMARC `Authentication-Results` under the configured
`IMAP_AUTH_SERV_ID`. The MTA must strip forged headers claiming its own identity.
Without that receiving-server guarantee the connector must remain disabled.

UID receipts are durable. Original-message digests prevent duplicate extraction
even after an IMAP UIDVALIDITY reset. Unmatched replies, unsupported content,
oversized messages and unauthenticated authors are retained as synchronization
issues and never reach the agent. They remain unread in the mailbox. Interrupted
processing is not automatically retried, to avoid repeating paid extraction or
financial proposals. A configured unavailable/stale mailbox, an outstanding
backlog, or an unresolved
interrupted receipt, pauses ordinary reminders for its tenant.

An authenticated correlated reply whose text cannot be read creates a case
exception that stops reminders until an accountant reviews the original email.
For oversized messages only a bounded relevant header fragment is fetched for
correlation; the oversized body never reaches the agent. Unrelated spam is
retained as a mailbox issue without permanently blocking unrelated cases.

`GET /api/workflow/mailbox` returns connection status and bounded issue metadata.
`POST /api/workflow/mailbox/issues/<id>/resolve` accepts `{resolution}` from the
authenticated accountant or manager, records the investigation and acknowledges
the issue without replaying the original email or changing any balance.

A reply to a reminder covering several invoices does not identify which invoice
a promise should affect. Such promises become `invoice_scope_ambiguous`
exceptions without changing promises or balances. A grouped dispute pauses the
case and asks the accountant to clarify scope; individual invoice disputes are
not guessed. Active recorded judicial escalation also stops ordinary reminders
and remains visible through `legal_escalation` and `legal_stage`.
