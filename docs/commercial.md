# Commercial access and private operator queue

The commercial API stores demo/custom requests, one 14-day trial per organization,
simulated monthly orders, cancellations and deletion-request tickets. It does not
charge money, send email, issue fiscal receipts, delete organizational data or
record subscription orders in the customer's receivables ledger.

`server/plan_catalog.json` is the shared frontend/backend source. Prices are
integer **kopeks**, currency `RUB`: Старт 990,000 (9,900 ₽), Команда 1,990,000
(19,900 ₽), Масштаб 3,990,000 (39,900 ₽). Custom conditions require a request,
not an order. Monthly active-invoice/user limits are 100/2, 500/5 and 2,000/15.
The catalog limits are recorded in entitlement snapshots; this release does not
enforce product quotas or restrict existing receivables access.

## Registration acceptance

Both registration screens submit `terms_accepted: true` and `terms_version: "2026-11-04"` as a pair. The server records the version, timestamp, user and tenant in `registration_acceptances` in the same transaction as identity/session creation. It rejects false/coerced values, unpaired fields and unknown versions. Legacy API clients without these fields remain compatible without inventing a consent record. The table has no mutation endpoint.

## API contract

All mutation bodies are strict JSON: unknown fields are rejected. Authenticated
mutations require the existing session cookie, current `X-CSRF-Token` and manager
role. Reads are tenant-scoped. Origin checks apply when `APP_URL` is configured.

| Method and path | Body | Result |
| --- | --- | --- |
| `GET /api/commercial/plans` | — | `{trial_days:14,payment_mode:"invoice",items:[...]}` |
| `POST /api/commercial/requests` | `{kind:"demo"\|"custom",name,email,company?:"",note?:"",consent:true}` | `201 {id,kind,status:"requested",created_at}`; no contact information is echoed |
| `GET /api/commercial/account` | — | Current plan snapshot, trial/subscription state, orders and deletion ticket |
| `POST /api/commercial/trial` | `{}` | Account with 14-day Команда trial; `409` if previously used or a plan was connected |
| `POST /api/commercial/orders` | `{plan_id:"start"\|"team"\|"scale",consent:true,idempotency_key}` | `201` order with server-selected amount and `pending` state |
| `POST /api/commercial/orders/{id}/confirm` | `{}` | `{order,account}`; only simulated confirmation, no actual payment |
| `POST /api/commercial/orders/{id}/cancel` | `{}` | Cancel a pending order; confirmed orders require account cancellation |
| `POST /api/commercial/cancel` | `{consent:true}` | End current trial/simulated subscription and cancel pending orders; preserve records |
| `POST /api/commercial/deletion-request` | `{confirmation:"УДАЛИТЬ",consent:true}` | `201 {id,status:"requested",created_at}`; idempotent tenant ticket |

`idempotency_key` is an 8–100 character opaque checkout key using letters,
digits, `_`, `.`, `:` or `-`. The same tenant/key/plan returns the original order,
including its original price. Reusing a key for a different plan returns `409`.
A canceled order stays canceled; create a fresh checkout key to order again.
Confirmation retries return the existing order and current account without
extending access or undoing cancellation. Confirming one pending order cancels
other pending orders in that tenant. Foreign-tenant order IDs return `404`.

Account `status` is `none`, `trial`, `trial_expired`, `active`,
`expired` or `canceled`. Trial timestamps are UTC; duration is exactly
14 days. Simulated subscription duration is one calendar month, clamped at month
end. `auto_renew` is always `false`. Expiry is calculated when reading the account;
there is no charge or automatic renewal job. `plan` is a stored snapshot, not an
assurance that payment took place. Order states are `pending`,
`confirmed` and `canceled`; **there is no `paid` state**.

Public requests have a separate process-local limit of 15/minute/IP; other API
limits still apply. A proxy must provide distributed limits for multiple workers.
Application responses omit tokens, contact details and internal operator notes.

## Daily request handling over SSH

The web application must have started once with this version so its additive
schema initializer creates the handling table. Use an authorized operator's SSH
session on the application host/container, in the application directory, with
the same protected environment as the running service. The script selects
`DATABASE_URL` when configured, otherwise `DATABASE_PATH`. It does not load `.env`
files, initialize schemas or create a missing SQLite database. Do not put a
database URL/password into shell arguments, chat or documentation.

List the oldest pending requests without contact information:

```sh
python -m scripts.commercial_requests list
python -m scripts.commercial_requests list --kind demo --limit 50
python -m scripts.commercial_requests list --kind custom
python -m scripts.commercial_requests list --kind deletion
```

Each item has its full UUID, kind, creation time and handling state. `has_more`
indicates additional rows. Limits are 1–500. Complete the oldest batch, then list
pending again. To view private contact information for manual follow-up:

