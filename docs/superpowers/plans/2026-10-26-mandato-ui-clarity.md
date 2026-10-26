# Mandato UI clarity implementation plan

> For agentic workers: use superpowers:subagent-driven-development. User supplied explicit UI corrections; implement them without another permission gate.

**Goal:** Исправить видимые дефекты и убрать перегрузку, сохранив существующие операции.
**Architecture:** Только React/CSS и браузерные регрессии; серверные финансовые контракты неизменны. Подключения используют прогрессивное раскрытие; обучение хранит прогресс по user/section.
**Tech Stack:** React, TypeScript, CSS, Playwright, существующий FastAPI/PostgreSQL runtime.

## 1. Reproduce and landing
- [x] Add e2e/ui-clarity.spec.ts: header line bounds at 1280/1728/desktop/mobile, landing footer icon/text adjacency, no decorative kicker text.
- [x] Build old bundle and run focused tests to record failures.
- [x] Replace forced h1 breaks in Landing.tsx; remove decorative labels. Namespace landing card classes to avoid workspace.css collision, constrain desktop typography/grid and responsive stacking in landing.css.
- [x] Run focused tests and visually inspect desktop/mobile screenshots.

## 2. Contextual learning
- [x] Update workflow browser regression and add tests for per-section progress, back/next, keyboard, no blocking backdrop, corner position and interaction with page while learning.
- [x] Replace Dialog usage in WorkflowOnboarding.tsx with a nonmodal labelled aside; concise per-tab steps, section prop, independent storage, safe highlight cleanup, close/Escape and optional first prompt.
- [x] Workspace.tsx passes current main section and help replays only that section; no navigation by tour.
- [x] Verify resumed progress, skip, all four tabs, mobile bounds and reduced motion.

## 3. Audit controls and connection catalogue
- [x] Add focused browser tests: audit selects keyboard and reserved chevron area; initial connections shows source chooser only, selected source operations, collapse/back, all old import/reconciliation actions still reachable.
- [x] Fix portfolio select appearance/right padding and nested empty state in PortfolioDesk.tsx/portfolio.css.
- [x] ConnectionsDesk.tsx renders a catalogue and one selected source; ConnectionAccess.tsx accepts source filter and hides IT detail until requested. Keep actual provider status, private access prerequisites and financial confirmation safeguards.
- [x] Update existing service-browser navigation for intended progressive disclosure; run all browser tests.

## 4. Release
- [x] Resolve overview decision from human; preserve functionality and document map of tools to main sections.
- [x] TypeScript, build, formatting, all browser and server regressions; independent spec and code review.
- [x] Commit/push, verify CI, private backup, exact-SHA manual deploy to same VM, verify HTTPS and unchanged financial fingerprint; private copy and rollback retained.
