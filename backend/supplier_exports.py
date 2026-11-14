"""Supplier order export helpers."""
from copy import deepcopy
from datetime import date, datetime
import io
import os
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from excel_rules import column


def export_vera_purchase_order(project):
    """Create VERA's compact purchase order using the same fields as order entry."""
    lines = project.get('lines') or []
    if not lines:
        raise ValueError('The order has no window lines to export')

    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('', ns)
    headers = [
        'Window Location / Name', 'Width (mm)', 'DROP (mm)', 'Material / Series',
        'Opening Style', 'Panels', 'Layout Code', 'VT Post', 'HT Post', 'Midrail',
        'Frame', 'Louver Size', 'Colour', 'Control Rod', 'Fitting',
        'Add-ons / Special Request',
    ]
    rows = [
        ['ORDER ID', project.get('order_number') or project.get('project_name') or project.get('id', ''),
         '', 'END CUSTOMER NAME', project.get('end_customer_name') or ''],
        [], headers,
    ]
    option_keys = ('opening_style', 'layout_code', 'vt_post', 'ht_post', 'midrail',
                   'frame', 'louver_size', 'colour', 'control_rod', 'fitting')
    for line in lines:
        options = line.get('options') or {}
        known = set(option_keys) | {'special_request'}
        extra = [f'{key}: {value}' for key, value in options.items() if key not in known and value]
        special = '; '.join(v for v in [options.get('special_request', ''), *extra] if v)
        rows.append([
            line.get('window_name', ''), line.get('width_mm', ''), line.get('height_mm', ''),
            line.get('material') or line.get('product_name') or line.get('source_code') or '',
            options.get('opening_style', ''), line.get('panel_count', 1),
            *[options.get(key, '') for key in option_keys[1:]], special,
        ])

    sheet = ET.Element(f'{{{ns}}}worksheet')
    views = ET.SubElement(sheet, f'{{{ns}}}sheetViews')
    view = ET.SubElement(views, f'{{{ns}}}sheetView', {'workbookViewId': '0', 'showGridLines': '0'})
    ET.SubElement(view, f'{{{ns}}}pane', {'ySplit': '3', 'topLeftCell': 'A4', 'activePane': 'bottomLeft', 'state': 'frozen'})
    cols = ET.SubElement(sheet, f'{{{ns}}}cols')
    widths = [25, 13, 13, 26, 22, 10, 18, 14, 14, 18, 20, 16, 18, 18, 16, 42]
    for index, width in enumerate(widths, 1):
        ET.SubElement(cols, f'{{{ns}}}col', {'min': str(index), 'max': str(index), 'width': str(width), 'customWidth': '1'})
    data = ET.SubElement(sheet, f'{{{ns}}}sheetData')
    for row_index, values in enumerate(rows, 1):
        row = ET.SubElement(data, f'{{{ns}}}row', {'r': str(row_index), 'ht': '32' if row_index <= 3 else '28', 'customHeight': '1'})
        for col_index, value in enumerate(values, 1):
            if value in (None, ''):
                continue
            numeric = row_index > 3 and col_index in (2, 3, 6)
            style = '1' if row_index == 1 else ('2' if row_index == 3 else '0')
            cell = ET.SubElement(row, f'{{{ns}}}c', {
                'r': column(col_index) + str(row_index), 's': style,
                **({} if numeric else {'t': 'inlineStr'}),
            })
            if numeric:
                ET.SubElement(cell, f'{{{ns}}}v').text = str(value)
            else:
                inline = ET.SubElement(cell, f'{{{ns}}}is')
                ET.SubElement(inline, f'{{{ns}}}t').text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))
    ET.SubElement(sheet, f'{{{ns}}}autoFilter', {'ref': f'A3:P{len(rows)}'})
    ET.SubElement(sheet, f'{{{ns}}}pageMargins', {'left': '0.25', 'right': '0.25', 'top': '0.5', 'bottom': '0.5', 'header': '0.2', 'footer': '0.2'})
    ET.SubElement(sheet, f'{{{ns}}}pageSetup', {'orientation': 'landscape', 'paperSize': '9', 'fitToWidth': '1', 'fitToHeight': '0'})

    styles = f'''<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF465966"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD6DEE3"/></left><right style="thin"><color rgb="FFD6DEE3"/></right><top style="thin"><color rgb="FFD6DEE3"/></top><bottom style="thin"><color rgb="FFD6DEE3"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    package = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="VERA Purchase Order" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': styles,
        'xl/worksheets/sheet1.xml': ET.tostring(sheet, encoding='utf-8'),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in package.items():
            archive.writestr(name, content)
    return output.getvalue()


def export_supplier(project, customer, max_lines=29):
    lines = project.get('lines') or []
    if len(lines) > max_lines:
        raise ValueError(f'Supplier template supports at most {max_lines} window rows')

    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ET.register_namespace('', ns)
    rows = [
        ['', 'Customer Name', customer.get('contact_name', ''), '', '', '', '', 'Type', (customer.get('customer_type') or 'wholesale').title(), '', '', '', '', 'Order Number', project.get('order_number') or project.get('project_name', '')],
        ['', 'Company Name', project.get('company', ''), '', '', '', '', 'Refer By', '', '', '', '', '', '', ''],
        ['', 'Phone', project.get('phone', ''), '', '', '', '', '', '', '', '', '', '', '', ''],
        ['', 'Address', project.get('company_address', ''), '', '', '', '', 'Installed', 'Yes' if project.get('installation_required') else 'No', '', '', '', '', '', ''],
        ['', 'Delivery / site address', project.get('site_address', ''), '', '', '', '', 'Estimated lead time', project.get('lead_time', {}).get('text', '10–12 weeks from order confirmation')],
        ['Blinds', 'Window Location', 'Width\n(mm)', 'Drop\n(mm)', 'Product', '', "Panel\nQ'ty", 'Control Side', '', '', '', 'Bracket Colour', 'Chain Colour', 'Main Colour', 'Bottom Rail Colour', 'In/Out\nFit', 'Special Request'],
        ['Shutters', 'Window Location', 'Width\n(mm)', 'Drop\n(mm)', 'Product', 'Open Method', "Panel\nQ'ty", 'Layout Code', 'VT\nPost', 'HT\nPost', 'Midrail', 'Frame', 'Louver Size', 'Colour', 'Control Rod', 'Fitting', 'Special Request'],
    ]

    shutter_keys = {'opening_style', 'layout_code', 'vt_post', 'ht_post', 'midrail', 'frame', 'louver_size', 'colour', 'control_rod', 'fitting', 'special_request'}
    blind_keys = {'control_side', 'bracket_colour', 'chain_colour', 'colour', 'bottom_rail_colour', 'fitting', 'special_request'}
    for line in lines:
        category = str(line.get('product_category') or '').lower()
        code = str(line.get('source_code') or '').lower()
        is_shutter = category in {'shutter', 'shutters'} or code.startswith('shutters_')
        keys = shutter_keys if is_shutter else blind_keys
        options = line.get('options') or {}
        known = {key: options.get(key, '') for key in keys}
        extra = [f'{key}: {value}' for key, value in options.items() if key not in keys and value]
        special = '; '.join(v for v in [known.get('special_request', ''), *extra] if v)
        if is_shutter:
            values = ['Shutters', line.get('window_name', ''), line.get('width_mm', ''), line.get('height_mm', ''),
                      line.get('source_code') or line.get('product_name') or line.get('product_id', ''),
                      known['opening_style'], line.get('panel_count', 1), known['layout_code'], known['vt_post'],
                      known['ht_post'], known['midrail'], known['frame'], known['louver_size'], known['colour'],
                      known['control_rod'], known['fitting'], special]
        else:
            values = ['Blinds', line.get('window_name', ''), line.get('width_mm', ''), line.get('height_mm', ''),
                      line.get('source_code') or line.get('product_name') or line.get('product_id', ''), '',
                      line.get('panel_count', 1), known['control_side'], '', '', '', known['bracket_colour'],
                      known['chain_colour'], known['colour'], known['bottom_rail_colour'], known['fitting'], special]
        rows.append(values)

    sheet = ET.Element('{'+ns+'}worksheet')
    views = ET.SubElement(sheet, '{'+ns+'}sheetViews')
    view = ET.SubElement(views, '{'+ns+'}sheetView', {'workbookViewId': '0', 'showGridLines': '0'})
    ET.SubElement(view, '{'+ns+'}pane', {'ySplit': '7', 'topLeftCell': 'A8', 'activePane': 'bottomLeft', 'state': 'frozen'})
    cols = ET.SubElement(sheet, '{'+ns+'}cols')
    for index, width in enumerate([12, 24, 14, 14, 24, 20, 12, 20, 16, 16, 16, 20, 20, 20, 22, 20, 48], 1):
        ET.SubElement(cols, '{'+ns+'}col', {'min': str(index), 'max': str(index), 'width': str(width), 'customWidth': '1'})
    data = ET.SubElement(sheet, '{'+ns+'}sheetData')
    for row_index, values in enumerate(rows, 1):
        row = ET.SubElement(data, '{'+ns+'}row', {'r': str(row_index), 'ht': '30', 'customHeight': '1'})
        for col_index, value in enumerate(values, 1):
            if value in (None, ''):
                continue
            numeric = row_index >= 8 and col_index in (3, 4, 7)
            cell = ET.SubElement(row, '{'+ns+'}c', {'r': column(col_index)+str(row_index), **({} if numeric else {'t': 'inlineStr'}), 's': '1' if row_index in (6, 7) else '0'})
            if numeric:
                ET.SubElement(cell, '{'+ns+'}v').text = str(value)
            else:
                inline = ET.SubElement(cell, '{'+ns+'}is')
                ET.SubElement(inline, '{'+ns+'}t').text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))
    ET.SubElement(sheet, '{'+ns+'}pageMargins', {'left': '0.25', 'right': '0.25', 'top': '0.5', 'bottom': '0.5', 'header': '0.2', 'footer': '0.2'})
    ET.SubElement(sheet, '{'+ns+'}pageSetup', {'orientation': 'landscape', 'paperSize': '9', 'fitToWidth': '1', 'fitToHeight': '0'})

    styles = f'''<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF183B2C"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    package = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Order" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': styles,
        'xl/worksheets/sheet1.xml': ET.tostring(sheet, encoding='utf-8'),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in package.items():
            archive.writestr(name, content)
    return output.getvalue()


