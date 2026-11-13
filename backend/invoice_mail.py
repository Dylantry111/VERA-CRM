"""Invoice presentation: readable numbers, plain-text and HTML email bodies, and a PDF copy.

Everything here is derived from stored invoice/order/customer facts. No payment details are invented:
the footer is configurable with VERA_INVOICE_FOOTER and otherwise only asks the customer to contact VERA.
"""
import io
import os
import re
import base64
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from html import escape

BRAND = 'VERA Shading Solutions'
DEFAULT_FOOTER = 'Please contact VERA to arrange payment. Questions about this invoice are welcome by reply to this email.'
_CJK = re.compile(r'([⺀-鿿＀-￯]+)')


def footer():
    return os.getenv('VERA_INVOICE_FOOTER', '').strip() or DEFAULT_FOOTER


def money(value):
    return f'{Decimal(str(value)):,.2f}'


INVOICE_PREFIX = 'INV-'
INVOICE_DIGITS = 5


def format_invoice_number(sequence):
    """Customer feedback, 30 Oct: one running number across deposit, balance and manual invoices, e.g. INV-00001."""
    return f'{INVOICE_PREFIX}{int(sequence):0{INVOICE_DIGITS}d}'


def invoice_number(invoice, order_numbers):
    """The saved running number. Invoices made before running numbers keep their old order-derived name
    (deposit V0000101-D, balance V0000105-B) until backfill_invoice_numbers.py gives them one."""
    if invoice.get('fixed_number'):
        return invoice['fixed_number']
    letter = 'D' if invoice.get('kind') == 'deposit' else 'B'
    numbers = sorted(order_numbers.get(oid) or '' for oid in invoice.get('order_ids', []))
    first = next((n for n in numbers if n), '')
    if not first:
        first = re.sub(r'[^A-Za-z0-9]', '', str(invoice.get('id', '')))[-8:].upper() or 'INVOICE'
    return f'{first}-{letter}'


def invoice_reference(invoice, order_numbers):
    """The reference is the order number; an invoice for several orders lists each one."""
    numbers = [order_numbers.get(oid) for oid in dict.fromkeys(invoice.get('order_ids', []))]
    return ', '.join(n for n in numbers if n)


def payment_lines(payment, labels=None, gst_number=''):
    """Label/value pairs for the bank details an administrator saved in settings; empty until something is saved."""
    labels = labels or {}
    fields = (('bank_name', labels.get('bank') or 'Bank'), ('account_name', labels.get('account_name') or 'Account Name'),
              ('account_number', labels.get('account_number') or 'Account Number'), ('reference_note', labels.get('payment_note') or 'Note'))
    result = [(label, str(payment[key]).strip()) for key, label in fields if payment and str(payment.get(key) or '').strip()]
    if gst_number:
        result.append((labels.get('payment_gst') or 'GST', gst_number))
    return result


def invoice_date(value):
    """Format stored ISO dates as the day-first New Zealand invoice format."""
    raw = str(value or '')[:10]
    try:
        parsed = date.fromisoformat(raw)
        return f'{parsed.day}/{parsed.month}/{parsed.year}'
    except ValueError:
        return raw or '—'


