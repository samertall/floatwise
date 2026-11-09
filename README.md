# Floatwise

**Know what's coming.** An open-source receivables intelligence and cash-flow planning platform for small businesses.

> A Python FastAPI + SQLite product concept with a responsive analytics dashboard, explainable 90-day forecasting, invoice management, CSV import/export, and automated tests.

**Product concept and implementation by [Samer Tallauze](https://samertall.com).**

## Why this product?

Late payments and unpredictable cash flow cause real operational friction. In the [2026 QuickBooks Small Business Late Payments Report](https://quickbooks.intuit.com/r/small-business-data/small-business-late-payments-report-2026/), 51% of surveyed small businesses with overdue invoices reported cash-flow problems, versus 36% without overdue invoices. The [Federal Reserve's report on business payments](https://www.fedsmallbusiness.org/survey/2024-report-on-payments) also documents widespread payments-related challenges.

Floatwise explores an accessible, lightweight approach to **cash visibility before cash stress**. It is designed for owners, finance leads, and agencies who need answers to three questions:

1. How much should we collect, and from whom?
2. Which unpaid invoices deserve attention first?
3. What happens to our cash if customers pay later than expected?

This repository is a *working single-workspace MVP and engineering showcase*, not a hosted banking product or a validated business outcome.

## Features

| Product capability | What it does |
| --- | --- |
| Cash-flow command center | Outstanding, overdue, due soon, and collection-rate metrics |
| Scenario forecast | 90-day optimistic, baseline, and stress projections |
| Explainable collections | Risk scores derived from overdue age, amount, and prior payment behavior |
| Next best action | Collection recommendations with no external AI dependency |
| Receivables workspace | Create, list, search, filter, mark paid, and reverse payments |
| CSV workflow | Transactional import (250 rows/file) and Excel-safer export |
| Adjustable assumptions | Opening cash and operating expenses update all forecasts |
| Developer API | OpenAPI documentation at `/docs` and `/openapi.json` |
| Demo-friendly | Synthetic invoices are added to an empty demo database |
| Tested and containerized | Pytest, GitHub Actions, Docker, API health endpoint |

**No third-party JavaScript, external font requests, analytics trackers, bank integrations, or LLM calls.** The UI works from the same Python server.

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

Open **http://127.0.0.1:8000**. API documentation is at **http://127.0.0.1:8000/docs**.

On first start, synthetic sample invoices populate an empty database. To begin with a blank workspace, set `FLOATWISE_DEMO=0` before launching. Persistent local data is stored in `data/floatwise.sqlite3`, which is excluded from Git.

Or run with Docker:

```bash
docker build -t floatwise .
docker run --rm -p 127.0.0.1:8000:8000 -v floatwise-data:/code/data floatwise
```

The bind address above is deliberately local-only. **Do not expose this MVP publicly:** it does not include authentication or multi-tenant data isolation.

## API walkthrough

```bash
# Demo health
curl http://127.0.0.1:8000/api/health

# Summary, collection priorities, insights, and 90-day forecast
curl http://127.0.0.1:8000/api/dashboard

# Add an invoice
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
│   ├── main.py               # FastAPI endpoints and validation
│   └── static/
│       ├── index.html        # Responsive, accessible product interface
│       ├── styles.css        # Design tokens and layout
│       └── app.js            # UI state, API calls, SVG data visualization
├── examples/invoices.csv     # Example import
├── tests/                   # Analytic and HTTP regression tests
├── .github/workflows/ci.yml  # Automated CI
├── Dockerfile
└── pyproject.toml
```

## Test

```bash
python -m pytest -q
python -m compileall -q app
```

Tests cover scenario ordering, empty-cash-burn forecasting, overdue risk, exact-cent invoice amounts, API mutations, date validation, CSV import/export, and batch rollback on duplicate invoice numbers.

## Privacy and security

- **Single-workspace localhost application.** Anyone who can reach the HTTP server can read or change the database. There are no logins, permissions, or tenant boundaries. Keep it private.
- Data is stored in SQLite locally; no analytics service, telemetry, AI API, or bank feed is configured.
- Demo customer names and invoices are entirely synthetic. Do not import sensitive information into a shared environment.
- SQL uses parameterized statements; API inputs are validated; browser-rendered customer text is escaped; exported text is protected against common spreadsheet formula-prefix injection.
- CSV uploads are limited to 1 MB and 250 records, and transaction rollbacks prevent partial data on duplicates.
- This software provides **illustrative financial planning** only. It is not investment, accounting, lending, or financial advice.

## Production roadmap

1. **Security foundation:** OAuth/SSO, role-based access, tenant isolation, secrets management, audit logs, API rate limiting, CSRF/origin policy, secure deployments.
2. **Reliable finance data:** Double-entry transaction model, ledger integration, currency handling, reconciliation, expenses schedules, actual versus forecast.
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