_XLSX_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_XLSX_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
_DRAWING = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'


def _xlsx_register_namespaces():
    # Preserve the supplier workbook's extension namespace prefixes when the
    # regular-shutter sheet is serialized back into the original package.
    for prefix, uri in (
        ('', _XLSX_MAIN), ('r', _XLSX_REL), ('xdr', _DRAWING),
        ('x14', 'http://schemas.microsoft.com/office/spreadsheetml/2009/9/main'),
        ('mc', 'http://schemas.openxmlformats.org/markup-compatibility/2006'),
        ('x14ac', 'http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac'),
        ('xr', 'http://schemas.microsoft.com/office/spreadsheetml/2014/revision'),
        ('xr2', 'http://schemas.microsoft.com/office/spreadsheetml/2015/revision2'),
        ('xr3', 'http://schemas.microsoft.com/office/spreadsheetml/2016/revision3'),
    ):
        ET.register_namespace(prefix, uri)


def _column_number(reference):
    letters = re.match(r'([A-Z]+)', reference).group(1)
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number


def _shift_ref(reference, insert_at, amount):
    """Shift A1 references at/after the inserted row, preserving $ markers."""
    def shift_cell(match):
        col, row = match.group(1), int(match.group(2))
        return f'{col}{row + amount if row >= insert_at else row}'
    return re.sub(r'(?<![A-Z0-9_])\$?([A-Z]{1,3})\$?(\d+)', shift_cell, reference)


