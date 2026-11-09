"""One hundred real, data-driven finance intelligence signals.

Each feature has a unique ID, explanation, display type, and executable formula.
The formulas never depend on an external AI model or invent customer data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, median
from typing import Callable

from app import analytics


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    kind: str
    description: str
    evaluate: Callable[[dict], object]


def money(items: list[dict], key: str = 'amount_cents') -> int:
    return sum(i[key] for i in items)


def avg(items: list[int]) -> int:
    return round(mean(items)) if items else 0


def med(items: list[int]) -> int:
    return round(median(items)) if items else 0


def pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def days(value: str, today: date) -> int:
    return (today - date.fromisoformat(value)).days


def safe_max(values: list[int]) -> int:
    return max(values, default=0)


def ctx_for(invoices: list[dict], resources: dict[str, list[dict]], settings: dict[str, int], today: date) -> dict:
    unpaid = [i for i in invoices if not i['paid_on']]
    paid = [i for i in invoices if i['paid_on']]
    overdue = [i for i in unpaid if i['due_on'] < today.isoformat()]
    customer_values: dict[str, int] = defaultdict(int)
    customer_counts: Counter = Counter()
    customer_paid: set[str] = set()
    for i in invoices:
        key = i['customer'].strip().casefold()
        customer_counts[key] += 1
        if not i['paid_on']:
            customer_values[key] += i['amount_cents']
        else:
            customer_paid.add(key)
    customer_late = analytics.customer_lateness(invoices)
    priorities = [analytics.collection_priority(i, today, customer_late) for i in unpaid]
    cash = resources['cash']
    income = [e for e in cash if e['kind'] == 'income']
    expenses = [e for e in cash if e['kind'] == 'expense']
    month = today.isoformat()[:7]
    month_expenses = [e for e in expenses if e['occurs_on'].startswith(month)]
    budget_limits = {b['category'].casefold(): b['monthly_limit_cents'] for b in resources['budgets']}
    spend_by_category: dict[str, int] = defaultdict(int)
    for e in month_expenses:
        spend_by_category[e['category'].casefold()] += e['amount_cents']
    overspent = {k: v - budget_limits[k] for k, v in spend_by_category.items() if k in budget_limits and v > budget_limits[k]}
    forecast = analytics.forecast(invoices, settings, today)['scenarios']
    return {
        'today': today, 'invoices': invoices, 'unpaid': unpaid, 'paid': paid, 'overdue': overdue,
        'customer_values': customer_values, 'customer_counts': customer_counts, 'customer_paid': customer_paid,
        'customer_late': customer_late, 'priorities': priorities,
        'cash': cash, 'income': income, 'expenses': expenses,
        'budgets': resources['budgets'], 'tasks': resources['tasks'], 'customers': resources['customers'],
        'views': resources['views'], 'month_expenses': month_expenses, 'spend_by_category': spend_by_category,
        'budget_limits': budget_limits, 'overspent': overspent, 'forecast': forecast, 'settings': settings,
    }


FEATURE_GROUPS: dict[str, list[Feature]] = {}


def feature(group: str, key: str, label: str, kind: str, description: str, fn: Callable[[dict], object]) -> None:
    FEATURE_GROUPS.setdefault(group, []).append(Feature(key, label, kind, description, fn))


# 01. Invoice portfolio — ten ways to understand current receivables.
feature('Receivables', 'ar.unpaid', 'Unpaid invoices', 'count', 'Number of invoices awaiting settlement.', lambda c:len(c['unpaid']))
feature('Receivables', 'ar.balance', 'Unpaid invoice balance', 'money', 'Total amount invoiced but not yet paid.', lambda c:money(c['unpaid']))
feature('Receivables', 'ar.average', 'Average unpaid invoice', 'money', 'Mean open invoice value.', lambda c:avg([i['amount_cents'] for i in c['unpaid']]))
feature('Receivables', 'ar.median', 'Median unpaid invoice', 'money', 'Middle open invoice amount; less sensitive to outliers.', lambda c:med([i['amount_cents'] for i in c['unpaid']]))
feature('Receivables', 'ar.largest', 'Largest unpaid invoice', 'money', 'Single largest open receivable.', lambda c:safe_max([i['amount_cents'] for i in c['unpaid']]))
feature('Receivables', 'ar.smallest', 'Smallest unpaid invoice', 'money', 'Smallest open receivable.', lambda c:min((i['amount_cents'] for i in c['unpaid']),default=0))
feature('Receivables', 'ar.today', 'Due today', 'count', 'Unpaid invoices reaching their due date today.', lambda c:sum(i['due_on']==c['today'].isoformat() for i in c['unpaid']))
feature('Receivables', 'ar.week', 'Due in next 7 days', 'count', 'Upcoming unpaid invoices including today.', lambda c:sum(0 <= -days(i['due_on'],c['today']) <= 7 for i in c['unpaid']))
feature('Receivables', 'ar.month', 'Due in next 30 days', 'money', 'Receivables due within 30 days.', lambda c:money([i for i in c['unpaid'] if 0 <= -days(i['due_on'],c['today']) <= 30]))
feature('Receivables', 'ar.later', 'Due beyond 30 days', 'money', 'Longer-dated open invoice balance.', lambda c:money([i for i in c['unpaid'] if -days(i['due_on'],c['today']) > 30]))

# 02. Customer intelligence — concentration, coverage and relationship depth.
feature('Customers', 'customers.distinct', 'Invoiced customers', 'count', 'Unique customers in invoice history.', lambda c:len(c['customer_counts']))
feature('Customers', 'customers.active', 'Customers with open balances', 'count', 'Unique customer accounts with unpaid invoices.', lambda c:sum(v>0 for v in c['customer_values'].values()))
feature('Customers', 'customers.repeat', 'Repeat customers', 'count', 'Customers appearing on two or more invoices.', lambda c:sum(n>=2 for n in c['customer_counts'].values()))
feature('Customers', 'customers.payers', 'Customers who paid', 'count', 'Customers with at least one paid invoice.', lambda c:len(c['customer_paid']))
feature('Customers', 'customers.peak', 'Largest customer exposure', 'money', 'Maximum outstanding balance for one customer.', lambda c:safe_max(list(c['customer_values'].values())))
feature('Customers', 'customers.top3', 'Top-three exposure share', 'percent', 'Share of outstanding balance held by the three largest customers.', lambda c:pct(sum(sorted(c['customer_values'].values(),reverse=True)[:3]),money(c['unpaid'])))
feature('Customers', 'customers.average_balance', 'Average open balance per customer', 'money', 'Outstanding amount divided by customers with an open balance.', lambda c:round(money(c['unpaid'])/sum(v>0 for v in c['customer_values'].values())) if any(c['customer_values'].values()) else 0)
feature('Customers', 'customers.invoice_depth', 'Invoices per customer', 'decimal', 'Average invoice relationships per customer.', lambda c:round(len(c['invoices'])/len(c['customer_counts']),1) if c['customer_counts'] else 0)
feature('Customers', 'customers.payer_share', 'Customer payment coverage', 'percent', 'Share of invoiced customers who have made a payment.', lambda c:pct(len(c['customer_paid']),len(c['customer_counts'])))
feature('Customers', 'customers.profiles', 'Enriched customer profiles', 'count', 'Customers with manually managed profiles and terms.', lambda c:len(c['customers']))

# 03. Recorded payments — timing and quality of historical settlement.
feature('Payments', 'payments.count', 'Invoices paid', 'count', 'Number of invoices with a payment date.', lambda c:len(c['paid']))
feature('Payments', 'payments.value', 'Paid invoice value', 'money', 'Recorded paid invoice amount.', lambda c:money(c['paid']))
feature('Payments', 'payments.week_count', 'Paid in last 7 days', 'count', 'Invoices marked paid in the last week.', lambda c:sum(0<=days(i['paid_on'],c['today'])<=7 for i in c['paid']))
feature('Payments', 'payments.week_value', 'Week received value', 'money', 'Paid invoice value in the last seven days.', lambda c:money([i for i in c['paid'] if 0<=days(i['paid_on'],c['today'])<=7]))
feature('Payments', 'payments.month_count', 'Paid in last 30 days', 'count', 'Invoices settled over the previous thirty days.', lambda c:sum(0<=days(i['paid_on'],c['today'])<=30 for i in c['paid']))
feature('Payments', 'payments.month_value', 'Month received value', 'money', 'Paid invoice value over the previous thirty days.', lambda c:money([i for i in c['paid'] if 0<=days(i['paid_on'],c['today'])<=30]))
feature('Payments', 'payments.on_time', 'On-time payment rate', 'percent', 'Share of settled invoices paid no later than the due date.', lambda c:pct(sum(i['paid_on']<=i['due_on'] for i in c['paid']),len(c['paid'])))
feature('Payments', 'payments.mean_late', 'Mean days past due when paid', 'days', 'Average positive days late for completed invoices.', lambda c:avg([max(0,(date.fromisoformat(i['paid_on'])-date.fromisoformat(i['due_on'])).days) for i in c['paid']]))
feature('Payments', 'payments.median_late', 'Median days past due when paid', 'days', 'Median positive settlement delay.', lambda c:med([max(0,(date.fromisoformat(i['paid_on'])-date.fromisoformat(i['due_on'])).days) for i in c['paid']]))
feature('Payments', 'payments.largest', 'Largest settled invoice', 'money', 'Largest invoice marked as paid.', lambda c:safe_max([i['amount_cents'] for i in c['paid']]))

# 04. Collections — aging buckets and follow-up workload.
feature('Collections', 'collections.overdue_count', 'Overdue invoices', 'count', 'Open invoices past their due date.', lambda c:len(c['overdue']))
feature('Collections', 'collections.overdue_value', 'Overdue receivables', 'money', 'Open balance already past due.', lambda c:money(c['overdue']))
feature('Collections', 'collections.age_1_7', '1–7 days overdue', 'money', 'Recently overdue invoice balance.', lambda c:money([i for i in c['overdue'] if 1<=days(i['due_on'],c['today'])<=7]))
feature('Collections', 'collections.age_8_30', '8–30 days overdue', 'money', 'Early-stage past-due invoice balance.', lambda c:money([i for i in c['overdue'] if 8<=days(i['due_on'],c['today'])<=30]))
feature('Collections', 'collections.age_31_60', '31–60 days overdue', 'money', 'Mid-stage past-due invoice balance.', lambda c:money([i for i in c['overdue'] if 31<=days(i['due_on'],c['today'])<=60]))
feature('Collections', 'collections.age_61_90', '61–90 days overdue', 'money', 'Late-stage past-due invoice balance.', lambda c:money([i for i in c['overdue'] if 61<=days(i['due_on'],c['today'])<=90]))
feature('Collections', 'collections.age_90plus', 'Over 90 days overdue', 'money', 'Severely aged receivables.', lambda c:money([i for i in c['overdue'] if days(i['due_on'],c['today'])>90]))
feature('Collections', 'collections.avg_age', 'Average overdue age', 'days', 'Average number of days late on overdue open invoices.', lambda c:avg([days(i['due_on'],c['today']) for i in c['overdue']]))
feature('Collections', 'collections.max_age', 'Oldest unpaid age', 'days', 'Longest overdue time of an unpaid invoice.', lambda c:safe_max([days(i['due_on'],c['today']) for i in c['overdue']]))
feature('Collections', 'collections.task_queue', 'Outstanding collection tasks', 'count', 'Open collection follow-ups in the task workspace.', lambda c:sum(t['category']=='collection' and t['status']=='open' for t in c['tasks']))

# 05. Cash events — entered cash movements, not linked bank deposits.
feature('Cash', 'cash.in_count', 'Cash inflow entries', 'count', 'Number of manually entered incoming transactions.', lambda c:len(c['income']))
feature('Cash', 'cash.in_total', 'Recorded cash inflows', 'money', 'Total entered income movements.', lambda c:money(c['income']))
feature('Cash', 'cash.out_count', 'Cash outflow entries', 'count', 'Number of manually entered expense movements.', lambda c:len(c['expenses']))
feature('Cash', 'cash.out_total', 'Recorded cash outflows', 'money', 'Total entered expense movements.', lambda c:money(c['expenses']))
feature('Cash', 'cash.net', 'Net recorded cash movements', 'money', 'Inflow minus outflow in manual cash events.', lambda c:money(c['income'])-money(c['expenses']))
feature('Cash', 'cash.adjusted_balance', 'Opening cash plus movements', 'money', 'Opening cash adjusted by entered movements dated today or earlier.', lambda c:c['settings']['opening_balance_cents']+sum(e['amount_cents']*(1 if e['kind']=='income' else -1) for e in c['cash'] if e['occurs_on']<=c['today'].isoformat()))
feature('Cash', 'cash.avg_expense', 'Average cash expense entry', 'money', 'Mean amount per expense event.', lambda c:avg([e['amount_cents'] for e in c['expenses']]))
feature('Cash', 'cash.biggest_outflow', 'Largest cash outflow', 'money', 'Highest expense event amount.', lambda c:safe_max([e['amount_cents'] for e in c['expenses']]))
feature('Cash', 'cash.category_count', 'Expense categories in use', 'count', 'Distinct categories represented in expense events.', lambda c:len({e['category'].casefold() for e in c['expenses']}))
feature('Cash', 'cash.week_events', 'Cash movements in last 7 days', 'count', 'Recent incoming and outgoing event count.', lambda c:sum(0<=days(e['occurs_on'],c['today'])<=7 for e in c['cash']))

# 06. Budgets — current-month category planning and variance.
feature('Budgets', 'budgets.categories', 'Budgeted categories', 'count', 'Categories with an approved monthly spending target.', lambda c:len(c['budgets']))
feature('Budgets', 'budgets.total_limit', 'Combined monthly budget', 'money', 'Sum of category-level spending limits.', lambda c:money(c['budgets'],'monthly_limit_cents'))
feature('Budgets', 'budgets.month_spend', 'Recorded spending this month', 'money', 'Expense entries dated in the current calendar month.', lambda c:money(c['month_expenses']))
feature('Budgets', 'budgets.remaining', 'Budget less recorded spending', 'money', 'Total category budgets less recorded month-to-date spending.', lambda c:money(c['budgets'],'monthly_limit_cents')-money(c['month_expenses']))
feature('Budgets', 'budgets.utilization', 'Monthly budget utilization', 'percent', 'Recorded spending divided by total category budgets.', lambda c:pct(money(c['month_expenses']),money(c['budgets'],'monthly_limit_cents')))
feature('Budgets', 'budgets.overspent_count', 'Categories over budget', 'count', 'Budget categories with month-to-date spending above the limit.', lambda c:len(c['overspent']))
feature('Budgets', 'budgets.on_track', 'Categories within budget', 'count', 'Budget categories currently at or below their limits.', lambda c:sum(c['spend_by_category'].get(k,0)<=v for k,v in c['budget_limits'].items()))
feature('Budgets', 'budgets.largest_limit', 'Largest category budget', 'money', 'Highest individual category monthly spending limit.', lambda c:safe_max(list(c['budget_limits'].values())))
feature('Budgets', 'budgets.largest_overage', 'Largest category overage', 'money', 'Largest absolute budget overrun among tracked categories.', lambda c:safe_max(list(c['overspent'].values())))
feature('Budgets', 'budgets.unallocated', 'Expenses without a category budget', 'money', 'Current-month expenses with no corresponding category limit.', lambda c:sum(v for k,v in c['spend_by_category'].items() if k not in c['budget_limits']))

# 07. Forecast — scenario levels, gap timing, and scenario spread.
feature('Forecast', 'forecast.base_30', 'Expected balance · day 30', 'money', 'Expected scenario 30-day projected cash.', lambda c:c['forecast']['base']['points'][30]['balance_cents'])
feature('Forecast', 'forecast.base_60', 'Expected balance · day 60', 'money', 'Expected scenario 60-day projected cash.', lambda c:c['forecast']['base']['points'][60]['balance_cents'])
feature('Forecast', 'forecast.base_90', 'Expected balance · day 90', 'money', 'Expected scenario 90-day projected cash.', lambda c:c['forecast']['base']['end_balance_cents'])
feature('Forecast', 'forecast.best_90', 'Best-case balance · day 90', 'money', 'Optimistic 90-day projected cash.', lambda c:c['forecast']['optimistic']['end_balance_cents'])
feature('Forecast', 'forecast.stress_90', 'Stress-case balance · day 90', 'money', 'Stress 90-day projected cash.', lambda c:c['forecast']['stress']['end_balance_cents'])
feature('Forecast', 'forecast.base_low', 'Expected low point', 'money', 'Minimum expected projected cash across 90 days.', lambda c:c['forecast']['base']['low_balance_cents'])
feature('Forecast', 'forecast.stress_low', 'Stress low point', 'money', 'Lowest modeled stress-case cash balance.', lambda c:c['forecast']['stress']['low_balance_cents'])
feature('Forecast', 'forecast.base_gap', 'Days until expected cash gap', 'days', 'Days to first negative expected cash, or zero if none.', lambda c:(date.fromisoformat(c['forecast']['base']['cash_gap_date'])-c['today']).days if c['forecast']['base']['cash_gap_date'] else 0)
feature('Forecast', 'forecast.stress_gap', 'Days until stress-case cash gap', 'days', 'Days to first negative stressed cash, or zero if none.', lambda c:(date.fromisoformat(c['forecast']['stress']['cash_gap_date'])-c['today']).days if c['forecast']['stress']['cash_gap_date'] else 0)
feature('Forecast', 'forecast.spread', 'Scenario balance spread', 'money', 'Optimistic minus stressed cash position on day 90.', lambda c:c['forecast']['optimistic']['end_balance_cents']-c['forecast']['stress']['end_balance_cents'])

# 08. Risk — exposure and heuristic warning signals.
feature('Risk', 'risk.critical', 'Critical-risk invoices', 'count', 'Open invoices with heuristic score of 70 or more.', lambda c:sum(i['risk_level']=='Critical' for i in c['priorities']))
feature('Risk', 'risk.high', 'High-risk invoices', 'count', 'Open invoices with heuristic score between 45 and 69.', lambda c:sum(i['risk_level']=='High' for i in c['priorities']))
feature('Risk', 'risk.watch', 'Watch-list invoices', 'count', 'Open invoices with heuristic score below 45.', lambda c:sum(i['risk_level']=='Watch' for i in c['priorities']))
feature('Risk', 'risk.mean_score', 'Average open-invoice risk score', 'decimal', 'Mean of the explainable heuristic risk scores.', lambda c:round(mean([i['risk_score'] for i in c['priorities']]),1) if c['priorities'] else 0)
feature('Risk', 'risk.peak_score', 'Highest invoice risk score', 'count', 'Maximum heuristic risk score among open invoices.', lambda c:safe_max([i['risk_score'] for i in c['priorities']]))
feature('Risk', 'risk.large_exposure', 'High-value invoices (≥ $5k)', 'count', 'Open invoices of five thousand dollars or more.', lambda c:sum(i['amount_cents']>=500_000 for i in c['unpaid']))
feature('Risk', 'risk.top_customer', 'Largest customer share', 'percent', 'Share of total open receivables owed by the largest customer.', lambda c:pct(safe_max(list(c['customer_values'].values())),money(c['unpaid'])))
feature('Risk', 'risk.worst_lateness', 'Worst historic customer lateness', 'days', 'Maximum median days late across customers with paid invoices.', lambda c:safe_max(list(c['customer_late'].values())))
feature('Risk', 'risk.aged_exposure', 'Overdue more than 30 days', 'money', 'Open receivables past due by over thirty days.', lambda c:money([i for i in c['overdue'] if days(i['due_on'],c['today'])>30]))
feature('Risk', 'risk.stress_shortfall', 'Stress-case maximum shortfall', 'money', 'Magnitude of negative stress-case low balance, if any.', lambda c:max(0,-c['forecast']['stress']['low_balance_cents']))

# 09. Operations — the tasks, profiles, and saved views supporting finance teams.
feature('Operations', 'ops.open_tasks', 'Open work tasks', 'count', 'Tasks still requiring action.', lambda c:sum(t['status']=='open' for t in c['tasks']))
feature('Operations', 'ops.completed_tasks', 'Completed tasks', 'count', 'Tasks marked done.', lambda c:sum(t['status']=='done' for t in c['tasks']))
feature('Operations', 'ops.high_tasks', 'High-priority open tasks', 'count', 'Open tasks explicitly marked high priority.', lambda c:sum(t['status']=='open' and t['priority']=='high' for t in c['tasks']))
feature('Operations', 'ops.overdue_tasks', 'Past-due work tasks', 'count', 'Open tasks with due dates before today.', lambda c:sum(t['status']=='open' and t['due_on']<c['today'].isoformat() for t in c['tasks']))
feature('Operations', 'ops.today_tasks', 'Tasks due today', 'count', 'Open tasks with deadlines today.', lambda c:sum(t['status']=='open' and t['due_on']==c['today'].isoformat() for t in c['tasks']))
feature('Operations', 'ops.week_tasks', 'Tasks due within 7 days', 'count', 'Open tasks with deadlines from today to seven days ahead.', lambda c:sum(t['status']=='open' and 0<=-days(t['due_on'],c['today'])<=7 for t in c['tasks']))
feature('Operations', 'ops.collection_tasks', 'Total collection tasks', 'count', 'All tasks classified as collection work.', lambda c:sum(t['category']=='collection' for t in c['tasks']))
feature('Operations', 'ops.expense_tasks', 'Expense-review tasks', 'count', 'All tasks classified as expense work.', lambda c:sum(t['category']=='expense' for t in c['tasks']))
feature('Operations', 'ops.customer_profiles', 'Managed customer profiles', 'count', 'Customer profiles with relationship metadata.', lambda c:len(c['customers']))
feature('Operations', 'ops.saved_views', 'Saved search views', 'count', 'Saved filter presets for operational work.', lambda c:len(c['views']))

# 10. Business health — derived operational trends rather than opaque AI scores.
feature('Health', 'health.cash_week', 'Net cash events · 7 days', 'money', 'Manual inflows less outflows recorded in the last seven days.', lambda c:sum(e['amount_cents']*(1 if e['kind']=='income' else -1) for e in c['cash'] if 0<=days(e['occurs_on'],c['today'])<=7))
feature('Health', 'health.cash_month', 'Net cash events · 30 days', 'money', 'Manual inflows less outflows recorded in the last thirty days.', lambda c:sum(e['amount_cents']*(1 if e['kind']=='income' else -1) for e in c['cash'] if 0<=days(e['occurs_on'],c['today'])<=30))
feature('Health', 'health.invoice_ticket', 'Average invoiced ticket', 'money', 'Mean amount of all invoices, paid or unpaid.', lambda c:avg([i['amount_cents'] for i in c['invoices']]))
feature('Health', 'health.daily_burn', 'Modeled daily operating burn', 'money', 'Monthly expense baseline divided by thirty days.', lambda c:round(c['settings']['monthly_expenses_cents']/30))
feature('Health', 'health.cash_coverage', 'Opening cash coverage', 'days', 'Days of modeled operating costs covered by opening balance, excluding receipts.', lambda c:round(c['settings']['opening_balance_cents']/(c['settings']['monthly_expenses_cents']/30)) if c['settings']['monthly_expenses_cents'] else 0)
feature('Health', 'health.collection_rate', 'Invoice settlement rate', 'percent', 'Paid invoices as a share of all created invoices.', lambda c:pct(len(c['paid']),len(c['invoices'])))
feature('Health', 'health.overdue_ratio', 'Overdue share of open balance', 'percent', 'Percent of all outstanding receivables past due.', lambda c:pct(money(c['overdue']),money(c['unpaid'])))
feature('Health', 'health.paid_to_open', 'Paid value relative to open value', 'percent', 'Settled value divided by current unpaid value.', lambda c:pct(money(c['paid']),money(c['unpaid'])))
feature('Health', 'health.paid_invoice_share', 'Settled share of invoiced value', 'percent', 'Paid invoice value divided by total invoiced value.', lambda c:pct(money(c['paid']),money(c['invoices'])))
feature('Health', 'health.task_completion', 'Task completion rate', 'percent', 'Completed work tasks divided by all work tasks.', lambda c:pct(sum(t['status']=='done' for t in c['tasks']),len(c['tasks'])))


def evaluate_features(invoices: list[dict], resources: dict[str, list[dict]], settings: dict[str, int], today: date) -> dict:
    context = ctx_for(invoices, resources, settings, today)
    rows = []
    for group, features in FEATURE_GROUPS.items():
        for item in features:
            value = item.evaluate(context)
            rows.append({'id':item.key, 'group':group, 'label':item.label, 'kind':item.kind,
                         'description':item.description, 'value':value})
    return {'total':len(rows), 'groups':{name:len(features) for name,features in FEATURE_GROUPS.items()},
            'generated_on':today.isoformat(), 'features':rows}
