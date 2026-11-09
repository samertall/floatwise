from datetime import date

from app.analytics import collection_priority, customer_lateness, forecast, summarize


TODAY = date(2026, 11, 9)


def invoice(number, customer, amount, due, paid=None):
    return {
        "invoice_number": number,
        "customer": customer,
        "amount_cents": amount,
        "issued_on": "2026-09-01",
        "due_on": due,
        "paid_on": paid,
        "notes": "",
    }


def test_aggregates_do_not_count_paid_invoices_as_outstanding():
    rows = [
        invoice("INV-1", "Acme", 200_00, "2026-10-10"),
        invoice("INV-2", "Beta", 300_00, "2026-11-14"),
        invoice("INV-3", "Acme", 400_00, "2026-10-14", "2026-10-16"),
    ]
    summary = summarize(rows, TODAY)
    assert summary["outstanding_cents"] == 500_00
    assert summary["overdue_cents"] == 200_00
    assert summary["due_soon_cents"] == 300_00
    assert summary["paid_cents"] == 400_00
    assert summary["collection_rate_pct"] == 33.3


def test_customer_lateness_from_paid_history():
    rows = [invoice("1", "Acme", 100, "2026-10-01", "2026-10-08"),
            invoice("2", "Acme", 100, "2026-10-09", "2026-10-12")]
    assert customer_lateness(rows)["acme"] == 5


def test_risk_is_higher_for_severely_overdue_invoice():
    fresh = invoice("1", "Beta", 500_00, "2026-11-20")
    overdue = invoice("2", "Beta", 500_00, "2026-09-01")
    a = collection_priority(fresh, TODAY, {})
    b = collection_priority(overdue, TODAY, {})
    assert b["risk_score"] > a["risk_score"]
    assert b["risk_level"] == "Critical"
    assert b["days_overdue"] == 69


def test_scenario_bounds_and_timeline():
    rows = [invoice("1", "Acme", 300_000, "2026-11-15")]
    settings = {"opening_balance_cents": 100_000, "monthly_expenses_cents": 30_000}
    result = forecast(rows, settings, TODAY, horizon=90)
    scenarios = result["scenarios"]
    assert len(scenarios["base"]["points"]) == 91
    assert scenarios["optimistic"]["end_balance_cents"] >= scenarios["base"]["end_balance_cents"]
    assert scenarios["base"]["end_balance_cents"] >= scenarios["stress"]["end_balance_cents"]
    assert scenarios["base"]["points"][0]["balance_cents"] == 100_000
    assert result["assumptions"]["weights_pct"]["stress"]["overdue"] == 38


def test_zero_invoices_forecast_is_daily_operating_burn():
    result = forecast([], {"opening_balance_cents": 30_000, "monthly_expenses_cents": 30_000}, TODAY, horizon=30)
    assert result["scenarios"]["base"]["end_balance_cents"] == 0
    assert result["scenarios"]["base"]["cash_gap_date"] is None