def _shift_range(reference, insert_at, amount):
    return ':'.join(_shift_ref(part, insert_at, amount) for part in reference.split(':'))


def _cell_text(cell, shared_strings):
    if cell is None:
        return ''
    if cell.attrib.get('t') == 's':
        value = cell.find(f'{{{_XLSX_MAIN}}}v')
        return shared_strings[int(value.text)] if value is not None and value.text else ''
    inline = cell.find(f'{{{_XLSX_MAIN}}}is')
    if inline is not None:
        return ''.join(node.text or '' for node in inline.iter(f'{{{_XLSX_MAIN}}}t'))
    value = cell.find(f'{{{_XLSX_MAIN}}}v')
    return value.text if value is not None and value.text else ''


def _set_cell(row, reference, value, numeric=False, formula=None):
    cell_tag = f'{{{_XLSX_MAIN}}}c'
    cell = next((c for c in row.findall(cell_tag) if c.attrib.get('r') == reference), None)
    if cell is None:
        cell = ET.Element(cell_tag, {'r': reference})
        target_column = _column_number(reference)
        for index, existing in enumerate(row.findall(cell_tag)):
            if _column_number(existing.attrib['r']) > target_column:
                row.insert(list(row).index(existing), cell)
                break
        else:
            row.append(cell)

    cell.attrib.pop('t', None)
    for child in list(cell):
        if child.tag in (f'{{{_XLSX_MAIN}}}v', f'{{{_XLSX_MAIN}}}is', f'{{{_XLSX_MAIN}}}f'):
            cell.remove(child)
    if formula:
        ET.SubElement(cell, f'{{{_XLSX_MAIN}}}f').text = formula
        ET.SubElement(cell, f'{{{_XLSX_MAIN}}}v').text = '0'
    elif value not in (None, ''):
        if numeric:
            ET.SubElement(cell, f'{{{_XLSX_MAIN}}}v').text = str(value)
        else:
            cell.set('t', 'inlineStr')
            inline = ET.SubElement(cell, f'{{{_XLSX_MAIN}}}is')
            text_node = ET.SubElement(inline, f'{{{_XLSX_MAIN}}}t')
            text_node.text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))
            if text_node.text != text_node.text.strip():
                text_node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')


