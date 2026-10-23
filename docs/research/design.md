# AgentPay — design research and editorial direction

Research date: 2026-10-24. Product: Russia-first B2B receivables workspace.

## Sources and what was actually inspected

- [SOLTERA / Diana Tatevosian / Behance](https://www.behance.net/gallery/249098715/SOLTERA-Wind-Energy-Landing-Page-Web-Design), published 2026-05-12. The project page returned 403 on direct fetch. Search-indexed project modules and their image descriptions were accessible. They show a panoramic wind-farm hero, transparent navigation overlay, very large uppercase heading, compact edge metadata, and airy white sections. This is evidence of composition, not a license to reuse the artwork, copy, fictitious metrics, or testimonials. [Hero / hierarchy source image](https://mir-s3-cdn-cf.behance.net/project_modules/1400/b71529249098715.6a00a4ad60d05.png). [Desktop and mobile source image](https://mir-s3-cdn-cf.behance.net/project_modules/1400_webp/1690ee249098715.6a00a4ad61a5a.png).
- [Pinterest reference](https://ru.pinterest.com/pin/682436149834058963/). The supplied pin could not be fetched or identified reliably through web search. No specific visual observations are attributed to this pin.
- [Upflow home](https://upflow.io/) and [Collections](https://upflow.io/features/cash-collection). The product narrative links receivables insight, collection work, and payment. Collections documents configurable agent autonomy, unified customer context, promises to pay, and dispute escalation. Adopt a visible human review step, an account timeline, and a distinct dispute state. Do not import Upflow customer logos, performance claims, or US-oriented integration assumptions.
- [Mercury](https://mercury.com/) and [Invoicing](https://mercury.com/invoicing). Invoicing explains concrete jobs through interface examples: see who owes what, filter by status, send reminders, and reconcile receipts. Adopt the close connection between concise benefit and recognisable working screen. Do not inherit banking product claims or foreign payment rails.
- [Ramp](https://ramp.com/). The homepage uses short business-outcome language, a single clear first action, and workflow-led product navigation. Adopt the clarity and directness, while avoiding its scale and results claims.
- [Linear](https://linear.app/). The page exposes product objects, statuses, activity, and agent work in a credible interface rather than relying on abstract AI imagery. Adopt the density control, hairline divisions, product-led storytelling, and legible work history. It is a product craft reference, not a fintech category competitor.

These observations come from primary product pages and indexed source artwork. The direction below is an original recommendation for AgentPay, not a claim that these sites use these exact tokens.

## Art direction

The site should feel like a financial operating desk expressed as an editorial composition: warm paper, strong ink, generous empty space, and a precise lime accent. Borrow SOLTERA’s scale and calm hierarchy. Replace its scenic photograph with a bespoke composition of document sheets, payment paths, ledger rules, and a concise live workflow. This keeps the financial subject visible immediately.

Suggested tokens:

| Role | Value | Use |
| --- | --- | --- |
| Paper | `#F4F3EC` | Main background |
| White | `#FFFFFF` | Working surfaces |
| Ink | `#17211C` | Titles, text, primary button |
| Secondary | `#6D756D` | Captions and metadata |
| Rule | `#DADDD2` | Fine dividers and table lines |
| Chartreuse | `#D8ED72` | One active accent and selected state |
| Soft lime | `#EAF0D3` | Secondary highlights |
| Caution | `#A16331` | Late invoices and review state |

Use the accent sparsely. Never use green as the only indication of success; pair it with a check and label. Reserve red for an actual error or unresolved blocking problem. No neon gradient, glossy purple sphere, or uniform grid of floating cards.

Choose one Cyrillic-capable sans family, such as Manrope, for the whole product. Use a 500 weight for expressive marketing titles, 400 for body text, and 600 only for functional emphasis. Title tracking can be slightly negative; long Russian text needs open line spacing. Numeric tables should use tabular figures. Use 72–104 px desktop hero type, 42–54 px mobile, with a deliberately controlled two- or three-line wrap. Body copy should be 16–18 px. Small uppercase section labels can give the design its editorial cadence without making every title uppercase.

Use broad asymmetric sections: 7/5 hero split, a wide working canvas, a slim descriptive side column, long horizontal rules, and a dark full-width product chapter. Round buttons and selected product panels subtly; avoid rounding every container into the same pill or card.

## Motion that explains work

The hero sequence should show a single invoice moving through meaningful states: imported → due date recognised → reminder drafted → reviewed → promise recorded → payment matched. A thin animated path and restrained amount reveal are enough. There should be one active focal point at a time.

Use 180–260 ms for interface state changes and 450–700 ms for one-off section reveals. A hover can lift a button by 1–2 px or move the arrow; no elastic motion. Pause background animation when outside the viewport. With `prefers-reduced-motion`, show the complete static workflow. Keep marketing animation separate from actual app state; an attractive loop must never look like a real external message was sent.

## Russian copy direction

Use concrete verbs and familiar finance vocabulary. Lead with the business job, then explain what the agent does. Avoid unsupported numerical promises, pseudo-customer quotes, invented clients, foreign social proof, and inflated AI language. Do not put «демо», «mock», or implementation notes into the visible product flow.

Suggested site copy:

- Brand descriptor: «Дебиторка под контролем».
- Hero: «Оплаты вовремя. Отношения — надолго.»
- Supporting text: «AgentPay собирает счета и переписку в одном месте, готовит напоминания и помогает команде видеть следующий шаг по каждому клиенту.»
- Main action: «Открыть AgentPay».
- Secondary action: «Как это работает».
- Product chapter: «От счёта до оплаты. В одном процессе.»
- Inbox chapter: «Внимание — тем, кому оно нужно».
- Automation chapter: «Рутину ведёт агент. Решения остаются у вас.»
- Integration chapter: «Начните с тех данных, которые уже есть».
- Final action: «Наведите порядок в дебиторке».

If an action opens a contact form, label it «Обсудить подключение» and make the form honest about what happens next. If the application is locally functional, «Открыть AgentPay» should open that application directly. A primary action must not silently scroll to a different section.

## Marketing flow

1. Navigation: AgentPay wordmark, «Возможности», «Как работает», «Интеграции», and a clear app entry. Mobile navigation needs a working menu and a reachable close action.
2. Hero: one promise, short explanation, two purposeful actions, and an original financial workflow visual.
3. Product proof: a recognisable working view of receivables, with the state of an account changing when a tab or workflow step is selected.
4. Three business jobs: understand what is overdue; prepare and review communication; track the promise and receipt. Use long editorial rows rather than three interchangeable feature tiles.
5. Integration/start: show CSV import as the dependable first step. Present 1С, Bitrix24, and email only with their actual connection states. A planned connector should open a useful configuration or inquiry flow and must not imply a completed integration.
6. Control: show draft review, pause, responsible colleague, and event history through the product interface.
7. Focused FAQ and final app entry. No fabricated logo marquee or invented testimonial section.

## App workflow and interaction requirements

- **Overview:** total receivables, overdue amount, due this week, and a priority queue. Each total must reconcile with visible records. Make the selected period and currency clear. An empty workspace should direct the user to import data.
- **Receivables:** searchable and sortable table with company, invoice number, amount, due date, days overdue, owner, and next action. Filters must actually change rows. Selecting a row opens its detail panel without losing the list context.
- **Account/invoice detail:** invoice amount and dates first; then contact, communication timeline, promised date, and next action. Include usable actions to prepare a reminder, record a payment, add a note, pause automation, and flag a dispute.
- **Reminder review:** choose channel and recipient, inspect editable message, and confirm. Show the invoice context alongside the draft. Saving a draft and recording an event are legitimate local outcomes; never present them as a real email delivery if no sending service exists.
- **Promises:** recording a promised payment date changes the next-action state and creates a timeline event. Missed promises return to the priority queue. An ordinary due date must not be confused with a promise.
- **Import:** select or drop CSV, map columns, validate dates/amounts, preview errors, and confirm. Preserve Russian formatting and names. Duplicate invoice handling should be visible and deterministic.
- **Integrations:** connection status, last sync, and purposeful setup action. No inert switches that appear to connect external systems.
- **Settings:** organisation details, sender signature, business hours, notification preference, and agent review mode. Persist meaningful local edits between reloads when a backend is absent.
- **Search and navigation:** global search opens a usable result state; Escape closes overlays; active navigation reflects the current section. Every icon-only control needs an accessible label and clear focus indication.

For the initial workspace, use internally consistent example invoice records as working product content. Never describe those records as customers of AgentPay or as evidence of business results. Product charts should be derived from those records, with clear ruble amounts and Russian dates.

## Acceptance checks

At 1440 px, the first screen should have a distinct composition, balanced empty space, and visible financial purpose. At 390 px, heading wraps, CTAs, drawer bounds, and tables must stay usable. Navigation, app entry, filtering, drawer actions, draft edits, import, and settings should produce a meaningful result. Keyboard focus and reduced motion need their own check. The product should contain no claims of delivery, integration, customer adoption, or measured results that the implementation cannot support.
