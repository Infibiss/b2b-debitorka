# Connection access preparation

`ConnectionAccess` is an administrative guide in the existing Connections desk.
It helps an owner collect a concrete access request without collecting secrets.
It does not provision accounts, purchase services, send messages, save provider
credentials, or claim to connect sources that have no implemented adapter.

## Embed and status contract

```tsx
import { ConnectionAccess } from './ConnectionAccess';
// Inside ConnectionsDesk, before the source-reading cards:
<ConnectionAccess />
```

No props are required. The component requests the authenticated
`GET /api/integrations` on mount and when the user chooses “Обновить статус”.
It retains only `provider`, `configured`, `status`, and `checked_at`; keys,
provider response bodies and credentials are not returned by that endpoint.
`configured` means the operator supplied the required binding fields. It does
**not** prove credentials are valid, the network is reachable, or a live read
succeeded. The most recent read outcome and date are shown separately. Failed
status retrieval shows “Статус не получен”, never “connected”. An unsuccessful
read may be dated: that is the last attempt, not a successful verification.

The guide maintains its own status request, independently of the desk’s read
history. Use its refresh action after changing operator configuration or reading
a source. It makes no provider read requests itself.

## Manager handoff

1. Select the actual source and read its scope and cost prerequisites.
2. Collect the prerequisite decisions with the listed owner. Checkboxes only
   track preparation in the current mounted page; they do not enable access.
3. Copy the selected provider’s IT request or download all providers as TXT/JSON.
   The component has no fields in which to enter credentials or account values.
4. Arrange a protected credential handoff and server environment delivery with
   the deployment operator. Bind access to the exact existing organization.
5. Refresh status, then use the existing desk’s source read and explicit review.
   Compare the sample against the real source before accepting ledger changes.

The export `mandato-access-checklist.json` has schema
`mandato.connection-access.v1`. It includes generated time, current safe status,
field **descriptions**, owner, scope, cost prerequisites, official links,
acceptance conditions and manually checked preparation steps. It includes no
credential values, configuration URLs belonging to the customer, account values,
customer invoices or tenant IDs. TXT exports the same human-readable tasks;
the clipboard action copies only the selected provider. Nothing is sent to IT.

## Actual access paths

| Source | Who prepares access | What the current adapter needs | Commercial / implementation boundary |
| --- | --- | --- | --- |
| 1С | Administrator of the customer’s 1С plus accountant | Standard OData publication, approved network route, dedicated read-only username/password, actual collection name and field mapping | Existing licensed 1С and configuration work are prerequisites. No universal invoice mapping is assumed; balance-only data is not an invoice feed. |
| Diadoc | Organization’s EDI administrator and Diadoc operator | Authorized OAuth Bearer access token with production `Diadoc.PublicAPI` scope and organization `box_id`; service user must have read access to the incoming documents | Confirm access and integration licensing with operator under the organization’s contract. The free reception of incoming documents does not establish that a custom integration has no cost. Tokens expire; the current adapter does not refresh them. Reads metadata, not original content or signatures. Other EDI operators are not implemented. |
| T-Bank | Existing account owner / T-Business administrator | Token with minimum statement access, 20-digit own RUB account and other own accounts to exclude internal transfers | T-API is advertised as free, but an existing company’s bank account and T-Business access are required; bank-account servicing has its own tariff. No payments need to be permitted. Other banks use the existing `1CClientBankExchange` import until an adapter is implemented. |
| DaData | Owner of an existing authorized DaData account | Ordinary API token bound to the exact organization | Published find-party allowance is up to 10,000 free daily requests; verify the account quota. No Secret key or paid standardization API is needed. This adapter only establishes exact identity and registration state. |
| Court cases | Lawyer | Manual KAD search and matching actual party / case | No automated adapter. An approved published/licensed API, access terms and implementation are needed for automation. |
| FSSP | Lawyer | Manual official bank-of-enforcement-proceedings search | No automated adapter. Current availability of a free public API is unverified. Do not integrate the obsolete API, scrape around restrictions or bypass CAPTCHA. Require current provider documentation and explicitly issued access before implementing automation. |
| Bankruptcy / EFRSB | Lawyer | Manual exact debtor search, published messages and their dates | No automated adapter or full bankruptcy verification. Require published API terms, any applicable license and credentials before implementing automation. |

For 1С invoices, the configuration must supply company, invoice number, issue
date, due date, total and paid amount or balance. The operator must validate RUB
units and the mapping against the real configuration. Metadata reads need fewer
fields but must never be presented as a configured invoice import.

## Secret handling boundary

The application currently has no self-service encrypted credential store and no
browser credential submission endpoint. Do not add actual credentials to this
checklist, source code, committed examples, chat or repository-root config files.
The existing server supports `MANDATO_INTEGRATIONS_JSON` delivered through the
operator’s private process/environment; follow the existing contract in
[integrations.md](integrations.md). This guide does not create that variable or
assert that the deployment already has an encrypted secret manager. Secure
storage and delivery must be agreed with the deployment operator before handling
customer credentials. Avoid command-line arguments containing credentials and
log output that can reveal them.

## Primary sources checked on 26 October 2026

- [1С publication setup](https://1c-dn.com/anticrisis/tools-and-technologies/embedded-web-client/setting-up/): standard OData publication and web-server prerequisites.
- [1С Standard Subsystems Library, OData Interface](https://1c-dn.com/library/tutorials/1c_standard_subsystems_library_3_1_11/): administrator-selected published objects and `RemoteODataAccess` rights.
- [Diadoc API documentation](https://developer.kontur.ru/doc/diadoc-api/index.html) and [integration access page](https://www.diadoc.ru/integrations/api): access is requested from operator; no request was submitted.
- [Diadoc authentication](https://developer.kontur.ru/doc/diadoc-api/authentication.html): OAuth `access_token` is passed as Bearer; access tokens have limited lifetime, client credentials alone are insufficient.
- [Diadoc tariffs](https://www.diadoc.ru/price): existing operator terms and integration conditions must be checked separately.
- [T-API getting started](https://developer.tbank.ru/docs/api/t-api): an ООО/ИП, T-Business access and token are required; customer-data access can require partner integration.
- [T-Bank official API overview](https://www.tbank.ru/business/open-api/): API advertised as free; [statement method](https://developer.tbank.ru/docs/api/get-api-v-1-statement): production account statements, explicit period and cursor pagination.
- [DaData find-party method](https://dadata.ru/api/find-party/): confirmed email, ordinary API token and published free daily allowance; registration data is not complete litigation/enforcement coverage.
- [Official KAD](https://kad.arbitr.ru/): public court case search.
- [Official FSSP bank of proceedings](https://fssp.gov.ru/iss/ip) and [official EFRSB](https://bankrot.fedresurs.ru/): manual destinations; automated fetching was blocked by those sites during research, so current API availability is **not verified**. No general API availability or free integration is asserted.

The old 2022 FSSP API suspension is historical evidence, not proof of current
availability. Use a current official contract and granted access if pursuing
an automated integration.

## Verification

Run `npm run check` after embedding. The component only adds a status GET and
local clipboard/download actions. No credential settings, server routes or
provider adapters are changed by this component.
