"""Bank/accounting statement imports and human-approved invoice reconciliation.

Supports CSV exports, QIF, OFX statement entries, and ISO 20022 camt.053.
Imports stage data for review; they NEVER auto-post to a ledger or contact a bank.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from app import operations


SCHEMA = """
CREATE TABLE IF NOT EXISTS bank_transactions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    booking_date TEXT NOT NULL,
    description TEXT NOT NULL,
    signed_amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'unreviewed' CHECK(status IN ('unreviewed','posted','matched','ignored')),
    invoice_id TEXT,
    cash_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(source,external_id)
);
CREATE INDEX IF NOT EXISTS idx_bank_date ON bank_transactions(booking_date);
CREATE TABLE IF NOT EXISTS invoice_payments (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    paid_on TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON invoice_payments(invoice_id);
"""

FORMATS = ('bank_csv','quickbooks_csv','xero_csv','qif','ofx','camt053')
MAX_RECORDS = 500
MAX_BYTES = 2_000_000


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def cents(value: str | Decimal) -> int:
    try:
        amount = Decimal(str(value).replace(',','').strip())
        result = int((amount*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        if abs(result) > 100_000_000_000:
            raise ValueError('Transaction exceeds supported limit')
        return result
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f'Invalid money amount: {value!r}') from error


def iso_date(value: str) -> str:
    value=(value or '').strip()
    for fmt in ('%Y-%m-%d','%m/%d/%Y','%d/%m/%Y','%Y%m%d','%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(value[:19],fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f'Invalid date: {value!r}; expected ISO or common statement date')


def choose(row: dict, *options: str) -> str:
    normalized={str(k).strip().casefold().replace('_',' ').replace('-',' '):str(v or '').strip() for k,v in row.items() if k is not None}
    for option in options:
        value=normalized.get(option.casefold().replace('_',' ').replace('-',' '))
        if value:
            return value
    return ''


def parsed_row(when: str, description: str, signed: int, reference: str='', currency: str='USD') -> dict:
    if not description.strip():
        raise ValueError('Transaction description is required')
    currency=(currency or 'USD').strip().upper()
    if not re.fullmatch(r'[A-Z]{3}',currency):
        raise ValueError('Currency must be a three-letter ISO code')
    return {'booking_date':iso_date(when),'description':description.strip()[:250],
            'signed_amount_cents':signed,'currency':currency,'reference':reference.strip()[:180]}


def parse_csv(text: str, style: str) -> list[dict]:
    reader=csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError('Missing CSV header')
    parsed=[]
    for index,row in enumerate(reader,2):
        if index>MAX_RECORDS+1:
            raise ValueError('Import exceeds 500 transactions')
        when=choose(row,'date','booking date','transaction date','created','created at')
        description=choose(row,'description','memo','payee','name','details','item')
        reference=choose(row,'reference','id','transaction id','ref','number')
        currency=choose(row,'currency') or 'USD'
        amount=choose(row,'amount','total','net')
        if not amount:
            debit=choose(row,'debit','withdrawal')
            credit=choose(row,'credit','deposit')
            if not debit and not credit:
                raise ValueError(f'Row {index}: expected amount or debit/credit columns')
            signed=cents(credit or '0')-cents(debit or '0')
        else:
            signed=cents(amount)
        if style=='quickbooks_csv':
            kind=choose(row,'type','transaction type').casefold()
            if kind in ('expense','bill payment','check','debit'):
                signed=-abs(signed)
            elif kind in ('deposit','receive payment','sales receipt','credit'):
                signed=abs(signed)
        parsed.append(parsed_row(when,description,signed,reference,currency))
    return parsed


def parse_qif(text: str) -> list[dict]:
    records=[]
    current={}
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('!Type:'):
            continue
        if line=='^':
            if current:
                records.append(parsed_row(current.get('D',''),current.get('P') or current.get('M','Transaction'),
                                          cents(current.get('T','')),current.get('N','')))
            current={}
            continue
        if line[0] in 'DTPMN':
            current[line[0]]=line[1:]
        if len(records)>MAX_RECORDS:
            raise ValueError('Import exceeds 500 transactions')
    if current:
        raise ValueError('QIF transaction must end with ^')
    return records


def parse_ofx(text: str) -> list[dict]:
    # Minimal OFX 1.x SGML + OFX 2.x XML STMTTRN support; never parses DTDs.
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('External entities and DTDs are not allowed')
    records=[]
    for block in re.findall(r'<STMTTRN(?:\s[^>]*)?>(.*?)</STMTTRN>',text,re.I|re.S):
        def tag(name: str) -> str:
            match=re.search(rf'<{name}>([^<\r\n]+)',block,re.I)
            return match.group(1).strip() if match else ''
        when=tag('DTPOSTED')[:8]
        description=tag('NAME') or tag('MEMO') or 'Bank transaction'
        records.append(parsed_row(when,description,cents(tag('TRNAMT')),tag('FITID')))
        if len(records)>MAX_RECORDS:
            raise ValueError('Import exceeds 500 transactions')
    if not records:
        raise ValueError('No OFX STMTTRN entries found')
    return records


def parse_camt053(text: str) -> list[dict]:
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('External entities and DTDs are not allowed')
    try:
        root=ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError('Invalid camt.053 XML') from error
    def child(node, name: str):
        return next((e for e in node.iter() if e.tag.rsplit('}',1)[-1]==name),None)
    result=[]
    for entry in root.iter():
        if entry.tag.rsplit('}',1)[-1]!='Ntry':
            continue
        amt=child(entry,'Amt')
        when=child(entry,'Dt')
        indicator=child(entry,'CdtDbtInd')
        ref=child(entry,'NtryRef')
        info=child(entry,'AddtlNtryInf')
        if amt is None or when is None:
            raise ValueError('camt.053 entry is missing an amount or date')
        sign=-1 if indicator is not None and indicator.text=='DBIT' else 1
        result.append(parsed_row(when.text or '', info.text if info is not None and info.text else 'Bank transfer',
                                 sign*abs(cents(amt.text or '')),ref.text if ref is not None and ref.text else '',
                                 amt.attrib.get('Ccy','USD')))
        if len(result)>MAX_RECORDS:
            raise ValueError('Import exceeds 500 transactions')
    if not result:
        raise ValueError('No camt.053 entry records found')
    return result


def parse_import(fmt: str, data: bytes) -> list[dict]:
    if fmt not in FORMATS:
        raise ValueError('Supported formats: '+', '.join(FORMATS))
    if len(data)>MAX_BYTES:
        raise ValueError('Maximum file size is 2 MB')
    try:
        text=data.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('Use UTF-8 encoding for statements') from error
    if fmt in ('bank_csv','quickbooks_csv','xero_csv'):
        result=parse_csv(text,fmt)
    elif fmt=='qif':
        result=parse_qif(text)
    elif fmt=='ofx':
        result=parse_ofx(text)
    else:
        result=parse_camt053(text)
    return result


def ingest(connection: sqlite3.Connection, source: str, records: list[dict]) -> dict:
    added=skipped=0
    collisions={}
    for record in records:
        base=record['reference'] or '|'.join(str(record[k]) for k in ('booking_date','description','signed_amount_cents','currency'))
        collisions[base]=collisions.get(base,0)+1
        stable=hashlib.sha256(f'{source}|{base}|{collisions[base]}'.encode()).hexdigest()
        try:
            connection.execute('''INSERT INTO bank_transactions
                (id,source,external_id,booking_date,description,signed_amount_cents,currency,created_at)
                VALUES (?,?,?,?,?,?,?,?)''',
                (str(uuid4()),source,stable,record['booking_date'],record['description'],
                 record['signed_amount_cents'],record['currency'],datetime.now(timezone.utc).isoformat()))
            added+=1
        except sqlite3.IntegrityError:
            skipped+=1
    if added:
        operations.activity(connection,'imported','bank_transactions',source)
    return {'imported':added,'duplicates':skipped,'total':len(records),'source':source,
            'note':'Transactions are staged; review and post or reconcile manually.'}


def get_transactions(connection: sqlite3.Connection, status: str | None=None) -> list[dict]:
    query='SELECT * FROM bank_transactions'
    params=()
    if status:
        query+=' WHERE status = ?'
        params=(status,)
    query+=' ORDER BY booking_date DESC, created_at DESC'
    return [dict(row) for row in connection.execute(query,params)]


def get_invoice_balance(connection: sqlite3.Connection, invoice_id: str) -> dict | None:
    row=connection.execute('SELECT id,amount_cents,paid_on,invoice_number FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
    if not row:
        return None
    total=connection.execute('SELECT COALESCE(SUM(amount_cents),0) FROM invoice_payments WHERE invoice_id = ?', (invoice_id,)).fetchone()[0]
    # Old binary paid invoices without ledger records remain fully settled.
    paid=row['amount_cents'] if row['paid_on'] and not total else total
    return {'id':row['id'],'invoice_number':row['invoice_number'],'amount_cents':row['amount_cents'],
            'paid_cents':paid,'balance_cents':max(0,row['amount_cents']-paid)}


def record_payment(connection: sqlite3.Connection, invoice_id: str, amount_cents: int, on: str,
                   reference: str='', source: str='manual') -> dict:
    invoice=get_invoice_balance(connection,invoice_id)
    if not invoice:
        raise ValueError('Invoice not found')
    if amount_cents<=0 or amount_cents>invoice['balance_cents']:
        raise ValueError('Payment must be positive and no greater than the unpaid invoice balance')
    issued = connection.execute('SELECT issued_on FROM invoices WHERE id = ?', (invoice_id,)).fetchone()[0]
    if iso_date(on) < issued:
        raise ValueError('Payment cannot precede the invoice issue date')
    payment={'id':str(uuid4()),'invoice_id':invoice_id,'amount_cents':amount_cents,
             'paid_on':iso_date(on),'reference':reference[:180],'source':source,
             'created_at':datetime.now(timezone.utc).isoformat()}
    connection.execute('''INSERT INTO invoice_payments
        (id,invoice_id,amount_cents,paid_on,reference,source,created_at)
        VALUES (:id,:invoice_id,:amount_cents,:paid_on,:reference,:source,:created_at)''',payment)
    if amount_cents==invoice['balance_cents']:
        connection.execute('UPDATE invoices SET paid_on = ? WHERE id = ?', (payment['paid_on'],invoice_id))
    operations.activity(connection,'payment_recorded','invoices',invoice_id)
    return {**payment,'remaining_cents':invoice['balance_cents']-amount_cents}


def payment_history(connection: sqlite3.Connection, invoice_id: str) -> list[dict]:
    return [dict(row) for row in connection.execute(
        'SELECT * FROM invoice_payments WHERE invoice_id = ? ORDER BY paid_on,created_at',(invoice_id,))]


def undo_payment(connection: sqlite3.Connection, payment_id: str) -> bool:
    row=connection.execute('SELECT invoice_id,source FROM invoice_payments WHERE id = ?', (payment_id,)).fetchone()
    if not row:
        return False
    if row['source']!='manual':
        raise ValueError('Imported bank payments cannot be reversed independently of the bank transaction')
    connection.execute('DELETE FROM invoice_payments WHERE id = ?', (payment_id,))
    connection.execute('UPDATE invoices SET paid_on = NULL WHERE id = ?', (row['invoice_id'],))
    operations.activity(connection,'payment_reversed','invoices',row['invoice_id'])
    return True


def suggestions(connection: sqlite3.Connection, transaction_id: str) -> list[dict]:
    item=connection.execute('SELECT * FROM bank_transactions WHERE id = ?', (transaction_id,)).fetchone()
    if not item or item['signed_amount_cents']<=0 or item['status']!='unreviewed':
        return []
    result=[]
    from app.database import fetch_invoices
    for invoice in fetch_invoices(connection):
        if invoice['balance_cents']<=0:
            continue
        score=0
        description=item['description'].casefold()
        if invoice['invoice_number'].casefold() in description:
            score+=65
        if invoice['customer'].casefold() in description:
            score+=25
        if invoice['balance_cents']==item['signed_amount_cents']:
            score+=30
        elif invoice['balance_cents']>=item['signed_amount_cents']:
            score+=12
        if abs((date.fromisoformat(item['booking_date'])-date.fromisoformat(invoice['due_on'])).days)<=30:
            score+=8
        if score>=20:
            result.append({'invoice_id':invoice['id'],'invoice_number':invoice['invoice_number'],
                           'customer':invoice['customer'],'remaining_cents':invoice['balance_cents'],
                           'confidence_pct':min(100,score)})
    return sorted(result,key=lambda x:-x['confidence_pct'])[:5]


def review(connection: sqlite3.Connection, transaction_id: str, action: str,
           invoice_id: str | None=None) -> dict:
    row=connection.execute('SELECT * FROM bank_transactions WHERE id = ?', (transaction_id,)).fetchone()
    if not row:
        raise ValueError('Transaction not found')
    if row['status']!='unreviewed':
        raise ValueError('Transaction was already reviewed')
    if action not in ('post','reconcile','ignore'):
        raise ValueError('Choose post, reconcile, or ignore')
    if action=='reconcile' and not invoice_id:
        raise ValueError('Select an invoice for reconciliation')
    if action=='reconcile' and (row['signed_amount_cents']<=0 or row['currency']!='USD'):
        raise ValueError('Only incoming USD transactions can be matched to USD invoices')
    cash_id=None
    if action in ('post','reconcile'):
        if row['currency']!='USD':
            raise ValueError('Convert non-USD transactions before posting into the USD workspace')
        if not row['signed_amount_cents']:
            raise ValueError('Zero-value transactions cannot be posted')
        if action=='reconcile':
            record_payment(connection,invoice_id,row['signed_amount_cents'],row['booking_date'],
                           row['description'],source=row['source'])
        cash=operations.create(connection,'cash',operations.CashInput(
            title=row['description'][:120],kind='income' if row['signed_amount_cents']>0 else 'expense',
            amount=Decimal(abs(row['signed_amount_cents']))/100,
            occurs_on=date.fromisoformat(row['booking_date']),category='Imported bank activity',
            notes=f"Source: {row['source']} / {row['external_id'][:12]}"))
        cash_id=cash['id']
    status={'post':'posted','reconcile':'matched','ignore':'ignored'}[action]
    connection.execute('''UPDATE bank_transactions SET status = ?, invoice_id = ?, cash_id = ? WHERE id = ?''',
                       (status,invoice_id if action=='reconcile' else None,cash_id,transaction_id))
    operations.activity(connection,action,'bank_transactions',transaction_id)
    return {'id':transaction_id,'status':status,'invoice_id':invoice_id if action=='reconcile' else None,
            'cash_id':cash_id}