def gst_included(amount, rate):
    """The GST part of a GST-inclusive amount."""
    rate = Decimal(str(rate))
    return (Decimal(amount) * rate / (1 + rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def build(invoice, customer, orders, payment=None):
    """invoice: stored invoice dict; customer: portal profile dict; orders: {order_id: project dict}; payment: saved bank details."""
    numbers = {oid: o.get('order_number') for oid, o in orders.items()}
    number = invoice_number(invoice, numbers)
    reference = invoice_reference(invoice, numbers)
    kind = invoice.get('kind')
    deposit = kind == 'deposit'
    manual = kind == 'manual'
    template = invoice.get('template') or {}
    kind_key = kind if kind in ('deposit', 'balance') else 'manual'
    currency = invoice.get('currency', 'NZD')
    labels = template.get('invoice_labels') or {}
    columns = template.get('invoice_columns') or {}
    rate = invoice.get('tax_rate') or next((o['tax_rate'] for o in orders.values() if o.get('tax_rate')), '0.15')
    gst_rate = f"{Decimal(str(rate)) * 100:.0f}%"
    rows = []
    for line in invoice.get('lines', []):
        amount = Decimal(line['amount'])
        if line.get('description') and not line.get('order_id'):
            rows.append({'order': '', 'item': line['description'], 'project': line['description'], 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(amount)})
            continue
        if manual:
            rows.append({'order': '', 'item': line.get('description', ''), 'project': line.get('description', ''), 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(amount)})
            continue
        order = orders.get(line['order_id'], {})
        total = Decimal(order['total']) if order.get('total') not in (None, '') else None
        order_number = order.get('order_number') or line['order_id']
        row_title = 'Deposit for Order' if deposit else 'Balance for Order'
        rows.append({
            'order': order_number,
            'item': f'{row_title} {order_number}',
            'project': order.get('project_name', ''),
            'site': order.get('site_address', ''),
            'order_total': money(total) if total is not None else '',
            'unit_price': '',
            'quantity': '',
            'gst_rate': gst_rate,
            'amount': money(amount),
        })
    due = Decimal(invoice['amount'])
    gross = Decimal(invoice['gross']) if invoice.get('gross') else sum((Decimal(r['amount'].replace(',', '')) for r in rows), Decimal(0))
    rebate = max(gross - due, Decimal(0))
    rebate_items = [
        {'label': f"Monthly rebate · {item['month']}" if item.get('month') else 'Rebate credit', 'amount': money(Decimal(item['amount']))}
        for item in invoice.get('rebate_allocations', []) if Decimal(str(item.get('amount', '0'))) > 0
    ]
    for item in invoice.get('rebate_allocations', []):
        amount = Decimal(str(item.get('amount', '0')))
        if amount <= 0:
            continue
        month = str(item.get('month') or '')
        try:
            month = date.fromisoformat(month + '-01').strftime('%B %Y') if month else ''
        except ValueError:
            pass
        description = str(labels.get('credit_line') or 'Credit from {month}').replace('{month}', month or 'rebate')
        rows.append({'order': '', 'item': description, 'project': description, 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(-amount)})
    if rebate > 0 and not rebate_items:
        description = str(labels.get('credit_line') or 'Credit from {month}').replace('{month}', 'rebate')
        rows.append({'order': '', 'item': description, 'project': description, 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(-rebate)})
    bank = payment_lines(payment, labels, template.get('gst_number', ''))
    logo = ''
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'vera-logo.png')
        with open(logo_path, 'rb') as image_file:
            logo = 'data:image/png;base64,' + base64.b64encode(image_file.read()).decode('ascii')
    except OSError:
        pass
    model = {
        'number': number,
        'reference': reference,
        'kind': 'Deposit invoice' if deposit else ('Invoice' if manual else 'Balance invoice'),
        'kind_key': kind,
        'is_deposit': deposit,
        'date': str(invoice.get('created_at', ''))[:10],
        'due_date': str(invoice.get('due_date') or '—')[:10],
        'formatted_date': invoice_date(invoice.get('created_at')),
        'formatted_due_date': invoice_date(invoice.get('due_date')),
        'currency': currency,
        'tax_basis': str(invoice.get('tax_basis', '')).replace('_', ' '),
        'company': customer.get('company', ''),
        'brand': template.get('company_name') or BRAND,
        'brand_gst': template.get('gst_number', ''),
        'brand_address': template.get('company_address', ''),
        'logo': logo,
        'contact': customer.get('contact_name', ''),
        'address': customer.get('company_address', ''),
        'rows': rows,
        'gross': money(gross),
        'rebate': money(rebate) if rebate > 0 else '',
        'rebate_items': rebate_items,
        'due': money(due),
        'gst': money(gst_included(due, rate)),
        'gst_rate': f"{Decimal(str(rate)) * 100:.0f}%",
        'basis': (template.get('deposit_note') or f"Deposit of {Decimal(invoice.get('deposit_rate', '0.6')) * 100:.0f}% of the order total. Amounts include GST." if deposit
                  else 'Amounts include GST.' if manual
                  else template.get('balance_note') or 'Balance of each order after the deposit already paid. Amounts include GST.'),
        'payment': bank,
        'footer': template.get('footer') or (f'Please pay by bank transfer to the account above and quote {reference or number} as the reference.' if bank else footer()),
        'design': invoice_design(template, kind_key),
        'labels': {
            'invoice_title': labels.get('invoice_title') or 'TAX INVOICE',
            'bill_to': labels.get('bill_to') or 'BILL TO',
            'invoice_number': labels.get('invoice_number') or 'Invoice No.',
            'invoice_date': labels.get('invoice_date') or 'Invoice Date',
            'due_date': labels.get('due_date') or 'Due Date',
            'item': labels.get('item') or 'Item',
            'unit_price': labels.get('unit_price') or 'Unit Price',
            'quantity': labels.get('quantity') or 'Quantity',
            'gst': labels.get('gst') or 'GST',
            'total': labels.get('total') or 'Total',
            'subtotal': labels.get('subtotal') or 'Subtotal',
            'gst_included': labels.get('gst_included') or 'incl. GST',
            'payment_instruction': labels.get('payment_instruction') or 'Payment Instruction',
            'bank': labels.get('bank') or 'Bank',
            'account_name': labels.get('account_name') or 'Account Name',
            'account_number': labels.get('account_number') or 'Account Number',
            'payment_gst': labels.get('payment_gst') or 'GST',
            'payment_note': labels.get('payment_note') or 'Note',
            'credit_line': labels.get('credit_line') or 'Credit from {month}',
        },
        'columns': {'unit_price': columns.get('unit_price', True), 'quantity': columns.get('quantity', True), 'gst': columns.get('gst', True)},
    }
    model['subject'] = f"VERA invoice {number}"
    model['text'] = _text(model)
    model['html'] = _html(model)
    return model


_LAYOUT_BLOCKS = ('logo', 'company', 'heading', 'bill_to', 'order_lines', 'totals', 'payment', 'notes', 'footer')
_LAYOUT_LABELS = {
    'logo': 'Company logo', 'company': 'Company details', 'heading': 'Invoice title and dates',
    'bill_to': 'Customer details', 'order_lines': 'Orders and items', 'totals': 'GST and total',
    'payment': 'Payment details', 'notes': 'Invoice note', 'footer': 'Footer message',
}

_LAYOUT_AREAS = ('top_left', 'top_right', 'middle_left', 'middle_right', 'items', 'bottom_left', 'bottom_right', 'footer')
_DEFAULT_AREAS = {
    'logo': 'top_left', 'heading': 'top_right',
    'company': 'middle_left', 'bill_to': 'middle_right',
    'order_lines': 'items', 'payment': 'bottom_left', 'notes': 'bottom_left',
    'totals': 'bottom_right', 'footer': 'footer',
}
_DEFAULT_ALIGNMENTS = {'heading': 'right', 'totals': 'right'}


def default_invoice_design():
    return {'blocks': [{'id': block, 'enabled': True, 'align': _DEFAULT_ALIGNMENTS.get(block, 'left'), 'width': 220, 'area': _DEFAULT_AREAS[block]} for block in _LAYOUT_BLOCKS]}


def invoice_design(template, kind):
    """Normalize stored layout while keeping old flat invoice settings fully compatible."""
    saved = (template.get('invoice_designs') or {}).get(kind) or {}
    source = saved.get('blocks') or []
    by_id = {block.get('id'): block for block in source if block.get('id') in _LAYOUT_BLOCKS}
    blocks = []
    for block_id in _LAYOUT_BLOCKS:
        block = by_id.get(block_id, {})
        blocks.append({
            'id': block_id,
            'label': _LAYOUT_LABELS[block_id],
            'enabled': block.get('enabled', True) if block_id not in ('order_lines', 'totals') else True,
            'align': (block.get('align') if block.get('area') in _LAYOUT_AREAS else _DEFAULT_ALIGNMENTS.get(block_id, 'left')) if block.get('align') in ('left', 'center', 'right') else _DEFAULT_ALIGNMENTS.get(block_id, 'left'),
            'width': max(80, min(560, int(block.get('width') or 220))),
            'area': block.get('area') if block.get('area') in _LAYOUT_AREAS else _DEFAULT_AREAS[block_id],
        })
    # Preserve the chosen order, append any blocks added by a newer version.
    ordered = [dict(by_id[b.get('id')], id=b['id']) for b in source if b.get('id') in _LAYOUT_BLOCKS]
    seen = {b.get('id') for b in ordered}
    ordered += [b for b in blocks if b['id'] not in seen]
    for block in ordered:
        base = next(b for b in blocks if b['id'] == block['id'])
        if block.get('area') not in _LAYOUT_AREAS:
            block['area'] = base['area']
            block['align'] = base['align']
        block.update({k: base[k] for k in ('label', 'enabled', 'width') if k not in block})
        if block.get('align') not in ('left', 'center', 'right'):
            block['align'] = base['align']
        if block['id'] in ('order_lines', 'totals'):
            block['enabled'] = True
    return {'blocks': ordered}


def sample_preview(template, payment, kind):
    """Render a realistic, deterministic invoice example for the visual template editor."""
    customer = {'company': 'Auckland Shutters', 'contact_name': 'Jeremy', 'company_address': 'Auckland, New Zealand'}
    invoice = {
        'id': 'preview-invoice', 'fixed_number': 'INV-00042', 'kind': kind, 'customer_id': 1,
        'created_at': '2026-11-12', 'due_date': '2026-11-26', 'currency': 'NZD',
        'tax_rate': '0.15', 'deposit_rate': '0.60', 'tax_basis': 'GST inclusive',
        'amount': '1201.06' if kind == 'deposit' else ('801.06' if kind == 'balance' else '460.00'),
        'gross': '1201.06' if kind != 'manual' else '460.00', 'template': template,
        'lines': ([{'order_id': 'preview-order', 'amount': '1201.06', 'description': 'AA-METCALFE'}] if kind == 'deposit'
                  else [{'order_id': 'preview-order', 'amount': '801.06', 'description': 'AA-METCALFE'}] if kind == 'balance'
                  else [{'description': 'Additional installation service', 'amount': '460.00'}]),
    }
    orders = {'preview-order': {'order_number': 'AA-METCALFE', 'project_name': 'Living room shutters', 'site_address': 'Auckland', 'total': '2001.77', 'tax_rate': '0.15'}}
    model = build(invoice, customer, orders, payment)
    model['preview_html'] = _html(model, a4=True)
    return model


def _columns(m):
    """Amount column labels; the text, HTML and PDF versions share this layout."""
    if m['is_deposit']:
        return ('Order total', 'Deposit due')
    return ('Amount incl. GST',) if m['kind_key'] == 'manual' else ('Balance incl. GST',)


def _cells(m, r):
    if m['is_deposit']:
        return [r['order_total'], r['amount']]
    return [r['amount']]


def _invoice_table_columns(m):
    labels, visible = m['labels'], m['columns']
    columns = []
    if visible.get('unit_price', True):
        columns.append(('unit_price', labels['unit_price']))
    if visible.get('quantity', True):
        columns.append(('quantity', labels['quantity']))
    if visible.get('gst', True):
        columns.append(('gst_rate', labels['gst']))
    columns.append(('amount', labels['total']))
    return columns


def _invoice_table_cells(m, row):
    return [(key, row.get(key, '')) for key, _ in _invoice_table_columns(m)]


def _invoice_amount(m, value):
    amount = Decimal(str(value or '0').replace(',', ''))
    sign = '-' if amount < 0 else ''
    return f"{sign}{m['currency']} {money(abs(amount))}"


def _invoice_subtotal(m):
    return money(Decimal(str(m['due'])) - Decimal(str(m['gst'])))


def _text(m):
    labels = m['labels']
    lines = [m.get('brand') or BRAND, labels['invoice_title'], f"{labels['invoice_number']} {m['number']}",
             f"{labels['invoice_date']}: {m['formatted_date']}", f"{labels['due_date']}: {m['formatted_due_date']}", '',
             f"{labels['bill_to']}: {m['company']}" + (f" ({m['contact']})" if m['contact'] else '')]
    if m['address']:
        lines.append(m['address'])
    if m.get('brand_gst'):
        lines.append(f"VERA GST No.: {m['brand_gst']}")
    if m.get('brand_address'):
        lines.append(m['brand_address'])
    lines.append('')
    for r in m['rows']:
        lines.append(r['item'])
        for key, label in _invoice_table_columns(m):
            value = r.get(key, '')
            if value:
                lines.append(f"    {label}: {_invoice_amount(m, value) if key == 'amount' else value}")
    lines.append('')
    lines += [f"{labels['subtotal']}: {m['currency']} {_invoice_subtotal(m)}", f"{labels['gst_included']} ({m['gst_rate']}): {m['currency']} {m['gst']}",
              f"{labels['total']}: {m['currency']} {m['due']}", m['basis'], '']
    if m['payment']:
        lines += [labels['payment_instruction']] + [f"    {label}: {value}" for label, value in m['payment']] + ['']
    lines += [m['footer'], 'The PDF invoice is attached.']
    return '\n'.join(lines)


def _html_legacy(m):
    e = escape
    green, ink, line = '#0f6e5c', '#1b2421', '#e1e8e3'
    labels = _columns(m)
    th = ''.join(f'<td align="right" style="padding:8px 0 8px 12px;border-bottom:2px solid {ink};font-size:11px;letter-spacing:.08em;color:#64766b;text-transform:uppercase">{e(label)}</td>' for label in labels)
    body = ''
    for r in m['rows']:
        cells = ''.join(
            f'<td align="right" style="padding:12px 0 12px 12px;border-bottom:1px solid {line};font-size:14px;color:{ink};white-space:nowrap">{e(m["currency"])} {v}</td>' if v
            else f'<td style="border-bottom:1px solid {line}"></td>' for v in _cells(m, r))
        main, sub = (r["order"], r["project"] + (" · " + r["site"] if r["site"] else "")) if r["order"] else (r["project"], "")
        detail = f'<br><span style="color:#64766b;font-size:12px">{e(sub)}</span>' if sub else ''
        body += (f'<tr><td style="padding:12px 0;border-bottom:1px solid {line};font-size:14px;color:{ink}"><strong>{e(str(main))}</strong>'
                 f'{detail}</td>{cells}</tr>')
    span = 1 + len(labels)
    extra = ''
    if m['rebate']:
        extra = f'<tr><td colspan="{span - 1}" style="padding:10px 0 4px;font-size:13px;color:#64766b">Subtotal</td><td align="right" style="padding:10px 0 4px;font-size:13px;color:#64766b;white-space:nowrap">{e(m["currency"])} {m["gross"]}</td></tr>'
        if m['rebate_items']:
            extra += ''.join(f'<tr><td colspan="{span - 1}" style="padding:4px 0;font-size:13px;color:#64766b">{e(item["label"])}</td><td align="right" style="padding:4px 0;font-size:13px;color:#64766b;white-space:nowrap">-{e(m["currency"])} {item["amount"]}</td></tr>' for item in m['rebate_items'])
        else:
            extra += f'<tr><td colspan="{span - 1}" style="padding:4px 0 12px;font-size:13px;color:#64766b">Rebate applied</td><td align="right" style="padding:4px 0 12px;font-size:13px;color:#64766b;white-space:nowrap">-{e(m["currency"])} {m["rebate"]}</td></tr>'
    pay = ''
    if m['payment']:
        pay = ('<tr><td style="padding:0 32px 16px"><div style="color:#64766b;font-size:11px;letter-spacing:.1em;margin-bottom:6px">PAYMENT DETAILS</div>'
               + ''.join(f'<div style="font-size:13px;line-height:1.7;color:{ink}"><span style="color:#64766b">{e(label)}:</span> <strong>{e(value)}</strong></div>' for label, value in m['payment'])
               + '</td></tr>')
    reference = f'<div style="font-size:13px;opacity:.85;margin-top:2px">Reference: {e(m["reference"])}</div>' if m['reference'] else ''
    logo = f'<img src="{m["logo"]}" alt="{e(m["brand"])}" style="display:block;max-width:220px;max-height:72px;margin:0 0 16px;background:#fff;border-radius:5px">' if m.get('logo') else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:0;background:#f4f7f5;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:{ink}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7f5;padding:24px 12px"><tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid {line}">
<tr><td style="background:{green};padding:26px 32px;color:#ffffff">{logo}<div style="font-size:12px;letter-spacing:.16em;opacity:.8">{e(m['brand'].upper())}</div>{f'<div style="font-size:11px;opacity:.8">GST No. {e(m["brand_gst"])}</div>' if m.get('brand_gst') else ''}{f'<div style="font-size:11px;opacity:.8">{e(m["brand_address"])}</div>' if m.get('brand_address') else ''}
<div style="font-size:24px;font-weight:700;margin-top:6px">{e(m["kind"])}</div><div style="font-size:14px;opacity:.9;margin-top:2px">{e(m["number"])}</div>{reference}</td></tr>
<tr><td style="padding:28px 32px 8px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td valign="top" style="font-size:13px;line-height:1.6"><div style="color:#64766b;font-size:11px;letter-spacing:.1em">BILL TO</div><strong>{e(m["company"])}</strong>{"<br>" + e(m["contact"]) if m["contact"] else ""}{"<br>" + e(m["address"]) if m["address"] else ""}</td>
<td valign="top" align="right" style="font-size:13px;line-height:1.6"><div style="color:#64766b;font-size:11px;letter-spacing:.1em">INVOICE DATE</div><strong>{e(m["date"])}</strong><br><span style="color:#64766b;font-size:11px">DUE DATE</span> <strong>{e(m["due_date"])}</strong></td></tr></table></td></tr>
<tr><td style="padding:12px 32px 0"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="padding:8px 0;border-bottom:2px solid {ink};font-size:11px;letter-spacing:.08em;color:#64766b">ORDER</td>{th}</tr>
{body}{extra}</table></td></tr>
<tr><td style="padding:8px 32px 24px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef6f2;border-radius:10px"><tr>
<td style="padding:16px 18px;font-size:13px;color:#34503f">Includes GST ({e(m["gst_rate"])}): {e(m["currency"])} {m["gst"]}<br><span style="font-size:11px;color:#64766b">{e(m["basis"])}</span></td>
<td align="right" style="padding:16px 18px;font-size:26px;font-weight:700;color:{green};white-space:nowrap">{e(m["currency"])} {m["due"]}</td></tr></table></td></tr>
{pay}<tr><td style="padding:0 32px 28px;font-size:13px;line-height:1.7;color:#4d6256">{e(m["footer"])}<br><span style="color:#64766b">The PDF invoice is attached to this email.</span></td></tr>
</table></td></tr></table></body></html>'''


def _html(m, a4=False):
    e = escape
    accent, ink, line = '#405969', '#263640', '#dce4e8'
    labels = m['labels']
    columns = _invoice_table_columns(m)
    headings = ''.join(f'<td align="right" style="padding:8px 0 8px 12px;border-bottom:2px solid {ink};font-size:11px;color:#64766b">{e(label)}</td>' for _, label in columns)
    rows = ''
    for row in m['rows']:
        values = ''.join(f'<td align="right" style="padding:10px 0 10px 12px;border-bottom:1px solid {line};white-space:nowrap">{e(_invoice_amount(m,row.get(key)))}</td>' if key == 'amount' and row.get(key) else f'<td align="right" style="padding:10px 0 10px 12px;border-bottom:1px solid {line};white-space:nowrap">{e(str(row.get(key,"—")))}</td>' for key, _ in columns)
        rows += f'<tr><td style="padding:10px 0;border-bottom:1px solid {line}">{e(row["item"])}</td>{values}</tr>'
    design = (m.get('design') or {}).get('blocks') or invoice_design({}, 'deposit')['blocks']
    payment = '<div style="padding:12px;border:1px solid ' + line + ';border-radius:7px"><b>' + e(labels['payment_instruction']) + '</b>' + ''.join(f'<div>{e(label)}: <strong>{e(value)}</strong></div>' for label, value in m['payment']) + '</div>' if m['payment'] else ''
    sections = []
    area_sections = {area: [] for area in _LAYOUT_AREAS}
    for block in design:
        bid, align = block['id'], block.get('align', 'left')
        area = block.get('area') if block.get('area') in area_sections else _DEFAULT_AREAS[bid]
        if not block.get('enabled', True):
            continue
        if bid == 'logo' and m.get('logo'):
            width = int(block.get('width', 220))
            value = f'<div style="text-align:{align};margin-bottom:12px"><img src="{m["logo"]}" alt="{e(m["brand"])}" style="width:{width}px;max-width:100%;height:auto;max-height:150px"></div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'company':
            value = f'<b style="font-size:15px">{e(m["brand"])}</b>' + (f'<div>GST No. {e(m["brand_gst"])}</div>' if m['brand_gst'] else '') + (f'<div>{e(m["brand_address"])}</div>' if m['brand_address'] else '')
            value = f'<div style="text-align:{align};font-size:12px;line-height:1.55;color:#52636d;margin-bottom:12px">{value}</div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'heading':
            reference = f'<div>Reference: {e(m["reference"])}</div>' if m['reference'] else ''
            value = f'<div style="text-align:{align};padding:10px 0;border-bottom:1px solid {line};margin-bottom:14px"><strong style="font-size:23px;color:{accent}">{e(labels["invoice_title"])}</strong><div>{e(labels["invoice_number"])} {e(m["number"])}</div>{reference}<small>{e(labels["invoice_date"])}: {e(m["formatted_date"])} · {e(labels["due_date"])}: {e(m["formatted_due_date"])}</small></div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'bill_to':
            value = f'<small>{e(labels["bill_to"])}</small><br><strong>{e(m["company"])}</strong>' + ('<br>' + e(m['contact']) if m['contact'] else '') + ('<br>' + e(m['address']) if m['address'] else '')
            value = f'<div style="text-align:{align};padding:12px;background:#f5f7f8;border-radius:7px;margin-bottom:14px">{value}</div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'order_lines':
            value = f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px"><tr><td style="border-bottom:2px solid {ink};padding:8px 0">{e(labels["item"])}</td>{headings}</tr>{rows}</table>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'totals':
            value = f'<div style="text-align:{align};padding:12px;background:#edf2f4;border-radius:7px;margin-bottom:14px"><div>{e(labels["subtotal"])}: {e(m["currency"])} {_invoice_subtotal(m)}</div><div>{e(labels["gst_included"])} ({e(m["gst_rate"])}): {e(m["currency"])} {e(m["gst"])}</div><strong style="font-size:21px;color:{accent}">{e(labels["total"])}: {e(m["currency"])} {e(m["due"])}</strong></div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'payment' and payment:
            value = f'<div style="text-align:{align};margin-bottom:14px">{payment}</div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'notes':
            value = f'<div style="text-align:{align};font-size:12px;color:#52636d;margin-bottom:14px">{e(m["basis"])}</div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'footer':
            value = f'<div style="text-align:{align};border-top:1px solid {line};padding-top:12px;font-size:12px;color:#52636d">{e(m["footer"])}<br><small>The PDF invoice is attached to this email.</small></div>'
            sections.append(value); area_sections[area].append(value)
    content = ''.join(sections)
    if a4:
        area_names = {'top_left': 'top-left', 'top_right': 'top-right', 'middle_left': 'middle-left', 'middle_right': 'middle-right', 'items': 'items', 'bottom_left': 'bottom-left', 'bottom_right': 'bottom-right', 'footer': 'footer'}
        grid = ''.join(f'<section class="invoice-area {area_names[area]}">{"".join(area_sections[area])}</section>' for area in _LAYOUT_AREAS)
        return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=794,initial-scale=1"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:794px;height:1123px;overflow:hidden!important;background:#fff;font-family:Arial,Helvetica,sans-serif;color:{ink}}}
@page{{size:A4;margin:0}}#paper{{width:794px;height:1123px;padding:42px 46px;overflow:hidden;background:#fff}}
.invoice-grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-areas:"top-left top-right" "middle-left middle-right" "items items" "bottom-left bottom-right" "footer footer";column-gap:24px;row-gap:10px;align-content:start}}
.invoice-area.top-left{{grid-area:top-left}}.invoice-area.top-right{{grid-area:top-right}}.invoice-area.middle-left{{grid-area:middle-left}}.invoice-area.middle-right{{grid-area:middle-right}}.invoice-area.items{{grid-area:items}}.invoice-area.bottom-left{{grid-area:bottom-left}}.invoice-area.bottom-right{{grid-area:bottom-right}}.invoice-area.footer{{grid-area:footer}}
.invoice-area{{min-width:0}}.invoice-area table{{table-layout:fixed}}.invoice-area img{{height:auto}}
.invoice-area.bottom-right{{text-align:right}}.invoice-area.bottom-right>div{{display:inline-block;text-align:right}}
.invoice-area.footer{{margin-top:8px}}
</style></head><body><main id="paper"><div class="invoice-grid">{grid}</div></main></body></html>'''
    return f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:20px 10px;background:#f1f4f5;font-family:Arial,sans-serif;color:{ink}"><table width="100%"><tr><td align="center"><table width="680" style="max-width:680px;width:100%;background:#fff;border:1px solid {line};border-radius:10px"><tr><td style="padding:26px 30px">{content}</td></tr></table></td></tr></table></body></html>'


def render_pdf(m):
    """A4 PDF with the same content as the email. CJK names use the built-in CID font, so no font files are shipped."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    try:
        pdfmetrics.getFont('STSong-Light')
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    def P(text, style):
        # Text is escaped here, so styling is done with paragraph styles, never with inline markup.
        safe = _CJK.sub(lambda g: f'<font name="STSong-Light">{g.group(1)}</font>', escape(str(text)))
        return Paragraph(safe, style)

    green, ink, muted = colors.HexColor('#0f6e5c'), colors.HexColor('#1b2421'), colors.HexColor('#64766b')
    base = ParagraphStyle('base', fontName='Helvetica', fontSize=9.5, leading=13, textColor=ink)
    small = ParagraphStyle('small', parent=base, fontSize=8, leading=10.5, textColor=muted)
    right = ParagraphStyle('right', parent=base, alignment=2)
    small_right = ParagraphStyle('small_right', parent=small, alignment=2)
    bold = ParagraphStyle('bold', parent=base, fontName='Helvetica-Bold')
    bold_right = ParagraphStyle('bold_right', parent=bold, alignment=2)
    due_right = ParagraphStyle('due_right', parent=bold_right, fontSize=13, leading=16, textColor=green)
    title = ParagraphStyle('title', parent=base, fontName='Helvetica-Bold', fontSize=22, leading=26, textColor=green)
    buf = io.BytesIO()
    # reportlab frames add 6pt padding; subtract it so paragraphs and full-width tables share one left edge (174mm of content).
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm - 6, rightMargin=18 * mm - 6, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"{m['kind']} {m['number']}", author=BRAND)
    story = []
    if m.get('logo'):
        from reportlab.platypus import Image
        story.append(Image(io.BytesIO(base64.b64decode(m['logo'].split(',', 1)[1])), width=52 * mm, height=13 * mm, kind='proportional'))
        story.append(Spacer(1, 3 * mm))
    story += [P(m.get('brand') or BRAND, small), P(m['kind'], title), P(m['number'], base)]
    if m.get('brand_gst'):
        story.append(P('GST No. ' + m['brand_gst'], small))
    if m.get('brand_address'):
        story.append(P(m['brand_address'], small))
    if m['reference']:
        story.append(P('Reference: ' + m['reference'], base))
    story.append(Spacer(1, 8 * mm))
    head = Table([[P('BILL TO', small), P('INVOICE DATE', small_right), P('DUE DATE', small_right)],
                  [P(m['company'], bold), P(m['date'], bold_right), P(m.get('due_date') or '—', bold_right)]], colWidths=[104 * mm, 35 * mm, 35 * mm])
    head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story.append(head)
    for extra in (m['contact'], m['address']):
        if extra:
            story.append(P(extra, small))
    story.append(Spacer(1, 8 * mm))

    labels = _columns(m)
    amount_w = 27 * mm
    widths = [26 * mm, 174 * mm - 26 * mm - amount_w * len(labels)] + [amount_w] * len(labels)
    data = [[P('ORDER', small), P('PROJECT', small)] + [P(label.upper(), small_right) for label in labels]]
    for r in m['rows']:
        project = r['project'] + (f" - {r['site']}" if r['site'] else '')
        cells = [P(f"{m['currency']} {v}" if v else '', right) for v in _cells(m, r)]
        data.append([P(r['order'], base), P(project, base)] + cells)
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 1, ink), ('LINEBELOW', (0, 1), (-1, -1), 0.4, colors.HexColor('#dfe7e1')),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story += [table, Spacer(1, 4 * mm)]
    totals = []
    if m['rebate']:
        totals.append([P('Subtotal', base), P(f"{m['currency']} {m['gross']}", right)])
        if m['rebate_items']:
            totals += [[P(item['label'], base), P(f"-{m['currency']} {item['amount']}", right)] for item in m['rebate_items']]
        else:
            totals.append([P('Rebate applied', base), P(f"-{m['currency']} {m['rebate']}", right)])
    totals.append([P(f"Includes GST ({m['gst_rate']})", small), P(f"{m['currency']} {m['gst']}", small_right)])
    totals.append([P('Amount due (incl. GST)', bold), P(f"{m['currency']} {m['due']}", due_right)])
    t = Table(totals, colWidths=[134 * mm, 40 * mm])
    t.setStyle(TableStyle([('LINEABOVE', (0, -2), (-1, -2), 1, green), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                           ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    story += [t, Spacer(1, 3 * mm), P(m['basis'], small)]
    if m['tax_basis']:
        story.append(P(f"Pricing basis: {m['tax_basis']}", small))
    if m['payment']:
        story += [Spacer(1, 8 * mm), P('PAYMENT DETAILS', small)] + [P(f"{label}: {value}", base) for label, value in m['payment']]
    story += [Spacer(1, 8 * mm), P(m['footer'], base)]
    doc.build(story)
    return buf.getvalue()


_render_pdf_legacy = render_pdf


def render_pdf(m):
    """A4 invoice PDF rendered from the same movable blocks as the HTML invoice."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    try:
        pdfmetrics.getFont('STSong-Light')
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    def para(value, size=9, bold=False, color='#263640', align='left'):
        safe = _CJK.sub(lambda g: f'<font name="STSong-Light">{g.group(1)}</font>', escape(str(value or '')).replace('\n', '<br/>'))
        return Paragraph(safe, ParagraphStyle(f'invoice_{size}_{bold}_{align}', fontName='Helvetica-Bold' if bold else 'Helvetica', fontSize=size, leading=size + 3, textColor=colors.HexColor(color), alignment={'left': 0, 'center': 1, 'right': 2}[align]))

    accent = colors.HexColor('#405969')
    ink = colors.HexColor('#263640')
    muted = colors.HexColor('#64766b')
    labels = m['labels']
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=f"{m['kind']} {m['number']}", author=BRAND)
    width = A4[0] - 36 * mm
    design = (m.get('design') or {}).get('blocks') or invoice_design({}, 'deposit')['blocks']
    block_content = {block['id']: [] for block in design}
    for block in design:
        bid, align = block['id'], block.get('align', 'left')
        out = block_content[bid]
        if not block.get('enabled', True):
            continue
        if bid == 'logo' and m.get('logo'):
            image = Image(io.BytesIO(base64.b64decode(m['logo'].split(',', 1)[1])), width=min(width / 2 - 8 * mm, int(block.get('width', 220)) / 3.78 * mm), height=28 * mm, kind='proportional')
            image.hAlign = {'left': 'LEFT', 'center': 'CENTER', 'right': 'RIGHT'}[align]
            out += [image, Spacer(1, 3 * mm)]
        elif bid == 'company':
            details = [para(m['brand'], 12, True, '#405969', align)]
            if m['brand_gst']:
                details.append(para('GST No. ' + m['brand_gst'], 8, color='#64766b', align=align))
            if m['brand_address']:
                details.append(para(m['brand_address'], 8, color='#64766b', align=align))
            out += details + [Spacer(1, 3 * mm)]
        elif bid == 'heading':
            out += [para(labels['invoice_title'], 21, True, '#405969', align), para(f"{labels['invoice_number']} {m['number']}", 10, align=align)]
            if m['reference']:
                out.append(para('Reference: ' + m['reference'], 9, align=align))
            out += [para(f"{labels['invoice_date']}: {m['formatted_date']}    {labels['due_date']}: {m['formatted_due_date']}", 8, color='#64766b', align=align), Spacer(1, 4 * mm)]
        elif bid == 'bill_to':
            out.append(para(labels['bill_to'], 8, True, '#64766b'))
            out.append(para(m['company'], 11, True))
            if m['contact']:
                out.append(para(m['contact'], 8, color='#64766b'))
            if m['address']:
                out.append(para(m['address'], 8, color='#64766b'))
            out.append(Spacer(1, 5 * mm))
        elif bid == 'order_lines':
            columns = _invoice_table_columns(m)
            item_width = max(60 * mm, width - 26 * mm * len(columns))
            widths = [item_width] + [(width - item_width) / len(columns)] * len(columns)
            data = [[para(labels['item'], 8, True, muted)] + [para(label, 8, True, muted, 'right') for _, label in columns]]
            for row in m['rows']:
                cells = [para(row['item'], 9)]
                for key, _ in columns:
                    value = row.get(key, '')
                    text = _invoice_amount(m, value) if key == 'amount' and value else str(value or '—')
                    cells.append(para(text, 9, align='right'))
                data.append(cells)
            table = Table(data, colWidths=widths, repeatRows=1)
            table.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,0),1,ink),('LINEBELOW',(0,1),(-1,-1),.4,colors.HexColor('#dce4e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
            out += [table, Spacer(1, 4 * mm)]
        elif bid == 'totals':
            totals = []
            totals += [[para(labels['subtotal'], 9), para(f"{m['currency']} {_invoice_subtotal(m)}", 9, align='right')], [para(f"{labels['gst_included']} ({m['gst_rate']})", 8, color='#64766b'), para(f"{m['currency']} {m['gst']}", 8, color='#64766b', align='right')], [para(labels['total'], 11, True, '#405969'), para(f"{m['currency']} {m['due']}", 14, True, '#405969', 'right')]]
            table = Table(totals, colWidths=[(width / 2) * .65, (width / 2) * .35])
            table.setStyle(TableStyle([('LINEABOVE',(0,-2),(-1,-2),1,accent),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
            out += [table, Spacer(1, 4 * mm)]
        elif bid == 'payment' and m['payment']:
            out.append(para(labels['payment_instruction'], 8, True, '#64766b', align))
            out += [para(f'{label}: {value}', 9, align=align) for label, value in m['payment']]
            out.append(Spacer(1, 4 * mm))
        elif bid == 'notes':
            out += [para(m['basis'], 8, color='#64766b', align=align), Spacer(1, 3 * mm)]
        elif bid == 'footer':
            out.append(para(m['footer'], 9, color='#52636d', align=align))
    story = []
    def area_content(area):
        result = []
        for block in design:
            block_area = block.get('area') if block.get('area') in _LAYOUT_AREAS else _DEFAULT_AREAS[block['id']]
            if block_area == area:
                result.extend(block_content[block['id']])
        return result
    def add_full(area):
        values = area_content(area)
        if values:
            story.extend(values + [Spacer(1, 5 * mm)])
    def add_pair(left_area, right_area):
        left, right = area_content(left_area), area_content(right_area)
        if left or right:
            table = Table([[left or [''], right or ['']]], colWidths=[width / 2, width / 2])
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),5 * mm),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
            story.extend([table, Spacer(1, 5 * mm)])
    add_pair('top_left', 'top_right')
    add_pair('middle_left', 'middle_right')
    add_full('items')
    add_pair('bottom_left', 'bottom_right')
    add_full('footer')
    doc.build(story)
    return buffer.getvalue()