def _parse_business_date(value):
    if not value:
        return ''
    if isinstance(value, (datetime, date)):
        return value.strftime('%d/%m/%Y')
    text = str(value).strip()
    if not text:
        return ''
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        return parsed.strftime('%d/%m/%Y')
    except ValueError:
        return text[:10]


def _regular_shutter_rows(project):
    output = []
    for line in project.get('lines') or []:
        options = line.get('options') or {}
        layout = str(options.get('layout_code') or '')
        material = str(line.get('material') or '')
        is_pvc = 'pvc' in material.lower()
        frame = options.get('frame') or ''
        values = {
            'B': line.get('window_name', ''),
            'C': line.get('width_mm', ''),
            'D': line.get('height_mm', ''),
            'E': options.get('fitting', ''),
            'F': options.get('louver_size', ''),
            'G': material,
            'H': options.get('colour', ''),
            'I': options.get('midrail', ''),
            'J': layout,
            'K': line.get('panel_count', 1),
            'L': '' if is_pvc else frame,
            'M': frame if is_pvc else '',
            'N': '',
            'O': options.get('control_rod', ''),
            'P': '',
            'Q': 'Hinged',
            'R': 'Standard',
            'S': '',
            'T': '', 'U': '', 'V': '', 'W': '', 'X': '', 'Y': '',
            'Z': '25.4',
            'AA': len(re.findall('T', layout, flags=re.IGNORECASE)),
            'AB': '',
        }
        output.append(values)
    return output


