# Floatwise V2: 100 Live Intelligence Signals

These are **100 individually defined, executable calculations**, grouped into ten product areas. They are not 100 separate enterprise software modules. Each appears in the Intelligence Lab UI and is available from `GET /api/v2/features` with its ID, group, display type, definition, and live value.

Calculations are transparent heuristics or deterministic aggregates. Some require the user to enter cash events, budgets, tasks, or customer profiles before they display nonzero values.

| Group | Signals |
| --- | ---: |
| Receivables | 10 |
| Customers | 10 |
| Payments | 10 |
| Collections | 10 |
| Cash | 10 |
| Budgets | 10 |
| Forecast | 10 |
| Risk | 10 |
| Operations | 10 |
| Health | 10 |
| **Total** | **100** |

## 01. Receivables

| ID | Feature | What it measures |
| --- | --- | --- |
| `ar.unpaid` | Unpaid invoices | Number of invoices awaiting settlement. |
| `ar.balance` | Unpaid invoice balance | Total amount invoiced but not yet paid. |
| `ar.average` | Average unpaid invoice | Mean open invoice value. |
| `ar.median` | Median unpaid invoice | Middle open invoice amount; less sensitive to outliers. |
| `ar.largest` | Largest unpaid invoice | Single largest open receivable. |
| `ar.smallest` | Smallest unpaid invoice | Smallest open receivable. |
| `ar.today` | Due today | Unpaid invoices reaching their due date today. |
| `ar.week` | Due in next 7 days | Upcoming unpaid invoices including today. |
| `ar.month` | Due in next 30 days | Receivables due within 30 days. |
| `ar.later` | Due beyond 30 days | Longer-dated open invoice balance. |

## 02. Customers

| ID | Feature | What it measures |
| --- | --- | --- |
| `customers.distinct` | Invoiced customers | Unique customers in invoice history. |
| `customers.active` | Customers with open balances | Unique customer accounts with unpaid invoices. |
| `customers.repeat` | Repeat customers | Customers appearing on two or more invoices. |
| `customers.payers` | Customers who paid | Customers with at least one paid invoice. |
| `customers.peak` | Largest customer exposure | Maximum outstanding balance for one customer. |
| `customers.top3` | Top-three exposure share | Share of outstanding balance held by the three largest customers. |
| `customers.average_balance` | Average open balance per customer | Outstanding amount divided by customers with an open balance. |
| `customers.invoice_depth` | Invoices per customer | Average invoice relationships per customer. |
| `customers.payer_share` | Customer payment coverage | Share of invoiced customers who have made a payment. |
| `customers.profiles` | Enriched customer profiles | Customers with manually managed profiles and terms. |

## 03. Payments

| ID | Feature | What it measures |
| --- | --- | --- |
| `payments.count` | Invoices paid | Number of invoices with a payment date. |
| `payments.value` | Paid invoice value | Recorded paid invoice amount. |
| `payments.week_count` | Paid in last 7 days | Invoices marked paid in the last week. |
| `payments.week_value` | Week received value | Paid invoice value in the last seven days. |
| `payments.month_count` | Paid in last 30 days | Invoices settled over the previous thirty days. |
| `payments.month_value` | Month received value | Paid invoice value over the previous thirty days. |
| `payments.on_time` | On-time payment rate | Share of settled invoices paid no later than the due date. |
| `payments.mean_late` | Mean days past due when paid | Average positive days late for completed invoices. |
| `payments.median_late` | Median days past due when paid | Median positive settlement delay. |
| `payments.largest` | Largest settled invoice | Largest invoice marked as paid. |

## 04. Collections

| ID | Feature | What it measures |
| --- | --- | --- |
| `collections.overdue_count` | Overdue invoices | Open invoices past their due date. |
| `collections.overdue_value` | Overdue receivables | Open balance already past due. |
| `collections.age_1_7` | 1–7 days overdue | Recently overdue invoice balance. |
| `collections.age_8_30` | 8–30 days overdue | Early-stage past-due invoice balance. |
| `collections.age_31_60` | 31–60 days overdue | Mid-stage past-due invoice balance. |
| `collections.age_61_90` | 61–90 days overdue | Late-stage past-due invoice balance. |
| `collections.age_90plus` | Over 90 days overdue | Severely aged receivables. |
| `collections.avg_age` | Average overdue age | Average number of days late on overdue open invoices. |
| `collections.max_age` | Oldest unpaid age | Longest overdue time of an unpaid invoice. |
| `collections.task_queue` | Outstanding collection tasks | Open collection follow-ups in the task workspace. |

## 05. Cash

| ID | Feature | What it measures |
| --- | --- | --- |
| `cash.in_count` | Cash inflow entries | Number of manually entered incoming transactions. |
| `cash.in_total` | Recorded cash inflows | Total entered income movements. |
| `cash.out_count` | Cash outflow entries | Number of manually entered expense movements. |
| `cash.out_total` | Recorded cash outflows | Total entered expense movements. |
| `cash.net` | Net recorded cash movements | Inflow minus outflow in manual cash events. |
| `cash.adjusted_balance` | Opening cash plus movements | Opening cash adjusted by entered movements dated today or earlier. |
| `cash.avg_expense` | Average cash expense entry | Mean amount per expense event. |
| `cash.biggest_outflow` | Largest cash outflow | Highest expense event amount. |
| `cash.category_count` | Expense categories in use | Distinct categories represented in expense events. |
| `cash.week_events` | Cash movements in last 7 days | Recent incoming and outgoing event count. |

## 06. Budgets

