"""Saved settings must reach legacy previews, PDFs and delivery without SMTP."""
import io
import json
import os
import tempfile
from unittest.mock import patch

with tempfile.TemporaryDirectory() as folder:
    os.environ.update(VERA_DB_BACKEND='sqlite', VERA_DB=os.path.join(folder, 'payment-settings.db'), VERA_STORAGE_BACKEND='local')
    import service
    from fastapi.testclient import TestClient
    from pypdf import PdfReader

    staff = TestClient(service.app)

    def post(path, body=None):
        response = staff.post('/api/operations/' + path, json=body)
        assert response.status_code == 200, (path, response.status_code, response.text)
        return response.json()

    login = staff.post('/api/auth/login', json={'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})
    staff.headers['Authorization'] = 'Bearer ' + login.json()['token']
    cid = post('customers', {'company': 'Payment Test', 'contact_name': 'Test', 'email': 'payment@example.invalid',
                            'username': 'payment@example.invalid', 'password': 'test-password',
                            'customer_code': 'PT', 'customer_type': 'wholesale'})['customer_id']
    invoices = [post('invoices/manual', {'customer_id': cid, 'operation_key': 'payment-settings-' + kind,
                                       'items': [{'description': 'Test charge', 'amount': '115.00'}]})
                for kind in ('deposit', 'balance', 'manual')]
    # Reproduce imported invoices with a populated dictionary of empty fields.
    with service.db() as c:
        for kind, invoice in zip(('deposit', 'balance', 'manual'), invoices):
            invoice.update(kind=kind, payment_details={'bank_name': '', 'account_name': '', 'account_number': '', 'reference_note': '', 'configured': False},
                           template={'company_name': 'Old Name', 'gst_number': '', 'layout_style': 'reference_aa0013'})
            c.execute('UPDATE operations_records SET data=? WHERE id=?', (json.dumps(invoice), invoice['id']))

    payment = {'bank_name': 'Test Bank', 'account_name': 'Test Account Ltd', 'account_number': '12-0000-0000000-00',
               'reference_note': 'Please quote the invoice number.'}
    template = {'company_name': 'Updated Company', 'gst_number': '123-456-789', 'footer': 'Saved footer', 'layout_style': 'reference_aa0013'}
    post('settings', {'payment_details': payment, 'invoice_template': template})

    def preview(invoice):
        response = staff.get('/api/operations/invoices/' + invoice['id'] + '/mail-preview')
        assert response.status_code == 200, response.text
        return response.json()

    for invoice in invoices:
        model = preview(invoice)
        for value in [*payment.values(), template['gst_number'], template['footer']]:
            assert value in model['html'] and value in model['body'], value
        pdf = staff.get('/api/operations/invoices/' + invoice['id'] + '/pdf')
        assert pdf.status_code == 200
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
        assert all(value in text for value in payment.values()) and template['gst_number'] in text

    # Sending freezes exactly the settings shown in the preview, including PDF.
    invoice = invoices[-1]
    captured = {}

    def fake_send(recipient, subject, body, **kwargs):
        captured.update(body=body, **kwargs)
        return 'test-message'

    with patch('email_service.configuration', return_value=({'configured': True, 'mode': 'live', 'delivery_enabled': True}, None)), patch('email_service.send_email', side_effect=fake_send):
        sent = post('invoices/' + invoice['id'] + '/send')
    assert sent['status'] == 'sent'
    assert all(value in captured['body'] and value in captured['html'] for value in payment.values())
    attachment = captured['attachments'][0][1]
    assert payment['account_number'] in PdfReader(io.BytesIO(attachment)).pages[0].extract_text()
    assert sent['payment_details']['account_number'] == payment['account_number']

    post('settings', {'payment_details': {**payment, 'account_number': '99-0000-0000000-00'},
                      'invoice_template': {**template, 'gst_number': '987-654-321'}})
    old = preview(invoice)
    assert payment['account_number'] in old['html'] and template['gst_number'] in old['html']
    assert '99-0000-0000000-00' not in old['html']
    assert '99-0000-0000000-00' in preview(invoices[0])['html']
    print('PASS legacy payment snapshots: all invoice kinds use saved settings; HTML/PDF/delivery agree; sent snapshots remain stable')
