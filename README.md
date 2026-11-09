# Floatwise

**Know what's coming.** An open-source receivables, cash-flow, and finance operations cockpit for small businesses.

> **Version 3.0** adds account authentication, isolated private workspaces, a read-only public demo, six statement-import adapters, partial payments, a bank reconciliation inbox, and an optional Plaid connector. The existing **100 live computed finance signals** and Operations Hub remain available.

**Product concept and implementation by [Samer Tallauze](https://samertall.com).**

## Why this product?

Late payments and unpredictable cash flow cause real operational friction. In the [2026 QuickBooks Small Business Late Payments Report](https://quickbooks.intuit.com/r/small-business-data/small-business-late-payments-report-2026/), 51% of surveyed small businesses with overdue invoices reported cash-flow problems, versus 36% without overdue invoices. The [Federal Reserve's report on business payments](https://www.fedsmallbusiness.org/survey/2024-report-on-payments) also documents widespread payments-related challenges.

Floatwise explores an accessible, lightweight approach to **cash visibility before cash stress**. It is designed for owners, finance leads, and agencies who need answers to three questions:

1. How much should we collect, and from whom?
2. Which unpaid invoices deserve attention first?
3. What happens to our cash if customers pay later than expected?

This repository is a *working multi-workspace MVP and engineering showcase*, not a licensed banking product or a validated business outcome.

## Features

| Product capability | What it does |
| --- | --- |
| Cash-flow command center | Outstanding, overdue, due soon, and collection-rate metrics |
| Scenario forecast | 90-day optimistic, baseline, and stress projections |
| Explainable collections | Risk scores derived from overdue age, amount, and prior payment behavior |
| Next best action | Collection recommendations with no external AI dependency |
| Receivables workspace | Create, list, search, filter, and record exact-cent partial payments |
| CSV workflow | Transactional import (250 rows/file) and Excel-safer export |
| Adjustable assumptions | Opening cash and operating expenses update all forecasts |
| Developer API | OpenAPI documentation at `/docs` and `/openapi.json` |
| Demo-friendly | Synthetic invoices are added to an empty demo database |
| Tested and containerized | Pytest, GitHub Actions, Docker, API health endpoint |
| 100-signal Intelligence Lab | Ten groups of ten independent calculated signals, with search, filters, and CSV export |
| Operations Hub | Create, edit, and delete cash events, monthly budgets, follow-up tasks, customer profiles, and saved views |
| Payment reminder drafts | Prioritized human-review messages; nothing is sent automatically |
| Activity timeline | Records creates, updates, imports, payments, and deletions |
| Reporting and backups | CSV and JSON resource reports, 100-signal exports, local JSON backup |
| Flexible horizons | API forecast from 7 through 365 days |
| Private accounts | Password-hashed accounts, HttpOnly signed-in sessions, CSRF protection, per-account SQLite databases |
| Read-only public demo | Synthetic data available anonymously; all writes require authentication |
| Six data connectors | Standard bank CSV, QuickBooks CSV, Xero CSV, QIF, OFX, and ISO 20022 camt.053 |
| Reconciliation inbox | Idempotent staging, match suggestions, explicit approve/ignore/post actions |
| Partial-payment ledger | Track multiple receipts per invoice; outstanding and forecast values update correctly |
| Optional Plaid Link | Encrypted server-side bank tokens, manual incremental transaction sync; requires your own Plaid credentials |
| Deployment Blueprint | Render-ready HTTPS public demo configuration with persistent disk and signup disabled |

See **[FEATURES.md](FEATURES.md)** for the exact definitions of all 100 new signals. The count refers to individually implemented intelligence calculations, **not** 100 separate enterprise modules. Their values update from actual workspace data.

**No analytics trackers, external font requests, or LLM calls.** The core UI works from the Python server; *only if you choose Connect a bank* does it load Plaid's external Link SDK. No bank API is contacted during ordinary CSV imports or forecasting.

## Run locally

Prerequisites: Python 3.11+.

```bash
git clone https://github.com/samertall/floatwise.git
cd floatwise
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**. API documentation is at **http://127.0.0.1:8000/docs**. Anonymous visitors see synthetic demo data in read-only mode; select **Sign in → Create account** to get an empty, private workspace. Passwords must be at least 12 characters.

On first start, synthetic invoices populate an empty demo database. Every registered account gets a separate `data/workspaces/<user-id>.sqlite3` database, while account records live in `data/accounts.sqlite3`. All are ignored by Git. Set `FLOATWISE_AUTH_MODE=off` to restore the V1/V2 unrestricted local-only development mode, or `FLOATWISE_AUTH_MODE=required` to require sign-in even for reads. Set `FLOATWISE_DEMO=0` to disable sample-data seeding.

Or run with Docker:

```bash
docker build -t floatwise .
docker run --rm -p 127.0.0.1:8000:8000 -v floatwise-data:/code/data floatwise
```

The bind address above is deliberately local-only. The app now has local account isolation, but **do not use it for real customer banking data in a public production deployment** without independent security assessment, database hardening, operational backup/restore, email verification, MFA, and compliance review.

### Connect real bank data (optional)

The app supports bank statement imports immediately; importing a file **never contacts a bank**. For the optional [Plaid Transactions API](https://plaid.com/docs/transactions/add-to-app/) connector:

1. Create your own Plaid account with the Transactions product enabled and obtain a client ID and secret. Coverage depends on [supported countries and institutions](https://plaid.com/global/).
2. Configure the environment variables from [`.env.example`](.env.example): `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`, `PLAID_TOKEN_ENCRYPTION_KEY`, and country codes. Generate a **stable, secret Fernet encryption key** using the command in that file. Preserve this key securely; rotating it without re-encryption makes stored bank tokens unreadable.
3. Sign in to a private workspace. Open **Banking & matching → Connect a bank**, complete Plaid Link, then press **Sync**. Plaid's access token stays encrypted server-side, never in browser storage. Synced transactions enter the unreviewed queue and **do not automatically affect invoices or the cash book**.
4. Review each transaction, select a suggested matching invoice, and explicitly confirm reconciliation. Amount and currency must be compatible with the invoice. Pending items are not imported until posted by the provider. Syncs are manual (no webhook processor yet).

Plaid uses its own fees and activation requirements; sandbox credentials only connect to simulated institutions. This repository does not include Plaid credentials, real bank access, or a live account. QuickBooks and Xero integrations currently use **export-file adapters**, not OAuth API sync.

### Public demo deployment (ready to configure)

[`render.yaml`](render.yaml) defines a public **read-only** demo: authentication enabled, signups disabled, HTTPS-only cookies, a health check, and a persistent SQLite volume. To activate it, connect this GitHub repository to a [Render Blueprint](https://render.com/docs/infrastructure-as-code), review the configuration and charges, and deploy. Render provides the public URL after deployment—**GitHub upload alone does not host the Python API**.

**Cost note:** Render persistent disks require a paid service, and disk-attached instances cannot horizontally scale or perform zero-downtime redeploys. Do not set up this deployment with actual user financial data; for real multi-tenant operation, migrate to a managed database and production identity stack. If you want an invitation-only private pilot, change `FLOATWISE_ALLOW_SIGNUP=1` temporarily for onboarding, then disable it; configure backups and access controls first.

## API walkthrough

```bash
# Demo health
curl http://127.0.0.1:8000/api/health

# Summary, collection priorities, insights, and 90-day forecast
curl http://127.0.0.1:8000/api/dashboard

# Add an invoice (requires authentication and an X-CSRF-Token from /api/auth/me
# in default demo mode, or set FLOATWISE_AUTH_MODE=off for local-only API testing)
curl -X POST http://127.0.0.1:8000/api/invoices \
  -H 'Content-Type: application/json' \
  -d '{"invoice_number":"INV-1001","customer":"Northstar","amount":"2450.00","issued_on":"2026-11-09","due_on":"2026-12-09","notes":"Design engagement"}'

# Import (required CSV columns: invoice_number,customer,amount,issued_on,due_on)
curl -X POST http://127.0.0.1:8000/api/import \
  -H 'Content-Type: text/csv' --data-binary @examples/invoices.csv

# Export invoices
curl -o invoices.csv http://127.0.0.1:8000/api/export

# Adjust assumptions
curl -X PATCH http://127.0.0.1:8000/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"opening_balance":"68000.00","monthly_expenses":"18500.00"}'

# Explore 100 computed signals and underlying finance records
curl http://127.0.0.1:8000/api/v2/features
curl http://127.0.0.1:8000/api/v2/workspace

# Create a manual expense entry (for budgets and cash signals)
curl -X POST http://127.0.0.1:8000/api/v2/cash \
  -H 'Content-Type: application/json' \
  -d '{"title":"Office rent","kind":"expense","amount":"900.00","occurs_on":"2026-11-09","category":"Facilities"}'

# Create a budget category
curl -X POST http://127.0.0.1:8000/api/v2/budgets \
  -H 'Content-Type: application/json' \
  -d '{"category":"Facilities","monthly_limit":"1200.00"}'

# More planning and reporting
curl 'http://127.0.0.1:8000/api/v2/forecast?days=180'
curl 'http://127.0.0.1:8000/api/v2/reports/features?format=csv' -o signals.csv
curl http://127.0.0.1:8000/api/v2/backup -o backup.json

# V3: supported statement formats and bank-connection status
curl http://127.0.0.1:8000/api/v3/import/formats
curl http://127.0.0.1:8000/api/v3/plaid/status

# Staged bank import (authentication + CSRF required in default mode)
curl -X POST http://127.0.0.1:8000/api/v3/import/bank_csv \
  -H 'Content-Type: text/csv' --data-binary @examples/bank-statement.csv
```

## How the forecast works

**No black box:** Floatwise applies a deterministic, auditable model to the current invoice book.

1. For each customer, compute the median number of days early or late on *paid* invoices, clamped to a -10 to +45 day range. If no history exists, start with a five-day delay.
2. Shift each unpaid invoice's due date by its customer's historical median and the scenario adjustment. Overdue invoices receive extra follow-up time.
3. Apply collection realization percentages and add the **weighted invoice value** on the estimated receipt date.
4. Subtract operating costs evenly at `monthly_expenses / 30` per day, beginning from opening cash.
5. Return a daily 90-day series, low balance, end balance, and first negative-cash date for each scenario.

| Assumption | Best case | Expected | Stress test |
| --- | ---: | ---: | ---: |
| Additional collection delay | -5 days | 0 days | +18 days |
| Invoice not overdue: modeled collection | 100% | 92% | 68% |
| Overdue invoice: modeled collection | 90% | 70% | 38% |

The weights are **illustrative product assumptions**, not empirically calibrated probabilities. They should be replaced with historical cohort estimates and backtesting before making operational or financial decisions. The amount-weighted receipts are planning estimates, not booked revenue or actual deposits.

**Risk scoring** considers days overdue, a high-invoice-amount threshold, near-term due dates, and previous customer lateness. Resulting priority labels are heuristics to help staff triage follow-ups, not a creditworthiness assessment.

## Project structure

```text
floatwise/
├── app/
│   ├── analytics.py          # Pure deterministic projections and priorities
│   ├── database.py           # SQLite schema and transaction boundaries
│   ├── demo.py               # Synthetic customer invoices
│   ├── feature_lab.py        # Exactly 100 executable intelligence formulas
│   ├── main.py               # FastAPI endpoints and validation
│   ├── operations.py         # Cash, budgets, tasks, customer, views, activity
│   ├── banking.py            # Statement adapters, partial-payment ledger, reconciliation
│   ├── plaid.py              # Optional encrypted Plaid Link and manual transaction sync
│   ├── security.py           # Account sessions, password hashing, private workspace scoping
│   └── static/
│       ├── index.html        # Responsive, accessible product interface
│       ├── styles.css        # Design tokens and layout
│       └── app.js            # UI state, API calls, SVG data visualization
│       ├── lab.css           # Intelligence and operations interface
│       ├── lab.js            # Forms, reports, and 100-signal UI
│       ├── auth.js/css       # Session-aware access and login UI
│       └── banking.js/css    # Statement review and Plaid Link UI
├── examples/invoices.csv     # Example import
├── examples/bank-statement.csv # Example bank statement import
├── scripts/                   # Generate/check 100-signal feature catalog
├── tests/                   # Analytic and HTTP regression tests
├── FEATURES.md               # Exactly 100 defined, computed indicators
├── .github/workflows/ci.yml  # Automated CI
├── Dockerfile
├── render.yaml               # Public read-only demo deployment blueprint
├── .env.example              # Local environment-variable reference
└── pyproject.toml
```

## Test

```bash
python -m pytest -q
python -m compileall -q app
python -m scripts.generate_feature_catalog --check
node --check app/static/app.js
node --check app/static/lab.js
node --check app/static/auth.js
node --check app/static/banking.js
```

Tests cover scenario ordering, empty-cash-burn forecasting, overdue risk, exact-cent invoice amounts, API mutations, date validation, CSV import/export, rollback on duplicates, the 100-feature registry, resource CRUD, budget variance, activity history, backup, and safe reminder previews. V3 adds authentication and tenant-isolation tests, CSRF protection, staged import idempotency, invoice matching, partial payments, QIF/OFX/camt.053 parsing, optional Plaid token encryption, and mocked incremental bank syncs.

## Privacy and security

- **Account-isolated local workspaces.** Passwords use per-user salted scrypt hashes. Session cookies are HttpOnly and SameSite=strict, with CSRF tokens for mutations. Separate workspace database files provide isolation for this single-process deployment. This is **not a replacement** for a thoroughly reviewed production identity, authorization, and data-protection architecture.
- The public demo is read-only and seeded with synthetic data. Account creation can be disabled using `FLOATWISE_ALLOW_SIGNUP=0`. For HTTPS deployment enable `FLOATWISE_COOKIE_SECURE=1`.
- Data is stored in SQLite locally; no analytics service, telemetry, or AI API is configured. Optional Plaid sync only runs when the operator explicitly connects and triggers it, with account-specific access tokens encrypted at rest.
- Imported bank movements are **never posted or reconciled automatically**. Matching is heuristic and must be confirmed manually. The opening cash baseline is not a computed bank balance.
- Demo customer names and invoices are entirely synthetic. Do not import sensitive information into a shared environment.
- SQL uses parameterized statements; API inputs are validated; browser-rendered customer text is escaped; exported text is protected against common spreadsheet formula-prefix injection.
- Invoice CSV uploads are limited to 1 MB and 250 records; bank/accounting statement uploads are limited to 2 MB and 500 entries. Parser errors roll back, and unique transaction identifiers make repeat imports idempotent.
- Operations changes are written to a lightweight activity timeline. This is not a tamper-proof regulated audit log.
- This software provides **illustrative financial planning** only. It is not investment, accounting, lending, or financial advice.
- Security limitations for production: no MFA, email verification, account recovery, server-side session revocation across multiple workers, distributed rate limiter, monitored alerting, immutable audit trails, or automated disaster recovery. Keep protected data off an unreviewed public deployment.

## Production roadmap

1. **Production identity:** OAuth/SSO, MFA, email verification, password recovery, roles and permissions, centralized sessions, formal security and privacy assessment.
2. **Reliable finance data:** Double-entry transaction model, validated accounting API OAuth sync, multi-currency conversion, reconciliation reversals, expenses schedules, actual versus forecast.
3. **Better predictions:** Historical backtesting, customer cohort calibration, holidays and seasonality, uncertainty intervals, explainability reports.
4. **Workflow automation:** Reminder templates, email integrations, collection notes and approvals, full invoice lifecycle.
5. **Enterprise readiness:** PostgreSQL migrations, observability, queue workers, backup/restore, regulatory/privacy review, accessibility testing.

## Suggested success measures (targets to validate, not proven results)

- Median time to identify top overdue accounts.
- Weekly active finance operators / month.
- Reduction in manual follow-up effort.
- Change in days sales outstanding (DSO) in a pilot cohort.
- Forecast error against actual bank cash using a consistent holdout period.

## License

MIT © 2026 [Samer Tallauze](https://samertall.com).