```sh
python -m scripts.commercial_requests list --kind demo --include-contact
python -m scripts.commercial_requests list --kind deletion --include-contact
```

`--include-contact` reveals name, email, company, submitted note and tenant ID
(when applicable). For deletion requests, the contact is the user who submitted
the ticket in that tenant. Output is ASCII JSON so submitted terminal control
characters cannot execute or hide terminal text. Treat decoded values as
untrusted customer input. Do not paste the output into public logs, shared
terminals or external tickets. If an authorized private export is needed, create
it with restrictive file permissions (`umask 077`); remove it after use under
the organization's retention process. The CLI provides no download/public API.

Review the request, arrange follow-up manually through the organization's
approved channel, and record the resulting private internal ticket reference:

```sh
python -m scripts.commercial_requests mark-handled \
  --kind demo \
  --request 01234567-89ab-4cde-8012-3456789abcde \
  --owner operator-1 \
  --reference CRM-143
python -m scripts.commercial_requests list --state handled
python -m scripts.commercial_requests list --state all --kind deletion
```

Use the actual full request UUID. `--owner` identifies the responsible operator;
`--reference` identifies an existing disposition/follow-up ticket. Do not include
passwords, tokens or message bodies. The command verifies the exact kind and ID,
then records the disposition transactionally. Identical retries preserve the
original timestamp. Different owner/reference values cannot overwrite that
record. SSH/database permissions control operator access; `--owner` is an audit
label, not an application authentication mechanism.

Assign an operator to review this queue at a defined cadence before relying on
the public promise of manual follow-up. There is no email or queue notification
worker in this release. Demo/custom acceptance means the request was stored;
the manual follow-up is the operator's responsibility.

For deletion, `handled` means a disposition or private case reference was
recorded. It does **not** mean data was deleted, authority verified or retention
requirements resolved. Check authority and scope through the approved manual
process, document the outcome in the private case, and perform any separately
authorized deletion through a reviewed procedure. Neither the CLI nor the
deletion endpoint performs destructive operations. Public request/ticket status
remains `requested`; internal handling lives separately and is never exposed by
the public API.

## Payment adapter and requirements before real billing

`server/commercial.py` contains `PaymentAdapter` and the only registered
implementation, `SandboxPaymentAdapter`. `COMMERCIAL_PAYMENT_MODE` defaults to
`sandbox`; any other value makes order creation/confirmation fail with `503`.
Changing an environment variable cannot enable real payments. The sandbox
reference is `sandbox:{order_id}`, an internal simulation marker with no bank or
receipt meaning. Existing historical simulation records must retain that meaning.

Connecting a merchant requires a separate implementation and release:

1. Select the merchant/provider and settle actual seller identity, currency,
   contractual terms, customer support and refund process. Confirm actual
   account access and current provider requirements with the merchant operator.
2. Implement server-created checkout sessions from the stored immutable order
   amount/currency, with provider idempotency and tenant ownership. Supply keys
   through protected server configuration, never through the browser or catalog.
3. Add a dedicated provider webhook route. Authenticate signatures, validate
   timestamp/replay rules, verify final provider payment state and independently
   compare merchant account, order identity, amount and currency. A browser
   redirect, client assertion or sandbox-confirm call must never prove payment.
4. Store unique provider event/payment IDs and perform state transitions,
   reconciliation and entitlement grants transactionally. Cover duplicate,
   delayed, out-of-order, forged and cross-tenant events. Define pending, failed,
   real-payment, cancellation, refund and chargeback handling separately from
   simulation states. Do not reinterpret `confirmed` as a real payment.
5. Implement and verify provider checkout failure recovery, reconciliation,
   settlement reporting, customer cancellation/refund paths and audit records.
   Address receipt/fiscalization integration applicable to the actual merchant;
   this release has no receipt implementation or legal determination of those
   obligations. Subscription payments must remain separate from client debt
   payments and the receivables ledger.
6. If recurring charges are desired, implement a separate explicit opt-in,
   mandate/token lifecycle, renewal schedule, notices and revocation. Existing
   trials and simulated grants have no recurring mandate and cannot be charged.
7. Test the real adapter against the provider's documented test environment,
   validate the production merchant setup, review public terms and disclosures,
   then obtain the deployment operator's approval for real billing activation.

No provider credentials or external network calls are needed for the current
commercial flow. The CLI never sends email or invokes a payment provider.

## Verification

```sh
python -m pytest -q tests/test_commercial.py tests/test_commercial_operator.py
TEST_POSTGRES_URL=postgresql://127.0.0.1/test_db \
  python -m pytest -q tests/test_commercial_postgres.py
```

Use an isolated local test database for PostgreSQL checks; the fixture creates
and removes its own schema. Do not point tests at the production database.
