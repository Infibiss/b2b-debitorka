# Private document recognition and browser dialogue

Implemented for the approved 26 October 2026 workflow. These adapters send real
requests to fixed Yandex endpoints only when explicitly enabled for the bound
organization. Automated tests use provider contract doubles. On 26 October 2026, separate live
requests from the existing VM successfully recognized a synthetic invoice image,
synthesized an Ogg phrase and recognized its PCM conversion with SpeechKit.
No customer data or external telephone calls were used. A separate isolated-process API canary verified persisted OCR acceptance and the
voice graph without financial writes; Yandex classified a paraphrased document
request as `documents`. This one example is not a general model-quality benchmark. A configured key alone is not evidence
that its OCR/SpeechKit roles or API scopes work.

## Operator setup

Use the existing private server environment and existing owner service-account
API key. Do not put a key in the browser or repository. Required variables:

- `YANDEX_API_KEY`: existing service-account API key.
- `YANDEX_AGENT_TENANT_IDS`: explicit UUID allowlist, reused from the agent policy.
  An empty allowlist disables both services even in development. Public signup
  cannot inherit the owner's paid key.
- `YANDEX_OCR_ENABLED=true`: explicit operator enablement for document OCR.
- `YANDEX_VOICE_ENABLED=true`: explicit enablement for browser dialogue and speech.
- `YANDEX_AGENT_MODEL` or `YANDEX_MODEL`: optional existing `gpt://...` model URI.
  Enables bounded intent classification; otherwise dialogue uses documented rules.

