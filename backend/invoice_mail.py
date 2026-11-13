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


def payment_lines(payment, labels=None, gst_number='', visible=None):
    """Label/value pairs for the bank details an administrator saved in settings; empty until something is saved."""
    labels = labels or {}
    fields = (('bank_name', labels.get('bank') or 'Bank'), ('account_name', labels.get('account_name') or 'Account Name'),
              ('account_number', labels.get('account_number') or 'Account Number'), ('reference_note', labels.get('payment_note') or 'Note'))
    visible = visible or {}
    flags = {'bank_name': 'payment_bank', 'account_name': 'payment_account_name', 'account_number': 'payment_account_number', 'reference_note': 'payment_note'}
    result = [(label, str(payment[key]).strip()) for key, label in fields if payment and visible.get(flags[key], True) and str(payment.get(key) or '').strip()]
    if gst_number and visible.get('payment_gst', True):
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


def invoice_field_settings(template, kind):
    """Normalize optional per-template visibility settings for invoice content modules."""
    defaults = {
        'deposit': {'item_columns': ['order_id', 'description', 'order_total', 'gst', 'amount']},
        'balance': {'item_columns': ['order_id', 'description', 'site_address', 'gst', 'amount']},
        'manual': {'item_columns': ['description', 'gst', 'amount']},
    }
    settings = dict(defaults[kind])
    settings.update((template.get('invoice_field_settings') or {}).get(kind) or {})
    return settings


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
    fields = invoice_field_settings(template, kind_key)
    rate = invoice.get('tax_rate') or next((o['tax_rate'] for o in orders.values() if o.get('tax_rate')), '0.15')
    gst_rate = f"{Decimal(str(rate)) * 100:.0f}%"
    rows = []
    for line in invoice.get('lines', []):
        amount = Decimal(line['amount'])
        if line.get('description') and not line.get('order_id'):
            rows.append({'order': '', 'item': line['description'], 'description': line['description'], 'project': line['description'], 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(amount)})
            continue
        if manual:
            rows.append({'order': '', 'item': line.get('description', ''), 'description': line.get('description', ''), 'project': line.get('description', ''), 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(amount)})
            continue
        order = orders.get(line['order_id'], {})
        total = Decimal(order['total']) if order.get('total') not in (None, '') else None
        order_number = order.get('order_number') or line['order_id']
        row_title = 'Deposit for Order' if deposit else 'Balance for Order'
        rows.append({
            'order': order_number,
            'item': f'{row_title} {order_number}',
            'description': order.get('project_name', ''),
            'project': order.get('project_name', ''),
            'site': order.get('site_address', ''),
            'order_total': money(total) if total is not None else '',
            'amount_due': money(amount),
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
        rows.append({'order': '', 'item': description, 'description': description, 'project': description, 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(-amount)})
    if rebate > 0 and not rebate_items:
        description = str(labels.get('credit_line') or 'Credit from {month}').replace('{month}', 'rebate')
        rows.append({'order': '', 'item': description, 'description': description, 'project': description, 'site': '', 'order_total': '', 'unit_price': '', 'quantity': '', 'gst_rate': gst_rate, 'amount': money(-rebate)})
    bank = payment_lines(payment, labels, template.get('gst_number', ''), fields)
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
        'customer_phone': customer.get('phone', ''),
        'customer_email': customer.get('email', ''),
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
            'company_gst': labels.get('company_gst') or 'GST No.',
            'reference': labels.get('reference') or 'Reference',
            'order_id': labels.get('order_id') or 'Order ID',
            'description': labels.get('description') or 'Description',
            'site_address': labels.get('site_address') or 'Site address',
            'order_total': labels.get('order_total') or 'Order total',
            'amount_due': labels.get('amount_due') or 'Amount due',
        },
        'columns': {'unit_price': columns.get('unit_price', True), 'quantity': columns.get('quantity', True), 'gst': columns.get('gst', True)},
        'field_settings': fields,
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


def default_invoice_canvas_elements():
    def item(id, field, x, y, width, height, font_size=12, bold=False, align='left'):
        return {'id': id, 'type': 'field', 'field': field, 'text': '', 'shape': 'rectangle', 'x': x, 'y': y,
                'width': width, 'height': height, 'font_family': 'Arial', 'font_size': font_size,
                'color': '#263640', 'background': '', 'border_color': '#d5dde2', 'border_width': 0,
                'bold': bold, 'italic': False, 'align': align}
    return [
        {**item('logo', '', 48, 38, 220, 75), 'type': 'logo'},
        item('company-name', 'company_name', 48, 128, 330, 24, 16, True),
        item('company-gst', 'company_gst', 48, 153, 330, 18, 9),
        item('company-address', 'company_address', 48, 172, 330, 36, 9),
        item('invoice-title', 'invoice_title', 438, 46, 308, 36, 24, True, 'right'),
        item('invoice-number', 'invoice_number', 438, 84, 308, 22, 13, True, 'right'),
        item('invoice-reference', 'invoice_reference', 438, 108, 308, 20, 10, False, 'right'),
        item('invoice-date', 'invoice_date', 438, 130, 308, 20, 10, False, 'right'),
        item('due-date', 'due_date', 438, 152, 308, 20, 10, False, 'right'),
        item('customer-label', 'customer_label', 48, 236, 330, 18, 9, True),
        item('customer-company', 'customer_company', 48, 257, 330, 24, 13, True),
        item('customer-contact', 'customer_contact', 48, 282, 330, 20, 10),
        item('customer-address', 'customer_address', 48, 303, 330, 40, 10),
        item('order-details', 'order_summary', 48, 375, 698, 245, 10),
        item('invoice-note', 'invoice_note', 48, 640, 698, 54, 9),
        item('subtotal', 'subtotal', 430, 735, 316, 22, 11, False, 'right'),
        item('gst-total', 'gst_total', 430, 758, 316, 22, 10, False, 'right'),
        {**item('total-highlight', '', 425, 784, 321, 43), 'type': 'shape', 'background': '#edf2f4', 'border_width': 0},
        item('invoice-total', 'invoice_total', 438, 793, 296, 26, 15, True, 'right'),
        item('payment-heading', 'payment_heading', 48, 862, 698, 22, 11, True),
        item('payment-details', 'payment_details', 48, 888, 698, 72, 10),
        item('footer', 'footer', 48, 1014, 698, 54, 9),
    ]


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
    elements = saved.get('elements')
    if not isinstance(elements, list):
        elements = default_invoice_canvas_elements()
    allowed_fields = {'company_name', 'company_gst', 'company_address', 'invoice_title', 'invoice_number', 'invoice_reference', 'invoice_date', 'due_date',
                      'customer_label', 'customer_company', 'customer_contact', 'customer_address', 'customer_phone', 'customer_email',
                      'order_summary', 'order_id', 'description', 'site_address', 'order_total', 'gst', 'amount_due', 'subtotal',
                      'gst_total', 'invoice_total', 'payment_heading', 'payment_details', 'invoice_note', 'footer'}
    elements = [element for element in elements if isinstance(element, dict) and element.get('type') in ('text', 'field', 'shape', 'logo')
                and (element.get('type') != 'field' or element.get('field') in allowed_fields)]
    return {'blocks': ordered, 'elements': elements}


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
    labels, settings = m['labels'], m['field_settings']
    names = {'order_id':'order_id','description':'description','site_address':'site_address','order_total':'order_total','gst':'gst','amount':'amount_due'}
    return [(key, labels[names[key]]) for key in settings.get('item_columns', []) if key in names]


def _invoice_table_cells(m, row):
    keys = {'order_id':'order','description':'description','site_address':'site','order_total':'order_total','gst':'gst_rate','amount':'amount'}
    return [(key, row.get(keys[key], '')) for key, _ in _invoice_table_columns(m)]


def _invoice_amount(m, value):
    amount = Decimal(str(value or '0').replace(',', ''))
    sign = '-' if amount < 0 else ''
    return f"{sign}{m['currency']} {money(abs(amount))}"


def _invoice_subtotal(m):
    return money(Decimal(str(m['due']).replace(',', '')) - Decimal(str(m['gst']).replace(',', '')))


def _canvas_field_value(m, key):
    labels = m['labels']
    settings = m['field_settings']
    visibility = {
        'company_name': settings.get('company_name', True), 'company_gst': settings.get('company_gst', True),
        'company_address': settings.get('company_address', True), 'customer_company': settings.get('customer_company', True),
        'customer_contact': settings.get('customer_contact', True), 'customer_address': settings.get('customer_address', True),
        'customer_phone': settings.get('customer_phone', False), 'customer_email': settings.get('customer_email', False),
        'customer_label': any(settings.get(name, False) for name in ('customer_company', 'customer_contact', 'customer_address', 'customer_phone', 'customer_email')),
        'invoice_title': settings.get('invoice_title', True), 'invoice_number': settings.get('invoice_number', True),
        'invoice_reference': settings.get('invoice_reference', True), 'invoice_date': settings.get('invoice_date', True), 'due_date': settings.get('due_date', True),
        'order_summary': bool(settings.get('item_columns', [])),
        'order_id': 'order_id' in settings.get('item_columns', []), 'description': 'description' in settings.get('item_columns', []),
        'site_address': 'site_address' in settings.get('item_columns', []), 'order_total': 'order_total' in settings.get('item_columns', []),
        'gst': 'gst' in settings.get('item_columns', []), 'amount_due': 'amount' in settings.get('item_columns', []),
        'subtotal': settings.get('subtotal', True), 'gst_total': settings.get('gst_total', True), 'invoice_total': settings.get('invoice_total', True),
        'payment_heading': settings.get('payment_heading', True), 'payment_details': bool(m['payment']),
    }
    if key in visibility and not visibility[key]:
        return ''
    values = {
        'company_name': m['brand'], 'company_gst': f"{labels['company_gst']} {m['brand_gst']}" if m['brand_gst'] else '',
        'company_address': m['brand_address'], 'invoice_title': labels['invoice_title'],
        'invoice_number': f"{labels['invoice_number']} {m['number']}",
        'invoice_reference': f"{labels['reference']}: {m['reference']}" if m['reference'] else '',
        'invoice_date': f"{labels['invoice_date']}: {m['formatted_date']}",
        'due_date': f"{labels['due_date']}: {m['formatted_due_date']}",
        'customer_label': labels['bill_to'], 'customer_company': m['company'], 'customer_contact': m['contact'],
        'customer_address': m['address'], 'customer_phone': m['customer_phone'], 'customer_email': m['customer_email'],
        'order_id': '\n'.join(row.get('order', '') for row in m['rows'] if row.get('order')),
        'description': '\n'.join(row.get('description', '') for row in m['rows'] if row.get('description')),
        'site_address': '\n'.join(row.get('site', '') for row in m['rows'] if row.get('site')),
        'order_total': '\n'.join(f"{m['currency']} {row['order_total']}" for row in m['rows'] if row.get('order_total')),
        'gst': '\n'.join(row.get('gst_rate', '') for row in m['rows'] if row.get('gst_rate')),
        'amount_due': '\n'.join(f"{m['currency']} {row['amount']}" for row in m['rows'] if row.get('amount')),
        'order_summary': '\n'.join(' · '.join(value for value in (row.get('order'), row.get('description'), row.get('site')) if value)
                                    + (f"    {m['currency']} {row['amount']}" if row.get('amount') else '') for row in m['rows']),
        'subtotal': f"{labels['subtotal']}: {m['currency']} {_invoice_subtotal(m)}",
        'gst_total': f"{labels['gst_included']} ({m['gst_rate']}): {m['currency']} {m['gst']}",
        'invoice_total': f"{labels['total']}: {m['currency']} {m['due']}",
        'payment_heading': labels['payment_instruction'],
        'payment_details': '\n'.join(f'{label}: {value}' for label, value in m['payment']),
        'invoice_note': m['basis'], 'footer': m['footer'],
    }
    return str(values.get(key, '') or '')


def _canvas_html(m):
    elements = (m.get('design') or {}).get('elements') or []
    pieces = []
    for element in elements:
        kind = element.get('type', 'text')
        x, y = int(element.get('x', 0)), int(element.get('y', 0))
        width, height = int(element.get('width', 200)), int(element.get('height', 30))
        style = (f'left:{x}px;top:{y}px;width:{width}px;height:{height}px;box-sizing:border-box;'
                 f'font-family:"{element.get("font_family", "Arial")}",sans-serif;font-size:{int(element.get("font_size", 12))}px;'
                 f'color:{element.get("color", "#263640")};background:{element.get("background") or "transparent"};'
                 f'border:{int(element.get("border_width", 0))}px solid {element.get("border_color", "#d5dde2")};'
                 f'font-weight:{"700" if element.get("bold") else "400"};font-style:{"italic" if element.get("italic") else "normal"};'
                 f'text-align:{element.get("align", "left")};')
        if kind == 'shape':
            if element.get('shape') == 'line':
                style += f'height:0;border:0;border-top:{max(1,int(element.get("border_width", 1)))}px solid {element.get("border_color", "#d5dde2")};background:transparent;'
            pieces.append(f'<div style="position:absolute;{style}"></div>')
        elif kind == 'logo':
            if m.get('logo'):
                pieces.append(f'<img alt="VERA logo" src="{m["logo"]}" style="position:absolute;{style}object-fit:contain;border:0;background:transparent" />')
        else:
            text = element.get('text', '') if kind == 'text' else _canvas_field_value(m, element.get('field', ''))
            pieces.append(f'<div style="position:absolute;{style}overflow:hidden;white-space:pre-wrap;overflow-wrap:anywhere;padding:2px">{escape(str(text))}</div>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=794,initial-scale=1"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:794px;height:1123px;overflow:hidden!important;background:#fff;font-family:Arial,Helvetica,sans-serif;color:#263640}}
@page{{size:A4;margin:0}}#paper{{position:relative;width:794px;height:1123px;overflow:hidden;background:#fff}}
</style></head><body><main id="paper">{''.join(pieces)}</main></body></html>'''


def _text(m):
    labels = m['labels']
    settings = m['field_settings']
    lines = []
    if settings.get('company_name'): lines.append(m.get('brand') or BRAND)
    if settings.get('company_gst') and m.get('brand_gst'): lines.append(f"{labels['company_gst']} {m['brand_gst']}")
    if settings.get('company_address') and m.get('brand_address'): lines.append(m['brand_address'])
    if settings.get('invoice_title'): lines.append(labels['invoice_title'])
    if settings.get('invoice_number'): lines.append(f"{labels['invoice_number']} {m['number']}")
    if settings.get('invoice_reference') and m.get('reference'): lines.append(f"{labels['reference']}: {m['reference']}")
    if settings.get('invoice_date'): lines.append(f"{labels['invoice_date']}: {m['formatted_date']}")
    if settings.get('due_date'): lines.append(f"{labels['due_date']}: {m['formatted_due_date']}")
    if settings.get('customer_company'): lines.extend(['', f"{labels['bill_to']}: {m['company']}"])
    if settings.get('customer_contact') and m.get('contact'): lines.append(m['contact'])
    if settings.get('customer_address') and m.get('address'): lines.append(m['address'])
    if settings.get('customer_phone') and m.get('customer_phone'): lines.append(m['customer_phone'])
    if settings.get('customer_email') and m.get('customer_email'): lines.append(m['customer_email'])
    lines.append('')
    for r in m['rows']:
        for (key, label), (_, value) in zip(_invoice_table_columns(m), _invoice_table_cells(m, r)):
            if value:
                lines.append(f"    {label}: {_invoice_amount(m, value) if key in ('amount','order_total') else value}")
    lines.append('')
    if settings.get('subtotal'): lines.append(f"{labels['subtotal']}: {m['currency']} {_invoice_subtotal(m)}")
    if settings.get('gst_total'): lines.append(f"{labels['gst_included']} ({m['gst_rate']}): {m['currency']} {m['gst']}")
    if settings.get('invoice_total'): lines.append(f"{labels['total']}: {m['currency']} {m['due']}")
    lines += [m['basis'], '']
    if m['payment']:
        if settings.get('payment_heading'): lines.append(labels['payment_instruction'])
        lines += [f"    {label}: {value}" for label, value in m['payment']] + ['']
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
    if 'elements' in (m.get('design') or {}):
        return _canvas_html(m)
    columns = _invoice_table_columns(m)
    headings = ''.join(f'<td align="right" style="padding:8px 0 8px 12px;border-bottom:2px solid {ink};font-size:11px;color:#64766b">{e(label)}</td>' for _, label in columns)
    rows = ''
    for row in m['rows']:
        cells = []
        for key, value in _invoice_table_cells(m, row):
            shown = _invoice_amount(m, value) if key in ('amount','order_total') and value else str(value or '—')
            cells.append(f'<td style="padding:10px 0 10px 12px;border-bottom:1px solid {line};white-space:nowrap">{e(shown)}</td>')
        rows += '<tr>' + ''.join(cells) + '</tr>'
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
            settings = m['field_settings']
            value = (f'<b style="font-size:15px">{e(m["brand"])}</b>' if settings.get('company_name') else '') + (f'<div>{e(labels["company_gst"])} {e(m["brand_gst"])}</div>' if settings.get('company_gst') and m['brand_gst'] else '') + (f'<div>{e(m["brand_address"])}</div>' if settings.get('company_address') and m['brand_address'] else '')
            value = f'<div style="text-align:{align};font-size:12px;line-height:1.55;color:#52636d;margin-bottom:12px">{value}</div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'heading':
            settings = m['field_settings']
            reference = f'<div>{e(labels["reference"])}: {e(m["reference"])}</div>' if settings.get('invoice_reference') and m['reference'] else ''
            title = f'<strong style="font-size:23px;color:{accent}">{e(labels["invoice_title"])}</strong>' if settings.get('invoice_title') else ''
            number = f'<div>{e(labels["invoice_number"])} {e(m["number"])}</div>' if settings.get('invoice_number') else ''
            invoice_date_text = f'{e(labels["invoice_date"])}: {e(m["formatted_date"])}' if settings.get('invoice_date') else ''
            due_date_text = f'{e(labels["due_date"])}: {e(m["formatted_due_date"])}' if settings.get('due_date') else ''
            value = f'<div style="text-align:{align};padding:10px 0;border-bottom:1px solid {line};margin-bottom:14px">{title}{number}{reference}<small>{invoice_date_text}{" · " if invoice_date_text and due_date_text else ""}{due_date_text}</small></div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'bill_to':
            settings = m['field_settings']
            parts = [f'<small>{e(labels["bill_to"])}</small>']
            if settings.get('customer_company') and m['company']: parts.append(f'<strong>{e(m["company"])}</strong>')
            if settings.get('customer_contact') and m['contact']: parts.append(e(m['contact']))
            if settings.get('customer_address') and m['address']: parts.append(e(m['address']))
            if settings.get('customer_phone') and m['customer_phone']: parts.append(e(m['customer_phone']))
            if settings.get('customer_email') and m['customer_email']: parts.append(e(m['customer_email']))
            value = '<br>'.join(parts)
            value = f'<div style="text-align:{align};padding:12px;background:#f5f7f8;border-radius:7px;margin-bottom:14px">{value}</div>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'order_lines':
            value = f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px"><tr>{headings}</tr>{rows}</table>'
            sections.append(value); area_sections[area].append(value)
        elif bid == 'totals':
            settings = m['field_settings']; parts=[]
            if settings.get('subtotal'): parts.append(f'<div>{e(labels["subtotal"])}: {e(m["currency"])} {_invoice_subtotal(m)}</div>')
            if settings.get('gst_total'): parts.append(f'<div>{e(labels["gst_included"])} ({e(m["gst_rate"])}): {e(m["currency"])} {e(m["gst"])}</div>')
            if settings.get('invoice_total'): parts.append(f'<strong style="font-size:21px;color:{accent}">{e(labels["total"])}: {e(m["currency"])} {e(m["due"])}</strong>')
            value = f'<div style="text-align:{align};padding:12px;background:#edf2f4;border-radius:7px;margin-bottom:14px">{"".join(parts)}</div>'
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


def _render_canvas_pdf(m):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Paragraph
    try:
        pdfmetrics.getFont('STSong-Light')
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    page_width, page_height = A4
    sx, sy = page_width / 794, page_height / 1123
    font_families = {'Arial': 'Helvetica', 'Verdana': 'Helvetica', 'Georgia': 'Times-Roman', 'Times New Roman': 'Times-Roman', 'Courier New': 'Courier'}
    for element in (m.get('design') or {}).get('elements') or []:
        x, y = int(element.get('x', 0)) * sx, page_height - int(element.get('y', 0)) * sy
        width, height = int(element.get('width', 200)) * sx, int(element.get('height', 30)) * sy
        kind = element.get('type', 'text')
        if kind == 'shape':
            if element.get('shape') == 'line':
                page.setStrokeColor(colors.HexColor(element.get('border_color', '#d5dde2')))
                page.setLineWidth(max(1, int(element.get('border_width', 1))))
                page.line(x, y, x + width, y)
            else:
                border_width = int(element.get('border_width', 0))
                page.setLineWidth(border_width or 0.1)
                page.setStrokeColor(colors.HexColor(element.get('border_color', '#d5dde2')))
                if element.get('background'):
                    page.setFillColor(colors.HexColor(element['background']))
                else:
                    page.setFillColor(colors.white)
                page.rect(x, y - height, width, height, fill=1 if element.get('background') else 0, stroke=1 if border_width else 0)
            continue
        if kind == 'logo':
            if m.get('logo'):
                page.drawImage(ImageReader(io.BytesIO(base64.b64decode(m['logo'].split(',', 1)[1]))), x, y - height,
                               width=width, height=height, preserveAspectRatio=True, anchor='c', mask='auto')
            continue
        value = element.get('text', '') if kind == 'text' else _canvas_field_value(m, element.get('field', ''))
        if not value:
            continue
        base_font = font_families.get(element.get('font_family', 'Arial'), 'Helvetica')
        font_name = {'Helvetica': 'Helvetica-Bold', 'Times-Roman': 'Times-Bold', 'Courier': 'Courier-Bold'}.get(base_font, base_font) if element.get('bold') else base_font
        if element.get('italic'):
            suffix = '-BoldItalic' if element.get('bold') else '-Italic'
            font_name = {'Helvetica': 'Helvetica' + ('-BoldOblique' if element.get('bold') else '-Oblique'),
                         'Times-Roman': 'Times' + suffix, 'Courier': 'Courier' + ('-BoldOblique' if element.get('bold') else '-Oblique')}[base_font]
        safe = escape(str(value)).replace('\n', '<br/>')
        safe = _CJK.sub(lambda match: f'<font name="STSong-Light">{match.group(1)}</font>', safe)
        size = int(element.get('font_size', 12)) * .75
        style = ParagraphStyle('canvas_element', fontName=font_name, fontSize=size, leading=size * 1.25,
                               textColor=colors.HexColor(element.get('color', '#263640')),
                               alignment={'left': 0, 'center': 1, 'right': 2}.get(element.get('align'), 0), splitLongWords=1)
        para = Paragraph(safe, style)
        para.wrapOn(page, max(1, width - 6), max(1, height - 4))
        if element.get('background'):
            page.setFillColor(colors.HexColor(element['background']))
            page.rect(x, y - height, width, height, fill=1, stroke=0)
        border_width = int(element.get('border_width', 0))
        if border_width:
            page.setStrokeColor(colors.HexColor(element.get('border_color', '#d5dde2')))
            page.setLineWidth(border_width)
            page.rect(x, y - height, width, height, fill=0, stroke=1)
        para.drawOn(page, x + 3, y - height + max(2, (height - para.height) / 2))
    page.showPage()
    page.save()
    return buffer.getvalue()


def render_pdf(m):
    """A4 invoice PDF rendered from the same movable elements as the HTML invoice."""
    if 'elements' in (m.get('design') or {}):
        return _render_canvas_pdf(m)
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
            settings=m['field_settings']; details=[]
            if settings.get('company_name'): details.append(para(m['brand'], 12, True, '#405969', align))
            if settings.get('company_gst') and m['brand_gst']:
                details.append(para(labels['company_gst'] + ' ' + m['brand_gst'], 8, color='#64766b', align=align))
            if settings.get('company_address') and m['brand_address']:
                details.append(para(m['brand_address'], 8, color='#64766b', align=align))
            out += details + [Spacer(1, 3 * mm)]
        elif bid == 'heading':
            settings=m['field_settings']
            if settings.get('invoice_title'): out.append(para(labels['invoice_title'], 21, True, '#405969', align))
            if settings.get('invoice_number'): out.append(para(f"{labels['invoice_number']} {m['number']}", 10, align=align))
            if settings.get('invoice_reference') and m['reference']: out.append(para(f"{labels['reference']}: {m['reference']}", 9, align=align))
            if settings.get('invoice_date'): out.append(para(f"{labels['invoice_date']}: {m['formatted_date']}", 8, color='#64766b', align=align))
            if settings.get('due_date'): out.append(para(f"{labels['due_date']}: {m['formatted_due_date']}", 8, color='#64766b', align=align))
            out.append(Spacer(1, 4 * mm))
        elif bid == 'bill_to':
            settings=m['field_settings']; out.append(para(labels['bill_to'], 8, True, '#64766b'))
            if settings.get('customer_company') and m['company']: out.append(para(m['company'], 11, True))
            if settings.get('customer_contact') and m['contact']: out.append(para(m['contact'], 8, color='#64766b'))
            if settings.get('customer_address') and m['address']: out.append(para(m['address'], 8, color='#64766b'))
            if settings.get('customer_phone') and m['customer_phone']: out.append(para(m['customer_phone'], 8, color='#64766b'))
            if settings.get('customer_email') and m['customer_email']: out.append(para(m['customer_email'], 8, color='#64766b'))
            out.append(Spacer(1, 5 * mm))
        elif bid == 'order_lines':
            columns = _invoice_table_columns(m)
            item_width = max(45 * mm, width - 25 * mm * (len(columns)-1))
            widths = [item_width] + [(width - item_width) / (len(columns)-1)] * (len(columns)-1) if len(columns)>1 else [width]
            data = [[para(label, 8, True, '#64766b', 'left' if index==0 else 'right') for index,(_,label) in enumerate(columns)]]
            for row in m['rows']:
                cells=[]
                for index,(key,_) in enumerate(columns):
                    value=dict(_invoice_table_cells(m,row)).get(key,'')
                    text=_invoice_amount(m,value) if key in ('amount','order_total') and value else str(value or '—')
                    cells.append(para(text,9,align='left' if index==0 else 'right'))
                data.append(cells)
            table = Table(data, colWidths=widths, repeatRows=1)
            table.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,0),1,ink),('LINEBELOW',(0,1),(-1,-1),.4,colors.HexColor('#dce4e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
            out += [table, Spacer(1, 4 * mm)]
        elif bid == 'totals':
            settings=m['field_settings']; totals=[]
            if settings.get('subtotal'): totals.append([para(labels['subtotal'], 9), para(f"{m['currency']} {_invoice_subtotal(m)}", 9, align='right')])
            if settings.get('gst_total'): totals.append([para(f"{labels['gst_included']} ({m['gst_rate']})", 8, color='#64766b'), para(f"{m['currency']} {m['gst']}", 8, color='#64766b', align='right')])
            if settings.get('invoice_total'): totals.append([para(labels['total'], 11, True, '#405969'), para(f"{m['currency']} {m['due']}", 14, True, '#405969', 'right')])
            if not totals: continue
            table = Table(totals, colWidths=[(width / 2) * .65, (width / 2) * .35])
            table.setStyle(TableStyle([('LINEABOVE',(0,-2),(-1,-2),1,accent),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
            out += [table, Spacer(1, 4 * mm)]
        elif bid == 'payment' and m['payment']:
            if m['field_settings'].get('payment_heading'): out.append(para(labels['payment_instruction'], 8, True, '#64766b', align))
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
            table = Table([[left or [para('', 8)], right or [para('', 8)]]], colWidths=[width / 2, width / 2])
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),5 * mm),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
            story.extend([table, Spacer(1, 5 * mm)])
    add_pair('top_left', 'top_right')
    add_pair('middle_left', 'middle_right')
    add_full('items')
    add_pair('bottom_left', 'bottom_right')
    add_full('footer')
    doc.build(story)
    return buffer.getvalue()
