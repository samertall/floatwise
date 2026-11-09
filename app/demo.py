"""Synthetic invoice fixtures; no real customers or payment records."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4


def demo_invoices(today: date | None = None) -> list[dict]:
    today = today or date.today()
    names = [
        ("Northstar Studio", 5400, -48, -19, None),
        ("Atlas Commerce", 12800, -42, -7, None),
        ("Lumina Health", 3750, -35, 4, None),
        ("Terra Logistics", 8200, -30, 16, None),
        ("Canvas Digital", 2450, -24, 6, None),
        ("Northstar Studio", 3900, -18, 21, None),
        ("Orion Education", 6700, -46, -16, -9),
        ("Terra Logistics", 4300, -60, -30, -17),
        ("Atlas Commerce", 9700, -58, -28, -11),
        ("Lumina Health", 2800, -52, -22, -23),
        ("Nova Labs", 11500, -5, 25, None),
        ("Orion Education", 5800, -9, 19, None),
        ("Meridian Works", 7200, -16, 13, None),
        ("Canvas Digital", 3300, -40, -11, None),
    ]
    result = []
    for index, (customer, amount, issued, due, paid) in enumerate(names, 1):
        result.append({
            "id": str(uuid4()),
            "invoice_number": f"FW-{2400 + index}",
            "customer": customer,
            "amount_cents": amount * 100,
            "issued_on": (today + timedelta(days=issued)).isoformat(),
            "due_on": (today + timedelta(days=due)).isoformat(),
            "paid_on": (today + timedelta(days=paid)).isoformat() if paid is not None else None,
            "notes": "Synthetic demonstration invoice",
            "created_at": today.isoformat(),
        })
    return result