| ID | Feature | What it measures |
| --- | --- | --- |
| `budgets.categories` | Budgeted categories | Categories with an approved monthly spending target. |
| `budgets.total_limit` | Combined monthly budget | Sum of category-level spending limits. |
| `budgets.month_spend` | Recorded spending this month | Expense entries dated in the current calendar month. |
| `budgets.remaining` | Budget less recorded spending | Total category budgets less recorded month-to-date spending. |
| `budgets.utilization` | Monthly budget utilization | Recorded spending divided by total category budgets. |
| `budgets.overspent_count` | Categories over budget | Budget categories with month-to-date spending above the limit. |
| `budgets.on_track` | Categories within budget | Budget categories currently at or below their limits. |
| `budgets.largest_limit` | Largest category budget | Highest individual category monthly spending limit. |
| `budgets.largest_overage` | Largest category overage | Largest absolute budget overrun among tracked categories. |
| `budgets.unallocated` | Expenses without a category budget | Current-month expenses with no corresponding category limit. |

## 07. Forecast

| ID | Feature | What it measures |
| --- | --- | --- |
| `forecast.base_30` | Expected balance · day 30 | Expected scenario 30-day projected cash. |
| `forecast.base_60` | Expected balance · day 60 | Expected scenario 60-day projected cash. |
| `forecast.base_90` | Expected balance · day 90 | Expected scenario 90-day projected cash. |
| `forecast.best_90` | Best-case balance · day 90 | Optimistic 90-day projected cash. |
| `forecast.stress_90` | Stress-case balance · day 90 | Stress 90-day projected cash. |
| `forecast.base_low` | Expected low point | Minimum expected projected cash across 90 days. |
| `forecast.stress_low` | Stress low point | Lowest modeled stress-case cash balance. |
| `forecast.base_gap` | Days until expected cash gap | Days to first negative expected cash, or zero if none. |
| `forecast.stress_gap` | Days until stress-case cash gap | Days to first negative stressed cash, or zero if none. |
| `forecast.spread` | Scenario balance spread | Optimistic minus stressed cash position on day 90. |

## 08. Risk

| ID | Feature | What it measures |
| --- | --- | --- |
| `risk.critical` | Critical-risk invoices | Open invoices with heuristic score of 70 or more. |
| `risk.high` | High-risk invoices | Open invoices with heuristic score between 45 and 69. |
| `risk.watch` | Watch-list invoices | Open invoices with heuristic score below 45. |
| `risk.mean_score` | Average open-invoice risk score | Mean of the explainable heuristic risk scores. |
| `risk.peak_score` | Highest invoice risk score | Maximum heuristic risk score among open invoices. |
| `risk.large_exposure` | High-value invoices (≥ $5k) | Open balances of five thousand dollars or more. |
| `risk.top_customer` | Largest customer share | Share of total open receivables owed by the largest customer. |
| `risk.worst_lateness` | Worst historic customer lateness | Maximum median days late across customers with paid invoices. |
| `risk.aged_exposure` | Overdue more than 30 days | Open receivables past due by over thirty days. |
| `risk.stress_shortfall` | Stress-case maximum shortfall | Magnitude of negative stress-case low balance, if any. |

## 09. Operations

| ID | Feature | What it measures |
| --- | --- | --- |
| `ops.open_tasks` | Open work tasks | Tasks still requiring action. |
| `ops.completed_tasks` | Completed tasks | Tasks marked done. |
| `ops.high_tasks` | High-priority open tasks | Open tasks explicitly marked high priority. |
| `ops.overdue_tasks` | Past-due work tasks | Open tasks with due dates before today. |
| `ops.today_tasks` | Tasks due today | Open tasks with deadlines today. |
| `ops.week_tasks` | Tasks due within 7 days | Open tasks with deadlines from today to seven days ahead. |
| `ops.collection_tasks` | Total collection tasks | All tasks classified as collection work. |
| `ops.expense_tasks` | Expense-review tasks | All tasks classified as expense work. |
| `ops.customer_profiles` | Managed customer profiles | Customer profiles with relationship metadata. |
| `ops.saved_views` | Saved search views | Saved filter presets for operational work. |

## 10. Health

| ID | Feature | What it measures |
| --- | --- | --- |
| `health.cash_week` | Net cash events · 7 days | Manual inflows less outflows recorded in the last seven days. |
| `health.cash_month` | Net cash events · 30 days | Manual inflows less outflows recorded in the last thirty days. |
| `health.invoice_ticket` | Average invoiced ticket | Mean amount of all invoices, paid or unpaid. |
| `health.daily_burn` | Modeled daily operating burn | Monthly expense baseline divided by thirty days. |
| `health.cash_coverage` | Opening cash coverage | Days of modeled operating costs covered by opening balance, excluding receipts. |
| `health.collection_rate` | Invoice settlement rate | Paid invoices as a share of all created invoices. |
| `health.overdue_ratio` | Overdue share of open balance | Percent of all outstanding receivables past due. |
| `health.paid_to_open` | Paid value relative to open value | Settled value divided by current unpaid value. |
| `health.paid_invoice_share` | Settled share of invoiced value | Paid invoice value divided by total invoiced value. |
| `health.task_completion` | Task completion rate | Completed work tasks divided by all work tasks. |

## Operational functionality beyond the 100 signals

- Create, edit, list, and delete cash income/expense entries.
- Maintain monthly category budgets and monitor overspending.
- Manage follow-up tasks with status, priority, owner, and deadline.
- Maintain customer profiles with email, segment, and payment terms.
- Save and apply search views for invoices, tasks, and cash events.
- Review an activity timeline, preview collection reminder drafts, and export JSON backups.
- Export workspace reports as CSV or JSON and request 7–365 day forecast horizons.

**Scope:** single-workspace MVP with local SQLite storage. It is not authenticated, multi-tenant, bank-connected, or intended for public deployment without additional safeguards.
