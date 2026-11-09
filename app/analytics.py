"""Pure, deterministic financial projections; all monetary inputs are integer cents.

The model is intentionally transparent, not a trained prediction system. Scenarios
apply documented receipt timing and collection weights. Outputs are estimates.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median


SCENARIOS = {
    "optimistic": {"delay": -5, "on_time_weight": 100, "overdue_weight": 90},
    "base": {"delay": 0, "on_time_weight": 92, "overdue_weight": 70},
    "stress": {"delay": 18, "on_time_weight": 68, "overdue_weight": 38},
}


def parse_day(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def customer_lateness(invoices: list[dict]) -> dict[str, int]:
    history: dict[str, list[int]] = defaultdict(list)
    for invoice in invoices:
        if invoice["paid_on"]:
            delay = (parse_day(invoice["paid_on"]) - parse_day(invoice["due_on"])).days
            history[invoice["customer"].strip().casefold()].append(delay)
    return {name: max(-10, min(45, round(median(delays)))) for name, delays in history.items()}


def collection_priority(invoice: dict, today: date, lateness: dict[str, int]) -> dict:
    days_overdue = max(0, (today - parse_day(invoice["due_on"])).days)
    past_behavior = lateness.get(invoice["customer"].strip().casefold(), 5)
    score = 10 + min(60, days_overdue * 2)
    if invoice["amount_cents"] >= 500_000:
        score += 10
    if past_behavior > 10:
        score += 20
    elif past_behavior > 0:
        score += 8
    if -7 <= (today - parse_day(invoice["due_on"])).days <= 0:
        score += 8
    score = min(100, score)
    if days_overdue >= 30:
        action = "Escalate with a personal call and payment plan"
    elif days_overdue > 0:
        action = "Send a personalized overdue reminder"
    elif (parse_day(invoice["due_on"]) - today).days <= 7:
        action = "Send a friendly pre-due reminder"
    else:
        action = "Monitor until the due date approaches"
    return {
        **invoice,
        "days_overdue": days_overdue,
        "risk_score": score,
        "risk_level": "Critical" if score >= 70 else "High" if score >= 45 else "Watch",
        "recommended_action": action,
    }


def summarize(invoices: list[dict], today: date) -> dict:
    unpaid = [i for i in invoices if not i["paid_on"]]
    paid = [i for i in invoices if i["paid_on"]]
    overdue = [i for i in unpaid if parse_day(i["due_on"]) < today]
    due_soon = [i for i in unpaid if today <= parse_day(i["due_on"]) <= today + timedelta(days=7)]
    value = lambda items: sum(i["amount_cents"] for i in items)
    total_count = len(invoices)
    return {
        "total_invoices": total_count,
        "outstanding_cents": value(unpaid),
        "overdue_cents": value(overdue),
        "overdue_count": len(overdue),
        "due_soon_cents": value(due_soon),
        "paid_cents": value(paid),
        "paid_count": len(paid),
        "collection_rate_pct": round(100 * len(paid) / total_count, 1) if total_count else 0,
    }


def forecast(
    invoices: list[dict], settings: dict[str, int], today: date, horizon: int = 90
) -> dict:
    """Project weighted, invoice-based receipts minus smoothed daily operating costs.

    Weights are deliberately heuristic. The resulting series is a planning
    scenario, not a prediction or promise of payment.
    """
    history = customer_lateness(invoices)
    unpaid = [i for i in invoices if not i["paid_on"]]
    all_series = {}
    opening = settings["opening_balance_cents"]
    daily_cost = settings["monthly_expenses_cents"] / 30

    for name, assumptions in SCENARIOS.items():
        receipts: dict[date, int] = defaultdict(int)
        for invoice in unpaid:
            due = parse_day(invoice["due_on"])
            late = history.get(invoice["customer"].strip().casefold(), 5)
            extra = max(0, late + assumptions["delay"])
            receipt_day = max(today + timedelta(days=1), due + timedelta(days=extra))
            # Overdue items need follow-up time; stress assumes a longer recovery.
            if due < today:
                receipt_day = max(receipt_day, today + timedelta(days=3 + max(0, assumptions["delay"])))
            weight = assumptions["overdue_weight"] if due < today else assumptions["on_time_weight"]
            receipts[receipt_day] += round(invoice["amount_cents"] * weight / 100)

        points = []
        cash = float(opening)
        first_negative = None
        minimum = opening
        for offset in range(horizon + 1):
            day = today + timedelta(days=offset)
            if offset:
                cash += receipts.get(day, 0) - daily_cost
            balance = round(cash)
            minimum = min(minimum, balance)
            if balance < 0 and first_negative is None:
                first_negative = day.isoformat()
            points.append({"date": day.isoformat(), "balance_cents": balance})
        all_series[name] = {
            "points": points,
            "end_balance_cents": points[-1]["balance_cents"],
            "low_balance_cents": minimum,
            "cash_gap_date": first_negative,
        }

    return {
        "horizon_days": horizon,
        "today": today.isoformat(),
        "scenarios": all_series,
        "assumptions": {
            "method": "Weighted invoice receipts, historical customer lateness and smoothed operating costs",
            "daily_expenses_cents": round(daily_cost),
            "weights_pct": {name: {"not_overdue": a["on_time_weight"], "overdue": a["overdue_weight"]} for name, a in SCENARIOS.items()},
            "limitations": "No seasonality, taxes, bank fees, new invoices or external bank transactions are modeled.",
        },
    }


def insights(invoices: list[dict], settings: dict[str, int], today: date) -> list[dict]:
    summary = summarize(invoices, today)
    prediction = forecast(invoices, settings, today)
    result = []
    if summary["overdue_count"]:
        result.append({"type": "warning", "title": "Receivables need attention", "description": f"{summary['overdue_count']} overdue invoices should be prioritized for follow-up."})
    base = prediction["scenarios"]["base"]
    stress = prediction["scenarios"]["stress"]
    if stress["cash_gap_date"]:
        result.append({"type": "danger", "title": "Stress-case cash gap", "description": f"A cash shortfall appears on {stress['cash_gap_date']} in the stress scenario. Review spending and collection timing."})
    elif base["cash_gap_date"]:
        result.append({"type": "danger", "title": "Projected cash gap", "description": f"The baseline crosses zero on {base['cash_gap_date']}. Revisit your assumptions."})
    else:
        result.append({"type": "success", "title": "Baseline liquidity stays positive", "description": "The modeled balance remains above zero across the next 90 days. Actual cash may differ."})
    if not invoices:
        result.append({"type": "info", "title": "Add your first invoice", "description": "Import a CSV or create an invoice to make the projections useful."})
    return result[:3]