def export_iswell(project):
    """Fill ISWELL's original Excel form while retaining its workbook package."""
    template_name = 'iswell_order_form.xlsx'
    candidates = [
        Path(__file__).resolve().parent / 'templates' / template_name,
        Path.cwd() / 'templates' / template_name,
        Path.cwd() / 'backend' / 'templates' / template_name,
    ]
    template = next((path for path in candidates if path.is_file()), None)
    if template is None:
        raise FileNotFoundError(f'ISWELL workbook template not found; checked: {", ".join(map(str, candidates))}')
    with template.open('rb') as source:
        package_bytes = source.read()

    _xlsx_register_namespaces()
    main = f'{{{_XLSX_MAIN}}}'
    with zipfile.ZipFile(io.BytesIO(package_bytes), 'r') as original:
        files = {name: original.read(name) for name in original.namelist()}

    workbook = ET.fromstring(files['xl/workbook.xml'])
    relationships = ET.fromstring(files['xl/_rels/workbook.xml.rels'])
    targets = {rel.attrib['Id']: rel.attrib['Target'] for rel in relationships.findall(f'{{{_PKG_REL}}}Relationship')}
    sheet_path = None
    for item in workbook.find(f'{main}sheets'):
        if item.attrib.get('name') == 'PAGE 1-Regular Shutters':
            target = targets[item.attrib[f'{{{_XLSX_REL}}}id']]
            sheet_path = 'xl/' + target.lstrip('/') if not target.startswith('/xl/') else target.lstrip('/')
            break
    if not sheet_path or sheet_path not in files:
        raise ValueError('The ISWELL regular shutters worksheet is missing from its template')

    sheet = ET.fromstring(files[sheet_path])
    data = sheet.find(f'{main}sheetData')
    rows = {int(row.attrib['r']): row for row in data.findall(f'{main}row')}
    source_strings = []
    if 'xl/sharedStrings.xml' in files:
        shared = ET.fromstring(files['xl/sharedStrings.xml'])
        source_strings = [''.join(node.text or '' for node in item.iter(f'{main}t')) for item in shared.findall(f'{main}si')]
    if _cell_text(next((c for c in rows[13].findall(f'{main}c') if c.attrib.get('r') == 'A13'), None), source_strings) != 'Item #':
        raise ValueError('The ISWELL regular shutter table headers do not match the expected template')

    values = _regular_shutter_rows(project)
    first_detail, original_last_detail, footer_start = 14, 34, 35
    original_capacity = original_last_detail - first_detail + 1
    extra_rows = max(0, len(values) - original_capacity)
    if extra_rows:
        # Move the lower T-post measurements/remarks section down, including
        # merged cells and drawing anchors, so no order row overwrites it.
        for row in sorted((r for r in rows if r >= footer_start), reverse=True):
            node = rows[row]
            node.set('r', str(row + extra_rows))
            for cell in node.findall(f'{main}c'):
                cell.set('r', _shift_ref(cell.attrib['r'], footer_start, extra_rows))

        row_template = rows[33]
        last_template = rows[34]
        last_styles = {re.match(r'[A-Z]+', c.attrib['r']).group(0): c.attrib.get('s', '0') for c in last_template.findall(f'{main}c')}
        # The old bottom row becomes a normal detail row when the table grows.
        for target_cell in rows[34].findall(f'{main}c'):
            source_cell = next((c for c in row_template.findall(f'{main}c') if re.match(r'[A-Z]+', c.attrib['r']).group(0) == re.match(r'[A-Z]+', target_cell.attrib['r']).group(0)), None)
            if source_cell is not None and target_cell.attrib.get('s') != source_cell.attrib.get('s'):
                target_cell.set('s', source_cell.attrib.get('s', '0'))

        for row_number in range(footer_start, footer_start + extra_rows):
            clone = deepcopy(row_template)
            clone.set('r', str(row_number))
            for cell in clone.findall(f'{main}c'):
                cell.set('r', _shift_ref(cell.attrib['r'], 33, row_number - 33))
            # Keep the original table's bottom-border styles on the final row.
            if row_number == footer_start + extra_rows - 1:
                for cell in clone.findall(f'{main}c'):
                    col = re.match(r'[A-Z]+', cell.attrib['r']).group(0)
                    if col in last_styles:
                        cell.set('s', last_styles[col])
            data.append(clone)
            rows[row_number] = clone

        # Reorder sheetData after inserting the cloned detail rows.
        ordered = sorted(data.findall(f'{main}row'), key=lambda row: int(row.attrib['r']))
        data[:] = ordered

        for merged in sheet.findall(f'{main}mergeCells/{main}mergeCell'):
            merged.set('ref', _shift_range(merged.attrib['ref'], footer_start, extra_rows))
        dimension = sheet.find(f'{main}dimension')
        if dimension is not None:
            dimension.set('ref', _shift_range(dimension.attrib['ref'], footer_start, extra_rows))
        for element in sheet.iter():
            for key in ('ref', 'sqref'):
                if key in element.attrib and element.tag not in (f'{main}mergeCell', f'{main}dimension'):
                    element.set(key, _shift_range(element.attrib[key], footer_start, extra_rows))

        # Any images anchored in the lower section move with that section.
        for rel in ET.fromstring(files.get(os.path.dirname(sheet_path) + '/_rels/' + os.path.basename(sheet_path) + '.rels', b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')):
            relationship_type = rel.attrib.get('Type', '')
            if relationship_type.endswith('/drawing'):
                drawing_path = os.path.normpath(os.path.join(os.path.dirname(sheet_path), rel.attrib['Target'])).replace('\\', '/')
                if drawing_path in files:
                    drawing = ET.fromstring(files[drawing_path])
                    for row_node in drawing.iter(f'{{{_DRAWING}}}row'):
                        if row_node.text and row_node.text.isdigit() and int(row_node.text) >= footer_start - 1:
                            row_node.text = str(int(row_node.text) + extra_rows)
                    files[drawing_path] = ET.tostring(drawing, encoding='utf-8', xml_declaration=True)
            elif relationship_type.endswith('/vmlDrawing'):
                vml_path = os.path.normpath(os.path.join(os.path.dirname(sheet_path), rel.attrib['Target'])).replace('\\', '/')
                if vml_path in files:
                    vml = ET.fromstring(files[vml_path])
                    for row_node in vml.iter('{urn:schemas-microsoft-com:office:excel}Row'):
                        if row_node.text and row_node.text.isdigit() and int(row_node.text) >= footer_start - 1:
                            row_node.text = str(int(row_node.text) + extra_rows)
                    files[vml_path] = ET.tostring(vml, encoding='utf-8', xml_declaration=True)

        # Move comment cell references in the lower section if present.
        sheet_rels_path = os.path.dirname(sheet_path) + '/_rels/' + os.path.basename(sheet_path) + '.rels'
        if sheet_rels_path in files:
            rel_root = ET.fromstring(files[sheet_rels_path])
            for rel in rel_root:
                if rel.attrib.get('Type', '').endswith('/comments'):
                    comment_path = os.path.normpath(os.path.join(os.path.dirname(sheet_path), rel.attrib['Target'])).replace('\\', '/')
                    if comment_path in files:
                        comments = ET.fromstring(files[comment_path])
                        for comment in comments.iter():
                            if comment.tag.endswith('}comment') and 'ref' in comment.attrib:
                                comment.set('ref', _shift_ref(comment.attrib['ref'], footer_start, extra_rows))
                        files[comment_path] = ET.tostring(comments, encoding='utf-8', xml_declaration=True)

    # The invoice date is the deposit-paid / operational order date. Other
    # header fields intentionally remain blank as agreed with the user.
    date_value = _parse_business_date(project.get('deposit_paid_at') or project.get('order_date'))
    if date_value:
        _set_cell(rows[2], 'Z2', date_value)

    for index, line_values in enumerate(values):
        row_number = first_detail + index
        row = rows.get(row_number)
        if row is None:
            raise ValueError('The ISWELL worksheet could not extend its detail rows')
        _set_cell(row, f'A{row_number}', index + 1, numeric=True)
        for col, value in line_values.items():
            numeric = col in {'C', 'D', 'K', 'AA'}
            _set_cell(row, f'{col}{row_number}', value, numeric=numeric)
        _set_cell(row, f'AC{row_number}', None, formula=f'C{row_number}*D{row_number}/1000000')

    total_row = rows[12]
    _set_cell(total_row, 'AC12', None, formula=f'SUM(AC{first_detail}:AC{first_detail + len(values) - 1})' if values else '0')

    # Preserve all original namespace declarations. In particular, the source
    # worksheet marks several extension namespaces as ignorable by prefix.
    source_sheet_xml = files[sheet_path]
    serialized_sheet = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)
    source_opening = re.search(rb'<worksheet\b[^>]*>', source_sheet_xml)
    generated_opening = re.search(rb'<worksheet\b[^>]*>', serialized_sheet)
    if source_opening and generated_opening:
        declarations = re.findall(rb'xmlns(?::[A-Za-z0-9_]+)?="[^"]+"', source_opening.group(0))
        opening = generated_opening.group(0)
        for declaration in declarations:
            prefix = declaration.split(b'=', 1)[0]
            if not re.search(rb'\b' + re.escape(prefix) + rb'=', opening):
                opening = opening[:-1] + b' ' + declaration + b'>'
        serialized_sheet = serialized_sheet.replace(generated_opening.group(0), opening, 1)
    files[sheet_path] = serialized_sheet

    # Excel will rebuild this cached list when it opens the changed formulas.
    # Keeping the source calculation chain would leave references to old rows.
    files.pop('xl/calcChain.xml', None)
    calc_pr = re.search(rb'<calcPr\b[^>]*?/>', files['xl/workbook.xml'])
    if calc_pr:
        tag = calc_pr.group(0)
        for attribute, value in ((b'calcMode', b'auto'), (b'fullCalcOnLoad', b'1'), (b'forceFullCalc', b'1')):
            if not re.search(rb'\b' + attribute + rb'="[^"]*"', tag):
                tag = tag[:-2] + b' ' + attribute + b'="' + value + b'"/>'
        files['xl/workbook.xml'] = files['xl/workbook.xml'].replace(calc_pr.group(0), tag, 1)
    rels_path = 'xl/_rels/workbook.xml.rels'
    if rels_path in files:
        rels = ET.fromstring(files[rels_path])
        for rel in list(rels):
            if rel.attrib.get('Type', '').endswith('/calcChain'):
                rels.remove(rel)
        files[rels_path] = ET.tostring(rels, encoding='utf-8', xml_declaration=True)
    content_types = ET.fromstring(files['[Content_Types].xml'])
    for override in list(content_types):
        if override.attrib.get('PartName') == '/xl/calcChain.xml':
            content_types.remove(override)
    files['[Content_Types].xml'] = ET.tostring(content_types, encoding='utf-8', xml_declaration=True)

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as generated:
        for name, content in files.items():
            generated.writestr(name, content)
    return output.getvalue()
