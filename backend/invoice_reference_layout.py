"""Invoice AA0013 layout. HTML and PDF share the same A4 drawing instructions."""
import base64
import io
import textwrap
from datetime import date
from html import escape

REFERENCE_PAYMENT = [('Bank', 'ASB'), ('Account Name', 'VCG Group Ltd'),
                     ('Account Number', '12-3233-0714884-00'), ('GST', '139-745-388')]


def short_date(value):
    try:
        parsed = date.fromisoformat(str(value)[:10])
        return f'{parsed.day}/{parsed.month}/{parsed.year}'
    except ValueError:
        return str(value or '')


def paginated_rows(model):
    pages, current, used = [], [], 0
    for row in model['rows']:
        # A row retains its complete description; subsequent rows move down together.
        lines = textwrap.wrap(str(row.get('item') or row.get('description') or ''), 56) or ['']
        for offset in range(0, len(lines), 18):
            part = lines[offset:offset + 18]
            height = max(18, len(part) * 18)
            if current and used + height > 342:
                pages.append(current)
                current, used = [], 0
            last = offset + 18 >= len(lines)
            current.append((row, '\n'.join(part), height, last))
            used += height
    pages.append(current)
    return pages


def drawing(model, rows, final, page_number, page_count):
    ops = []
    def text(x, y, width, height, value, size=14, bold=False, align='left'):
        ops.append(dict(type='text', x=x, y=y, width=width, height=height, value=str(value or ''),
                        size=size, bold=bold, align=align))
    def rect(x, y, width, height):
        ops.append(dict(type='rect', x=x, y=y, width=width, height=height))
    def line(x, y, width):
        ops.append(dict(type='line', x=x, y=y, width=width, height=0))
    ops.append(dict(type='logo', x=25, y=91, width=220, height=67))
    text(475, 105, 281, 42, model.get('document_title', 'TAX INVOICE'), 32, True, 'right')
    text(25, 161, 360, 18, 'BILL TO', 14, True)
    rect(23, 180, 377, 90)
    text(35, 202, 353, 46, model['company'], 18, True, 'center')
    for y, label, value in [(185, 'Invoice No.', model['number']),
                             (215, 'Invoice Date', short_date(model['date'])),
                             (245, 'Due Date', short_date(model['due_date']))]:
        text(421, y, 95, 20, label, 14, True, 'center')
        text(530, y, 228, 20, value, 14, True, 'right')
    rect(23, 288, 738, 400)
    for x, width, label in [(25, 374, 'Item'), (402, 95, 'Unit Price'), (499, 84, 'Quantity'),
                            (584, 55, 'GST'), (644, 112, 'Total')]:
        text(x, 289, width, 22, label, 15, True, 'center')
    y = 326
    for row, description, height, show_amount in rows:
        text(25, y, 374, height, description, 14)
        if show_amount:
            text(587, y, 47, 18, row.get('gst_rate', model['gst_rate']), 14, False, 'center')
            amount = row.get('amount', '')
            text(642, y, 20, 18, '-$' if str(amount).startswith('-') else '$', 14)
            text(666, y, 88, 18, str(amount).lstrip('-'), 14, False, 'right')
        y += height
    if final:
        for y, label, value in [(690, 'Subtotal', model['due']), (711, 'incl. GST', model['gst'])]:
            text(501, y, 137, 20, label, 15, False, 'right')
            text(648, y, 16, 20, '$', 15)
            text(667, y, 87, 20, value, 15, False, 'right')
        line(497, 732, 264)
        line(497, 734, 264)
        text(502, 739, 136, 26, 'Total', 18, True, 'right')
        text(648, 739, 16, 26, '$', 18, True)
        text(667, 739, 87, 26, model['due'], 18, True, 'right')
        payment = model.get('payment') or REFERENCE_PAYMENT
        payment_height = max(127, 49 + len(payment) * 18)
        rect(23, 790, 738, payment_height)
        text(25, 791, 700, 21, 'Payment Instruction', 14, True)
        payment = model.get('payment') or REFERENCE_PAYMENT
        for index, (label, value) in enumerate(payment):
            text(25, 826 + index * 18, 728, 18, f'{label}: {value}', 14)
        if model.get('reference_footer'):
            text(25, 802 + payment_height, 728, 48, model['reference_footer'], 11)
    if page_count > 1:
        text(600, 1040, 154, 20, f'Page {page_number} of {page_count}', 11, False, 'right')
    return ops


