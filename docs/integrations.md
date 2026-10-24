# Mandato: external source adapters

Implemented 24 October 2026. These adapters make real read requests when an
operator supplies credentials bound to the exact tenant. Contract tests use
explicit fixtures. Live 1C, Diadoc and production T-Bank verification has **not**
been performed: customer system versions, accounts and credentials are pending.
A real DaData exact public-INN lookup succeeded with the owner-supplied API key;
see [redacted evidence](evals/dadata-live.json). Only the owner tenant is bound.
The secret key and paid standardization API are not used.
An unconfigured connection is shown as unconfigured, never as connected.
The public T-Bank sandbox requires no customer account and is separately
available for a free format check; its actual network attempt is recorded below.

## Official contracts reviewed

| System | Official documentation | Implemented read | Credentials / prerequisites |
| --- | --- | --- | --- |
| 1C | [Standard REST interface, OData v3](https://v8.1c.ru/platforma/rest-interfeys/) | `GET <operator publication>/odata/standard.odata/<entity>?$format=json&$top=500&$select=...` | Published standard OData, dedicated read-only 1C user, operator destination and explicit configuration-specific field mapping. No universal invoice schema is assumed. |
| Diadoc | [GetDocuments V3](https://developer.kontur.ru/doc/diadoc-api/http/GetDocuments.html), [retrieval instructions](https://developer.kontur.ru/doc/diadoc-api/instructions/documents/getdocs.html) | Fixed `https://diadoc-api.kontur.ru/V3/GetDocuments`, `Any.Inbound`, newest first, maximum 100 metadata records | Tenant-authorized OAuth Bearer access token and exact organization box identifier. V3 remains documented; provider now recommends V4 for extended search. |
| DaData | [Organization by exact INN](https://dadata.ru/api/find-party/) | Fixed `POST https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party`, exact checksum-valid INN, `branch_type=MAIN` | Tenant-bound DaData API token, corresponding plan/quota. Only response fields supporting exact identity and registration status are retained. |
| T-Bank Business | [Account statement](https://developer.tbank.ru/docs/api/get-api-v-1-statement) | Fixed `GET https://business.tbank.ru/openapi/api/v1/statement`, `operationStatus=Transaction`, maximum 500 operations | Tenant-bound Bearer API token with account-statement scope and operator-bound 20-digit RUB account. Period is explicit and limited to 31 days, starting June 2023. |
| T-Bank public sandbox | [Sandbox](https://developer.tbank.ru/docs/intro/other/sandbox), [official 1C sandbox example](https://developer.tbank.ru/docs/intro/other/integration-1c) | Fixed `GET https://business.tbank.ru/openapi/sandbox/api/v1/statement`, published test account `40702810110011000000`, `from=2024-04-26T21:00:00.000Z` | Public `Bearer TBankSandboxToken`; no customer registration, token issue or certificate is required by the sandbox API contract. This is provider mock data and never a source of real money. Normal HTTPS server-certificate verification still applies. |
| Client-bank text exchange | [NSD bank format](https://www.nsd.ru/upload/docs/edo/rp_format_1c_txt_dat.pdf), [iBank corporate export guide](https://ibank.ccb.ru/docs/Corporate_iBank2-Format_Guide.pdf) | Real `1CClientBankExchange` text upload, versions 1.01/1.02/1.03 | User uploads an actual bank export and specifies their own account; bank confirmation requires an incoming record with settlement date and explicit approval. File upload is distinct from a direct bank API connection. |

## Operator configuration

Set `MANDATO_INTEGRATIONS_JSON` in the server's existing private environment or
secret delivery process. It is a JSON array. Every entry must include an exact
existing `tenant_id` and a supported `provider`. Duplicate bindings fail closed.
There is no wildcard, owner-account fallback, browser credential input or
customer-controlled request URL. Publicly registered tenants inherit no binding.

Example with placeholders only (do not commit real values):

```json
[
  {
    "tenant_id": "EXISTING_TENANT_UUID",
    "provider": "one_c",
    "base_url": "https://erp.example.ru/accounting/odata/standard.odata",
    "username": "mandato_readonly",
    "password": "SECRET",
    "entity": "Document_Invoice",
    "data_kind": "receivables",
    "mapping": {
      "source_id": "Ref_Key",
      "company": "CustomerName",
      "inn": "CustomerINN",
      "number": "Number",
      "issued_on": "Date",
      "due_on": "PaymentDueDate",
      "amount": "Total",
      "balance": "OutstandingBalance"
    }
  },
  {"tenant_id": "EXISTING_TENANT_UUID", "provider": "diadoc", "token": "OAUTH_ACCESS_TOKEN", "box_id": "ORGANIZATION_BOX_GUID"},
  {"tenant_id": "EXISTING_TENANT_UUID", "provider": "dadata", "token": "DADATA_API_TOKEN"},
  {"tenant_id": "EXISTING_TENANT_UUID", "provider": "tbank", "token": "BANK_READ_ONLY_TOKEN", "account_number": "40702810000000000001", "excluded_own_accounts": ["40702810000000000002"]}
]
```

1C names above demonstrate the mapping syntax; they are **not** a promised
configuration schema. Inspect the actual published metadata and publish a
read-only projection if required. Required normalized fields for a metadata
read are `source_id` and `company`; other allowed fields are `inn`, `number`,
`issued_on`, `due_on`, `amount`, `paid_amount` and `balance`.
Amounts must represent RUB, as explicitly verified by the operator's mapping;
aggregate balances do not become invoices. A dedicated balance import remains
available through the existing accounting reconciliation routes.

To import individual receivable invoices, declare `data_kind=receivables` and
explicitly map `number`, `issued_on`, `due_on`, `amount` plus at least one of
`paid_amount`/`balance`. The due date must be present in the source; no payment
term is invented. Balance-only derives opening paid as total minus balance;
both fields, when mapped, must reconcile. The default `data_kind=metadata` and
explicit `data_kind=balances` cannot become invoices. A missing settlement field
never silently means unpaid. Coverage exposes `invoice_import_supported` so UI
can offer the correct import path.

For an approved on-premise 1C publication only, the same operator binding may
include `"allow_private": true`. This permits that fixed configured host to
resolve privately and, if necessary, use HTTP inside the operator's network.
Prefer HTTPS and a read-only publication restricted by network policy. Other
providers always use fixed public HTTPS endpoints. No request-supplied URL,
redirect, proxy environment variable or provider continuation URL is followed.

## Authenticated API

All routes require the existing session and CSRF protection on POST requests.
Every read, saved preview and approval is tenant-scoped. Read requests finish
before database write transactions begin.

- `GET /api/integrations` returns `{items:[{provider,configured,status,checked_at,coverage,message}]}`. Providers are `one_c`, `diadoc`, `dadata`, `tbank`, `bank_exchange`. File upload is `available`; configured external providers remain `not_checked` until read.
- `POST /api/integrations/one_c/read` and `POST /api/integrations/diadoc/read` accept no body and return a saved `{id,provider,status,items,coverage,checked_at,message}`.
- `POST /api/integrations/tbank/read` accepts `{"from_on":"2026-10-01","to_on":"2026-10-24","cursor":null}`; `to_on` is exclusive. The operator-bound account is used, so browsers cannot substitute another account. A partial page has `status=partial` and `coverage.next_cursor`; request the next bounded page explicitly with that cursor and the same period. Each page retains its own preview and approval.
- `POST /api/integrations/tbank/sandbox/read` accepts only `{"mode":"sandbox"}`. Its account, date, public authorization and sandbox endpoint are fixed server constants taken from official documentation; no user data is sent. No operator credentials or production account binding are needed. It saves `provider=tbank_sandbox`, `environment=sandbox`, `mode=sandbox`, `coverage.synthetic=true` and `ledger_effect=forbidden`. All items are unapprovable. Real-source and invoice approval routes refuse sandbox runs with 422. The production route forbids a client `mode` override, and a production operator binding configured with `mode=sandbox` is not used.
- `GET /api/integrations/runs` returns up to 100 saved reads; `GET /api/integrations/runs/{id}` returns one read and its approval result.
- `POST /api/integrations/runs/{id}/approve` accepts `{"reason":"Checked against source","selected_rows":[1,2]}`. 1C/Diadoc approval retains source evidence only. T-Bank approval inserts selected eligible settled incoming RUB payment orders into the existing bank source table, leaving them entirely unallocated.
- `POST /api/integrations/runs/{id}/invoice-preview` accepts `{"selected_rows":[1,2]}` for an explicitly mapped individual 1C receivables source. It returns the existing finance import shape `{id,items,errors,changes}` plus `source_run_id`, `selected_rows`, and `source_provider`. It creates a preview, not ledger invoices. Approve valid changes explicitly through `POST /api/finance/imports/{id}/approve` with `{"reason":"Source, due dates and balances checked"}`. Opening paid remains opening paid, never bank cash. Missing mapped terms or metadata/aggregate sources return 422.
- `POST /api/integrations/registry/check` accepts `{"inn":"7707083893"}` and saves the exact lookup result. `GET /api/integrations/registry/checks` returns the latest result per INN.
- `POST /api/integrations/bank/preview` accepts `{"content":"BASE64_OF_ORIGINAL_FILE_BYTES","own_account":"40702810000000000001","source_ref":"Statement 2026-10"}`. It returns `{id,items,errors,source_hash,encoding,own_account,source_ref,format}`. Rows are document ordinals, starting at 1.
- `POST /api/integrations/bank/imports/{id}/approve` accepts the same reason/selected_rows approval shape and returns `{imported,skipped}`. An identical repeat returns its original result; changing an approved selection is a conflict.

Each read uses a bounded single page. `coverage.complete=false` explicitly means
the portfolio is incomplete: no next-link supplied by a remote system is ever
followed. Use T-Bank's returned cursor with the same period for subsequent
bounded page requests, or narrow its time interval. Larger 1C and
Diadoc portfolios need a subsequent reviewed pagination extension or existing
file/accounting import. No empty partial page is represented as a verified full
portfolio. No adapter sends, signs or alters an external document or payment.
An OData response containing exactly the requested 500 records is conservatively
incomplete even when its server omits a next-link; absence of that link is not a
verified total count.

## Source identity and money

Money is parsed with decimal arithmetic into integer kopeks. Fractional
kopeks, non-finite values, negative or zero receipts, wrong currency, future
dates, unsettled bank authorizations and identity mismatches are refused.
Bank uploads support declared Windows-1251, DOS-866 and UTF-8 encodings, require
a complete file terminator and reject duplicate fields or document identities.

Bank identity combines own account, payer account, document number, document
date and document type. The amount is deliberately excluded from the identity:
an altered amount conflicts instead of becoming new cash. The same identity is
used for T-Bank settled payment orders and client-bank files, preventing double
counting when both representations are loaded. Full normalized source-fact
fingerprints detect changed purposes and party details. File names and approval
wording are provenance and cannot create a second receipt. T-Bank's own
operation ID is also retained as independent provenance. Unsupported transaction
types can be inspected but cannot be approved as payment orders.
Numeric document numbers normalize leading zeros (`42` and `000042` refer to
the same document). Before inserting any new source, an additional ambiguity
gate checks existing manual/legacy sources on date and amount plus matching
normalized payer or reference. Two sources with fully known, distinct bank
document identities (for example verified orders 42 and 43) remain distinct even
when payer, amount and receipt date coincide. A legacy/manual source without
enough identity evidence returns 409 for operator reconciliation; it is neither
silently merged nor added as a second receipt.

After checking the actual bank originals, a genuinely separate receipt with a
different normalized document reference can be approved using additional fields
`"distinct_confirmed": true` and a nonempty `"distinct_reason"` on the file or
direct-bank approval. The server records candidate source IDs, actor, time and
reason in `integration_bank_resolution_events` within the financial transaction.
This cannot override an identical normalized reference (`42`/`000042`). Approval
confirmation is strict boolean; it is not inferred from the normal reason field.
The shared helper `assert_no_duplicate_source(connection, tenant_id, item,
distinct_confirmed=False, reason='', actor_id=None)` provides the same gate for
manual bank entry, after exact external-ID retries and before inserting cash.
Approval-only flags must not enter immutable bank-source retry comparisons.

No automatic invoice allocation occurs. Returns, outgoing operations, transfers
between any own accounts declared in the same statement, foreign-currency operations
and ambiguous transactions require the appropriate existing ledger workflow.
For T-Bank, the operator should list the tenant's other known accounts in
`excluded_own_accounts` (up to 100 exact account numbers); transfers between them
and the bound account cannot be approved as external receipts. Accounts outside
the statement/operator configuration cannot be independently identified as the
tenant's own; the approval reviewer must still check the payment's economic basis.
Source approval is an operator attestation, not cryptographic verification of
the uploaded file's authenticity.

## Registry evidence and freshness

The registry result is `{id,inn,provider,status,checked_at,coverage,result,message}`.
On a successful exact match, `result` contains `inn`, `name`, `ogrn`,
`registration_status`, `state` (same provider status), `provider_record_date`,
`provider_record_date_status=available|unknown`, and `provider_as_of=null`.
Registration statuses are `ACTIVE`, `LIQUIDATING`, `LIQUIDATED`, `BANKRUPT` or
`REORGANIZING`; they are provider facts, not a recovery probability.

`coverage` is always explicit:

```json
{"egrul":"provider_snapshot","bankruptcy":"unverified","court_cases":"unverified","fssp":"unverified"}
```

The DaData registration state may say `BANKRUPT`; this adapter still does not
claim a complete bankruptcy publication search. Court cases, FSSP enforcement
and the full bankruptcy register require separate documented sources/evidence.
`unconfigured`, `unavailable` and `no_match` retain an empty `result`; none means
the debtor is risk-free. DaData documents `state.actuality_date` as the record's
last-change date, so it is labelled `provider_record_date`; it is not evidence
that a stable company became stale just because nothing changed for years.
Absent record date is explicit unknown metadata. A successful exact lookup is
`completed` even with an old or unknown record-change date; it asserts only a
fresh query of a provider snapshot, not live verification with the FNS. Future
record dates are rejected. Retrieved evidence becomes `stale` after 24 hours
based on `checked_at` when read. This is a conservative product refresh window,
not a legal deadline or provider guarantee. Every check remains in history; latest lookup
failure is shown as failure rather than silently reusing an earlier clean state.

Server integration point: `latest_registry_checks(connection, tenant_id)` returns
`dict[inn, latest_result]` for the portfolio snapshot. It does no network I/O.

## Transport and release evidence

Transport allows at most 2 MB of uncompressed JSON, an 8-second socket timeout
and a 20-second read deadline. It validates resolved addresses, rejects private
and special addresses for public providers, pins the selected address for the
TCP connection, and retains hostname certificate validation/TLS SNI. Redirects,
compressed responses and malformed contracts fail closed. Provider exception
texts and raw bodies are not persisted or shown. Only allowlisted normalized
fields are retained; tokens remain in the operator environment.

Run local contract and financial-boundary checks with:

```sh
.venv/bin/python -m pytest tests/test_integrations.py tests/test_bank_exchange.py -q
```

Before claiming a live integration, supply each tenant's actual read credentials,
verify their 1C mapping and scope, exercise a real source read and reconcile a
real bank preview with its statement. Record the actual provider/version,
verification time and covered period privately without copying secrets into
release notes. No bank partnership, certification, court filing, electronic
signature verification or complete debtor risk clearance is asserted here.

### Free public sandbox verification, 24 October 2026

Exactly one real connection attempt used the official sandbox endpoint, published
test account/period and public test constant. It sent no customer data and wrote
no financial ledger rows. The connection failed before an HTTP response:
`SSLCertVerificationError`, errno `1`, certificate verification code `19`
(self-signed certificate in the certificate chain). `http_status` is null and
response parsing is **not verified**. Certificate verification was not disabled
and no alternate endpoint was guessed. The redacted reproducible evidence is
[tbank-sandbox.json](evals/tbank-sandbox.json).

This failure does not establish a provider outage or a successful bank
integration. The operator needs an appropriately trusted server certificate chain
in the runtime before repeating the free check. Public sandbox responses are
fixed provider examples, can differ from the query's account/period and are
handled in a separate namespace with an unconditional approval prohibition.
