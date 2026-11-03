# Mandato MVP workflow and interface implementation plan

Goal: simplify the existing accountant/lawyer workflow and complete implementable legal-case gaps without connecting mail or SIP.

Architecture: retain four workspace sections and tenant-isolated financial ledger; expand legal-case scope through explicit invoice membership with backward compatibility. Preserve evidence, document freshness and manager approvals. Shared design tokens define semantic colors, form controls and spacing.

- [x] Refresh main; inspect CI/deployment without expanding SSH access.
- [x] Remove obsolete Render blueprint, archive historical documentation clearly; protect private source documents, keys, dumps and SQLite sidecars in Git and Docker contexts.
- [x] Implement contract-based legal cases, safe transition after order cancellation, explicit responsible lawyer/review workflow with regression tests and migration compatibility.
- [x] Simplify workspace chrome, remove duplicated actions/footer slogans and entry-help dropdown; repair password recovery and settings layout.
- [x] Simplify documents and related tools with consistent upload controls, status colors and direct task language.
- [x] Establish documented design tokens and consistent select arrows, file controls, spacing, warning/success states across desktop/mobile.
- [x] Visually inspect all major screens in browser using an isolated synthetic account; fix confirmed problems and capture evidence.
- [x] Run server/financial regression checks, TypeScript, production build and browser tests; review changes.
- [ ] Publish the reviewed revision and verify GitHub CI.
- [ ] Deploy manually once pinned SSH access is available; do not expand network access. Current blocker: SSH banner timeout.

Acceptance: no duplicate workspace title/footer shortcuts; section help remains available; no raw browser file controls; disconnected mail is a warning; legal case totals cannot count an invoice twice or cross tenants; old legal documents remain accessible and stale versions require review; no live external sends or paid calls during testing.
