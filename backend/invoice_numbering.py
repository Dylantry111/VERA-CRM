"""Permanent invoice number reservations, separate from editable draft records.

Writers hold BEGIN IMMEDIATE (SQLite) or the shared PostgreSQL advisory lock.
The registry's unique keys are the final protection against duplicate numbers.
"""
import json
import re
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def counter(c, key, floor=0, advance=True):
    row = c.execute('SELECT data FROM operations_records WHERE id=?', (key,)).fetchone()
    value = max(floor, int(json.loads(row['data']).get('value', 0)) if row else 0) + int(advance)
    c.execute('INSERT INTO operations_records(id,kind,customer_id,data) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
              (key, 'internal_counter', None, json.dumps({'id': key, 'value': value})))
    return value


def prepare_draft(c, invoice):
    if invoice.get('fixed_number'):
        return invoice
    if not invoice.get('draft_number'):
        invoice['draft_number'] = f'DRAFT-{counter(c, "invoice-draft-sequence"):05d}'
    invoice['invoice_number'] = invoice['draft_number']
    invoice['numbering_status'] = 'draft'
    return invoice


def reserve(c, invoice, actor='system'):
    existing = c.execute('SELECT invoice_number,sequence FROM invoice_number_registry WHERE invoice_id=?', (invoice['id'],)).fetchone()
    if existing:
        invoice.update(fixed_number=existing['invoice_number'], invoice_number=existing['invoice_number'],
                       sequence=existing['sequence'], numbering_status='issued')
    else:
        # An old deployment may have committed a numbered record while rolling
        # over. Adopt that reservation rather than ever reusing its number.
        while True:
            sequence = counter(c, 'invoice-number-sequence')
            number = f'INV-{sequence:05d}'
            expression = "upper(data::jsonb->>'fixed_number')" if hasattr(c, 'connection') else "upper(json_extract(data,'$.fixed_number'))"
            owner = c.execute(f"SELECT id FROM operations_records WHERE kind='invoice' AND {expression}=?", (number,)).fetchone()
            if not owner or owner['id'] == invoice['id']:
                break
            c.execute('INSERT INTO invoice_number_registry(invoice_number,invoice_id,sequence,reserved_at) VALUES(?,?,?,?)',
                      (number, owner['id'], sequence, now()))
        c.execute('INSERT INTO invoice_number_registry(invoice_number,invoice_id,sequence,reserved_at) VALUES(?,?,?,?)',
                  (number, invoice['id'], sequence, now()))
        invoice.update(fixed_number=number, invoice_number=number, sequence=sequence, numbering_status='issued')
    invoice.setdefault('issued_at', now())
    invoice.setdefault('issued_by', actor)
    return invoice


def migrate(c, backend):
    marker = 'invoice-numbering-v2'
    if c.execute('SELECT 1 FROM operations_records WHERE id=?', (marker,)).fetchone():
        return
    c.executescript('''
    CREATE TABLE IF NOT EXISTS invoice_number_registry(invoice_number TEXT PRIMARY KEY,invoice_id TEXT NOT NULL UNIQUE,sequence BIGINT UNIQUE,reserved_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS invoice_number_audit(invoice_id TEXT PRIMARY KEY,previous_number TEXT NOT NULL,new_number TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL);
    ''')
    invoices = [json.loads(row['data']) for row in c.execute("SELECT data FROM operations_records WHERE kind='invoice'").fetchall()]
    floor = 0
    groups = {}
    for invoice in invoices:
        number = invoice.get('fixed_number') or invoice.get('invoice_number') or ''
        if number.startswith('DRAFT-'):
            number = ''
        if number:
            match = re.fullmatch(r'INV-(\d+)', number, re.I)
            sequence = int(match.group(1)) if match else None
            floor = max(floor, sequence or 0, int(invoice.get('sequence') or 0))
            groups.setdefault(number.upper(), []).append((invoice, sequence))
    counter(c, 'invoice-number-sequence', floor=floor, advance=False)
    repairs = []
    for number, group in groups.items():
        group.sort(key=lambda pair: (not bool(pair[0].get('notification_id')), pair[0].get('created_at', ''), pair[0]['id']))
        keeper, sequence = group[0]
        c.execute('INSERT INTO invoice_number_registry(invoice_number,invoice_id,sequence,reserved_at) VALUES(?,?,?,?)',
                  (number, keeper['id'], sequence, now()))
        keeper.update(fixed_number=number, invoice_number=number, numbering_status='issued')
        keeper.setdefault('issued_at', keeper.get('created_at') or now())
        for duplicate, _ in group[1:]:
            if duplicate.get('notification_id') or duplicate.get('status') in ('sent', 'demo_sent', 'sending'):
                raise RuntimeError('A duplicate invoice has delivery history; review it before numbering migration')
            repairs.append((duplicate, number))
    for invoice, previous in repairs:
        reserve(c, invoice)
        invoice.setdefault('legacy_numbers', []).append(previous)
        invoice.setdefault('numbering_history', []).append({'previous_number': previous, 'new_number': invoice['fixed_number'],
                                                          'reason': 'Repair duplicate historical invoice number', 'created_at': now()})
        c.execute('INSERT INTO invoice_number_audit(invoice_id,previous_number,new_number,reason,created_at) VALUES(?,?,?,?,?)',
                  (invoice['id'], previous, invoice['fixed_number'], 'duplicate_historical_number', now()))
    for invoice in invoices:
        if not invoice.get('fixed_number'):
            prepare_draft(c, invoice)
        c.execute('UPDATE operations_records SET data=? WHERE id=?', (json.dumps(invoice, ensure_ascii=False), invoice['id']))
    # Index the persisted public number as well as the independent registry.
    expression = "upper(data::jsonb->>'fixed_number')" if backend == 'postgres' else "upper(json_extract(data,'$.fixed_number'))"
    c.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS invoice_public_number_unique ON operations_records(({expression})) WHERE kind='invoice'")
    c.execute('INSERT INTO operations_records(id,kind,customer_id,data) VALUES(?,?,?,?)',
              (marker, 'internal_migration', None, json.dumps({'id': marker, 'completed_at': now(), 'repairs': len(repairs)})))
