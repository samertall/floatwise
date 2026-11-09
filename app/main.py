"""Floatwise HTTP API and locally hosted web application."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app import analytics, database, feature_lab, operations
from app.demo import demo_invoices

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.environ.get("FLOATWISE_DB_PATH", "data/floatwise.sqlite3"))
INSERT_SQL = """INSERT INTO invoices
    (id, invoice_number, customer, amount_cents, issued_on, due_on, paid_on, notes, created_at)
    VALUES (:id, :invoice_number, :customer, :amount_cents, :issued_on, :due_on,
            :paid_on, :notes, :created_at)"""


def as_cents(amount: Decimal) -> int:
    value = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if value < 0 or value > 100_000_000_000:
        raise ValueError("Amount must be between 0 and 1 billion")
    return value


class InvoiceCreate(BaseModel):
    invoice_number: str = Field(min_length=2, max_length=36, pattern=r"^[A-Za-z0-9][A-Za-z0-9_\-/]*$")
    customer: str = Field(min_length=2, max_length=100)
    amount: Decimal = Field(gt=0, le=Decimal("1000000000"))
    issued_on: date
    due_on: date
    paid_on: date | None = None
    notes: str = Field(default="", max_length=500)

    @field_validator("customer", "invoice_number")
    @classmethod
    def no_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Cannot be blank")
        return value

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.due_on < self.issued_on:
            raise ValueError("Due date cannot precede issue date")
        if self.paid_on and self.paid_on < self.issued_on:
            raise ValueError("Payment date cannot precede issue date")
        return self


class PaymentUpdate(BaseModel):
    paid_on: date | None


class SettingsUpdate(BaseModel):
    opening_balance: Decimal = Field(ge=0, le=Decimal("1000000000"))
    monthly_expenses: Decimal = Field(ge=0, le=Decimal("1000000000"))


def normalize_invoice(payload: InvoiceCreate) -> dict:
    return {
        "id": str(uuid4()),
        "invoice_number": payload.invoice_number,
        "customer": payload.customer,
        "amount_cents": as_cents(payload.amount),
        "issued_on": payload.issued_on.isoformat(),
        "due_on": payload.due_on.isoformat(),
        "paid_on": payload.paid_on.isoformat() if payload.paid_on else None,
        "notes": payload.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def create_app(db_path: str | Path | None = None, seed_demo: bool | None = None) -> FastAPI:
    path = Path(db_path) if db_path is not None else DEFAULT_DB
    database.initialize(path)
    with database.connect(path) as connection:
        operations.initialize(connection)
    demo_enabled = (os.environ.get("FLOATWISE_DEMO", "1") == "1") if seed_demo is None else seed_demo
    if demo_enabled:
        with database.connect(path) as connection:
            if connection.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 0:
                connection.executemany(INSERT_SQL, demo_invoices())

    app = FastAPI(title="Floatwise API", version="2.0.0", description="Explainable SME receivables and finance operations intelligence")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "static" / "index.html")

    @app.get("/api/health", tags=["System"])
    def health():
        return {"status": "ok", "database": "sqlite", "mode": "single-workspace-demo"}

    @app.get("/api/dashboard", tags=["Analytics"])
    def dashboard():
        with database.connect(path) as connection:
            invoices = database.fetch_invoices(connection)
            settings = database.fetch_settings(connection)
        today = date.today()
        history = analytics.customer_lateness(invoices)
        priorities = [analytics.collection_priority(i, today, history) for i in invoices if not i["paid_on"]]
        priorities.sort(key=lambda item: (-item["risk_score"], item["due_on"]))
        return {
            "today": today.isoformat(),
            "summary": analytics.summarize(invoices, today),
            "forecast": analytics.forecast(invoices, settings, today),
            "priorities": priorities,
            "insights": analytics.insights(invoices, settings, today),
            "settings": settings,
            "demo_mode": demo_enabled,
        }

    @app.get("/api/invoices", tags=["Invoices"])
    def list_invoices():
        with database.connect(path) as connection:
            return {"items": database.fetch_invoices(connection)}

    @app.post("/api/invoices", status_code=201, tags=["Invoices"])
    def add_invoice(payload: InvoiceCreate):
        row = normalize_invoice(payload)
        try:
            with database.connect(path) as connection:
                connection.execute(INSERT_SQL, row)
                operations.activity(connection, 'created', 'invoices', row['id'])
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, "Invoice number already exists") from error
        return row

    @app.patch("/api/invoices/{invoice_id}/payment", tags=["Invoices"])
    def set_payment(invoice_id: str, payload: PaymentUpdate):
        with database.connect(path) as connection:
            invoice = connection.execute("SELECT issued_on FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            if not invoice:
                raise HTTPException(404, "Invoice not found")
            if payload.paid_on and payload.paid_on < date.fromisoformat(invoice["issued_on"]):
                raise HTTPException(422, "Payment cannot precede invoice issue date")
            connection.execute(
                "UPDATE invoices SET paid_on = ? WHERE id = ?",
                (payload.paid_on.isoformat() if payload.paid_on else None, invoice_id),
            )
            operations.activity(connection, 'payment_updated', 'invoices', invoice_id)
            return dict(connection.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone())

    @app.delete("/api/invoices/{invoice_id}", status_code=204, tags=["Invoices"])
    def remove_invoice(invoice_id: str):
        with database.connect(path) as connection:
            cursor = connection.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
            if not cursor.rowcount:
                raise HTTPException(404, "Invoice not found")
            operations.activity(connection, 'deleted', 'invoices', invoice_id)
        return Response(status_code=204)

    @app.patch("/api/settings", tags=["Settings"])
    def update_settings(payload: SettingsUpdate):
        values = {
            "opening_balance_cents": as_cents(payload.opening_balance),
            "monthly_expenses_cents": as_cents(payload.monthly_expenses),
        }
        with database.connect(path) as connection:
            connection.executemany("UPDATE settings SET value = ? WHERE key = ?", ((v, k) for k, v in values.items()))
            operations.activity(connection, 'updated', 'settings', 'financial-baseline')
        return values

    @app.post("/api/import", tags=["Invoices"])
    async def import_csv(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "text/csv":
            raise HTTPException(415, "Expected text/csv")
        if int(request.headers.get("content-length", "0") or 0) > 1_000_000:
            raise HTTPException(413, "CSV too large (1 MB maximum)")
        body = await request.body()
        if len(body) > 1_000_000:
            raise HTTPException(413, "CSV too large (1 MB maximum)")
        try:
            reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
            required = {"invoice_number", "customer", "amount", "issued_on", "due_on"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise HTTPException(422, f"CSV must contain: {', '.join(sorted(required))}")
            rows = []
            for index, item in enumerate(reader, 2):
                if index > 251:
                    raise HTTPException(413, "Import limit is 250 invoices per file")
                try:
                    if item.get("paid_on") == "":
                        item["paid_on"] = None
                    if item.get("notes") is None:
                        item["notes"] = ""
                    rows.append(normalize_invoice(InvoiceCreate.model_validate(item)))
                except (ValueError, TypeError) as error:
                    raise HTTPException(422, f"Invalid CSV row {index}: {error}") from error
        except UnicodeDecodeError as error:
            raise HTTPException(422, "CSV must use UTF-8 encoding") from error
        try:
            with database.connect(path) as connection:
                connection.executemany(INSERT_SQL, rows)
                for row in rows:
                    operations.activity(connection, 'imported', 'invoices', row['id'])
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, "Duplicate invoice number in import or database; no rows imported") from error
        return {"imported": len(rows)}

    @app.get("/api/export", tags=["Invoices"])
    def export_csv():
        with database.connect(path) as connection:
            invoices = database.fetch_invoices(connection)
        output = io.StringIO()
        fields = ["invoice_number", "customer", "amount", "issued_on", "due_on", "paid_on", "notes"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in invoices:
            # Protect spreadsheet viewers from CSV formula injection in free-text fields.
            def safe_cell(value: str | None) -> str:
                text = value or ""
                return f"'{text}" if text.lstrip().startswith(("=", "+", "-", "@")) else text
            writer.writerow({
                **{key: safe_cell(row[key]) for key in fields if key != "amount"},
                "amount": f"{Decimal(row['amount_cents']) / 100:.2f}",
            })
        return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="floatwise-invoices.csv"'})

    # V2: a small finance operations layer under the existing public API.
    @app.get('/api/v2/features', tags=['Intelligence Lab'])
    def intelligence_features():
        with database.connect(path) as connection:
            invoices = database.fetch_invoices(connection)
            settings = database.fetch_settings(connection)
            resources = operations.get_all(connection)
        return feature_lab.evaluate_features(invoices, resources, settings, date.today())

    @app.get('/api/v2/workspace', tags=['Operations'])
    def operations_workspace():
        with database.connect(path) as connection:
            return {
                'resources': operations.get_all(connection),
                'activity': operations.get_activity(connection),
            }

    @app.get('/api/v2/activity', tags=['Operations'])
    def activity_feed():
        with database.connect(path) as connection:
            return {'items': operations.get_activity(connection)}

    @app.get('/api/v2/backup', tags=['Reports'])
    def backup():
        with database.connect(path) as connection:
            data = operations.backup_data(connection)
        return Response(
            __import__('json').dumps(data, indent=2), media_type='application/json',
            headers={'Content-Disposition':'attachment; filename="floatwise-backup.json"'},
        )

    @app.get('/api/v2/reports/{resource}', tags=['Reports'])
    def reports(resource: str, format: str = 'csv'):
        if resource not in (*operations.TABLES.keys(), 'invoices', 'features'):
            raise HTTPException(404, 'Unknown report')
        if format not in ('csv', 'json'):
            raise HTTPException(422, 'Choose csv or json')
        with database.connect(path) as connection:
            if resource == 'invoices':
                rows = database.fetch_invoices(connection)
            elif resource == 'features':
                rows = feature_lab.evaluate_features(
                    database.fetch_invoices(connection), operations.get_all(connection),
                    database.fetch_settings(connection), date.today(),
                )['features']
            else:
                rows = operations.get_rows(connection, resource)
        if format == 'json':
            return Response(__import__('json').dumps(rows, indent=2), media_type='application/json',
                            headers={'Content-Disposition':f'attachment; filename="floatwise-{resource}.json"'})
        return Response(operations.report_csv(rows), media_type='text/csv',
                        headers={'Content-Disposition':f'attachment; filename="floatwise-{resource}.csv"'})

    @app.get('/api/v2/forecast', tags=['Intelligence Lab'])
    def flexible_forecast(days: int = 90):
        if not 7 <= days <= 365:
            raise HTTPException(422, 'Forecast horizon must be 7 to 365 days')
        with database.connect(path) as connection:
            return analytics.forecast(database.fetch_invoices(connection),
                                      database.fetch_settings(connection),date.today(),horizon=days)

    @app.get('/api/v2/reminders', tags=['Collections'])
    def reminder_drafts():
        with database.connect(path) as connection:
            invoices = database.fetch_invoices(connection)
        today = date.today()
        scores = analytics.customer_lateness(invoices)
        queue = [analytics.collection_priority(i,today,scores) for i in invoices if not i['paid_on']]
        queue.sort(key=lambda i:(-i['risk_score'],i['due_on']))
        drafts = []
        for item in queue[:20]:
            status = f"{item['days_overdue']} days overdue" if item['days_overdue'] else f"due on {item['due_on']}"
            drafts.append({
                'invoice_id':item['id'],
                'subject':f"Payment reminder for invoice {item['invoice_number']}",
                'body':f"Hello {item['customer']},\n\nThis is a friendly reminder that invoice {item['invoice_number']} for ${item['amount_cents']/100:,.2f} is {status}. Please let us know when we can expect payment.\n\nThank you.",
                'risk_level':item['risk_level'],
            })
        return {'drafts':drafts, 'disclaimer':'Drafts are not sent and must be reviewed by a person.'}

    @app.get('/api/v2/{resource}', tags=['Operations'])
    def resource_list(resource: str):
        if resource not in operations.TABLES:
            raise HTTPException(404, 'Unknown resource')
        with database.connect(path) as connection:
            return {'items':operations.get_rows(connection, resource)}

    @app.post('/api/v2/{resource}', status_code=201, tags=['Operations'])
    def resource_add(resource: str, payload: dict):
        if resource not in operations.TABLES:
            raise HTTPException(404, 'Unknown resource')
        try:
            validated = operations.MODELS[resource].model_validate(payload)
        except ValidationError as error:
            raise HTTPException(422, error.errors(include_url=False, include_context=False)) from error
        try:
            with database.connect(path) as connection:
                return operations.create(connection, resource, validated)
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, 'A record with this unique name or category already exists') from error

    @app.put('/api/v2/{resource}/{item_id}', tags=['Operations'])
    def resource_replace(resource: str, item_id: str, payload: dict):
        if resource not in operations.TABLES:
            raise HTTPException(404, 'Unknown resource')
        try:
            validated = operations.MODELS[resource].model_validate(payload)
        except ValidationError as error:
            raise HTTPException(422, error.errors(include_url=False, include_context=False)) from error
        try:
            with database.connect(path) as connection:
                row = operations.update(connection,resource,item_id,validated)
                if row is None:
                    raise HTTPException(404, 'Record not found')
                return row
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, 'A record with this unique name or category already exists') from error

    @app.delete('/api/v2/{resource}/{item_id}', status_code=204, tags=['Operations'])
    def resource_delete(resource: str, item_id: str):
        if resource not in operations.TABLES:
            raise HTTPException(404, 'Unknown resource')
        with database.connect(path) as connection:
            if not operations.remove(connection,resource,item_id):
                raise HTTPException(404, 'Record not found')
        return Response(status_code=204)

    return app


app = create_app()