def render_html(model):
    papers = []
    pages = paginated_rows(model)
    for number, rows in enumerate(pages, 1):
        parts = []
        for op in drawing(model, rows, number == len(pages), number, len(pages)):
            style = f'position:absolute;left:{op["x"]}px;top:{op["y"]}px;width:{op["width"]}px;height:{op["height"]}px;'
            if op['type'] == 'rect':
                parts.append(f'<div style="{style}border:1.3px solid black"></div>')
            elif op['type'] == 'line':
                parts.append(f'<div style="{style}border-top:.7px solid black"></div>')
            elif op['type'] == 'logo':
                if model.get('logo'):
                    parts.append(f'<img alt="VERA" src="{model["logo"]}" style="{style}object-fit:contain"/>')
            else:
                style += f'font-size:{op["size"]}px;font-weight:{700 if op["bold"] else 400};text-align:{op["align"]};'
                parts.append(f'<div class="text" style="{style}">{escape(op["value"])}</div>')
        papers.append('<main class="paper">' + ''.join(parts) + '</main>')
    return '''<!doctype html><html><head><meta charset="utf-8"><style>
    *{box-sizing:border-box}html,body{margin:0;padding:0;background:white;color:black;font-family:"Times New Roman",serif}
    .paper{position:relative;width:794px;height:1123px;background:white;break-after:page;overflow:hidden}
    .text{display:flex;flex-direction:column;justify-content:center;white-space:pre-wrap;line-height:1.2;overflow-wrap:anywhere}
    @page{size:A4;margin:0}.paper:last-child{break-after:auto}
    </style></head><body>''' + ''.join(papers) + '</body></html>'


def render_pdf(model):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Paragraph
    result = io.BytesIO()
    page = canvas.Canvas(result, pagesize=A4, pageCompression=1)
    page.setTitle(f'Tax invoice {model["number"]}')
    scale_x, scale_y = A4[0] / 794, A4[1] / 1123
    pages = paginated_rows(model)
    for number, rows in enumerate(pages, 1):
        for op in drawing(model, rows, number == len(pages), number, len(pages)):
            x, y = op['x'] * scale_x, A4[1] - op['y'] * scale_y
            width, height = op['width'] * scale_x, op['height'] * scale_y
            if op['type'] == 'rect':
                page.setLineWidth(1.3 * scale_x)
                page.rect(x, y - height, width, height, stroke=1, fill=0)
            elif op['type'] == 'line':
                page.setLineWidth(.7 * scale_x)
                page.line(x, y, x + width, y)
            elif op['type'] == 'logo':
                if model.get('logo'):
                    page.drawImage(ImageReader(io.BytesIO(base64.b64decode(model['logo'].split(',', 1)[1]))),
                                   x, y - height, width, height, preserveAspectRatio=True, anchor='c', mask='auto')
            else:
                style = ParagraphStyle('reference', fontName='Times-Bold' if op['bold'] else 'Times-Roman',
                                       fontSize=op['size'] * scale_x, leading=op['size'] * scale_x * 1.2,
                                       alignment={'left': 0, 'center': 1, 'right': 2}[op['align']])
                paragraph = Paragraph(escape(op['value']).replace('\n', '<br/>'), style)
                paragraph.wrapOn(page, width, max(height, 1))
                paragraph.drawOn(page, x, y - (height + paragraph.height) / 2)
        page.showPage()
    page.save()
    return result.getvalue()