The service account needs `ai.vision.user` for OCR, `ai.speechkit-stt.user` for
recognition, `ai.speechkit-tts.user` for synthesis, and `ai.languageModels.user`
when model intent classification is enabled. API-key scopes and folder access
must allow those operations. Roles are documented in the
[official role reference](https://yandex.cloud/en/docs/iam/roles-reference).
No roles, billing settings or cloud resources are changed by this module.

`GET /api/yandex/status` reports configuration separately from the last request.
`not_checked` means no successful access verification has happened. Provider
401/403 responses become `permission_required`; the UI names the required roles.
This status route does not make a paid probe. The last request status is
historical, not a guarantee about future availability. Enable the browser
microphone for this origin through `Permissions-Policy: microphone=(self)`;
HTTPS and an explicit browser permission are required for capture.

## Official request contracts

| Operation | Fixed endpoint | Contract and scope |
| --- | --- | --- |
| OCR | `POST https://ai.api.cloud.yandex.net/ocr/v1/recognizeText` | `content`, `mimeType` (`PDF`/`PNG`/`JPEG`), `languageCodes`, `model=page`; reads `result.textAnnotation.fullText` (or the direct envelope). [Official recognition reference](https://aistudio.yandex.ru/en/docs/vision/ocr/api-ref/TextRecognition/recognize). |
| STT | `POST https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?lang=ru-RU&format=lpcm&sampleRateHertz=16000` | Raw mono PCM16LE bytes; returns JSON `result`. [Official synchronous recognition reference](https://aistudio.yandex.ru/en/docs/speechkit/stt/api/request-api). |
| TTS | `POST https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize` | URL-encoded `text`, `lang=ru-RU`, `voice=filipp`, `format=oggopus`; binary Ogg response. Service-account requests omit `folderId`. [Official synthesis reference](https://aistudio.yandex.ru/en/docs/speechkit/tts/request). |
| Optional intent classification | `POST https://ai.api.cloud.yandex.net/foundationModels/v1/completion` | Existing model URI; JSON schema permits only eleven intent names, maximum 60 output tokens. No arbitrary generated financial prose or tools. [Official completion reference](https://aistudio.yandex.ru/en/docs/ai-studio/text-generation/api-ref/TextGeneration/completion). |

Every request uses server-side `Authorization: Api-Key ...` and
`x-data-logging-enabled: false`. OCR/intent reuse the bounded public destination
transport in `integration_providers.py`; binary SpeechKit requests use the same
bounded DNS pool, validate public IPs and pin the validated address to a TLS
socket while preserving hostname verification. Proxy environment settings,
redirects, compressed responses and request-supplied URLs are not used. Provider
bodies and exception messages are never exposed as errors or stored as diagnostics.

## Document flow and limits

`POST /api/yandex/documents` accepts JSON `{content, mime_type, filename,
invoice_id?}` where content is original-byte base64. Documents are private to the
session's tenant. The optional invoice must belong to that tenant.

The application limit is 1,000,000 original bytes, five PDF pages and 20 million
image pixels. It checks signatures and dimensions; PDF parsing rejects malformed
or encrypted files. `pypdf==6.21.2` is pinned, selected from the
[official package release](https://pypi.org/project/pypdf/6.21.2/). Synchronous
Yandex OCR accepts one PDF page per request: the adapter splits an accepted PDF,
removes annotations/actions from the submitted page copy, and makes at most five
page requests. Original bytes remain unchanged in the private database.

A reservation is committed before any provider request and before releasing the
write lock. SQLite's writer lock and PostgreSQL's existing transaction advisory
lock serialize quota admission. Network requests happen outside write
transactions. Limits are 10 pages per user per UTC day and 20 per organization;
failed attempts consume their reserved units. A repeated original fingerprint
for the same user/tenant returns the original reservation. Rebinding that same
original to another invoice returns a conflict instead of charging again.

Each completed page is saved with ordinal and page-copy hash. The aggregate has
original SHA-256, source endpoint/model, uploader, timestamp, filename, MIME type
and invoice linkage. Provider JSON is bounded to 2 MB per page, extracted text to
30,000 characters across all pages, and the operation to 25 seconds. An interrupted
multi-page operation keeps its completed pages but cannot be accepted as complete.
A processing or failed reservation is never automatically retried, including
uncertain network outcomes and server restarts. An operator must investigate an
uncertain outcome; this implementation intentionally has no charge-producing
retry button.

`GET /api/yandex/documents` lists the latest 50 tenant documents;
`GET /api/yandex/documents/{id}` returns the saved result.
`GET /api/yandex/documents/{id}/original` serves the authenticated original as an
attachment with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

`POST /api/yandex/documents/{id}/accept` accepts `{text, fields, reason}` for a
completed result. The operator can correct text and metadata before accepting.
Allowed string metadata keys are `company`, `inn`, `number`, `issued_on`, `due_on`,
`amount`, `contract`, `notes`; values are evidence, not normalized financial facts.
Acceptance records actor/time/reason and retains the original recognized result.
An identical repeat returns its original version; changing an accepted version
is a conflict. Acceptance never inserts invoices, payments, promises or ledger
adjustments. Recognized text is not proof of a debt.

## Browser voice and dialogue graph

`YandexDesk` exports props `{invoices: Invoice[], notify, invoiceId?}` and shows
“Разговор по счёту”. The browser user plays the selected counterparty's
representative; Mandato speaks as the creditor's assistant. This browser roleplay
is not an external phone call, verified debtor communication or authority to
change financial records. There is no external telephone number.

Click “Начать разговор” to hear a business greeting and questions about a
convenient time and authorized representation. The server discloses no company,
invoice number or amount until the logged-in operator explicitly confirms the
roleplay representation switch for the selected invoice. That confirmation is
recorded with actor and invoice. It is **not** real-world identity verification.
The switch resets when changing invoices; every utterance must carry the boolean
`identity_confirmed=true` to permit disclosure. A spoken “yes” alone cannot bypass
this gate. Request fingerprints include that flag to prevent a retry key from
returning a different disclosure level.

The microphone starts only on explicit click. Capture stops at 20 seconds and
resamples to mono 16 kHz PCM16LE, at most 640,000 bytes. Stop-and-send and discard
are separate buttons. Tracks, audio nodes, contexts and timers are released on
stop, cancellation, invoice change and unmount; late permission results after
unmount are discarded. No recording starts on page load.

`POST /api/yandex/voice/opening` accepts `{invoice_id, request_id}` and produces the
greeting without STT. `POST /api/yandex/voice/turn` accepts `{audio, invoice_id,
request_id, identity_confirmed?}` with base64 PCM bytes. Odd, empty or oversized
input is rejected before any provider call. `POST /api/yandex/voice/text` accepts
`{text, invoice_id, request_id, identity_confirmed?}` and runs the same dialogue
without microphone/STT. Typed text is bounded to 1,000 characters.
`GET /api/yandex/voice/turns?invoice_id=...` returns up to 20 turns for that
user/invoice within the current tenant.

The actual LangGraph is `safe_facts → bounded_intent → next_response/handoff`.
Its eleven fixed intent names are balance, documents, promise, dispute,
paid_claim, reason, confirm, not_now, transfer, mutation and help. A configured
Yandex model receives the current stage and last three same-user/invoice turns
to understand short replies and pronouns. It returns only an intent enum;
financial prose is constructed from validated server-side facts. Failed or
invalid intent output uses bounded rules and records `intent_source`. Explicit
signals about paid claims, disputes, refusal, transfer or mutation cannot be
softened by the model. No model call is made before the identity gate opens.

The saved `dialogue_state` carries the conversation stage, claimed reason for
delay, proposed amount/date and handoff details; these are transcript metadata,
not ledger facts. After representation confirmation the agent states the actual
adjusted remaining balance and asks the reason for delay. Future-payment replies
collect the exact amount in rubles and calendar date, validate that the amount is
positive and within the remaining balance and the date within the next year,
then ask for explicit confirmation. Relative “tomorrow” uses the application's
business timezone. Confirmation is recorded only in the transcript.

“We paid yesterday” asks the caller for payment-order number, date and amount,
explains bank verification and avoids asking for a duplicate payment. Document
requests ask which document and period, recording the request for staff rather
than claiming to send it. Disputes or a request for a human set
`handoff_required=true`, preserve the details and stop reminder language in the
conversation. An inconvenient time asks for a callback preference without
continuing collection. No real callback, external message, case-status update,
workflow exception or staff assignment is claimed to have occurred. Staff must
review the transcript and perform any authorized action in the case workflow.

The reply is sent to real SpeechKit TTS and returned as base64 `audio/ogg` with
transcript, reply, intent source and executed node names. The UI offers native
audio controls and tries to play only the newly returned answer; historical turns
never autoplay. Browsers blocking playback or Ogg still retain the transcript and
answer. A synthesis failure retains the text and is visibly unavailable rather
than a fake audio success. Audio input is not stored; transcripts, replies and
synthesized audio remain private in the database. No external phone number or
outbound call is configured or claimed.

Voice allows 10 turns per user and 20 per organization per UTC day, including
failed reservations. Same-key repeats return the original turn; changed content
or invoice under an existing key conflicts. STT, optional intent and TTS share a
30-second operation deadline; single network stages are at most 20 seconds, STT
JSON at most 32 KB, TTS at most 1 MB. All turns declare `ledger_effect=none`.

## Verification

`python -m pytest tests/test_yandex_services.py -q` exercises idempotency,
quota admission, tenant isolation, original download and corrected acceptance,
PDF page splitting/caps/partial failure, provider permission failures, grounded
adjusted amounts, actual LangGraph routing and bounded optional model intent,
STT/TTS request shapes, private DNS and binary transport rejection paths. These
are contract tests, not evidence of live Yandex permission or speech quality.
