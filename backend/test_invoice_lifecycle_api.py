"""Isolated invoice lifecycle API regression. No production data or SMTP."""
import json
import os
import tempfile
from unittest.mock import patch

with tempfile.TemporaryDirectory() as folder:
    os.environ.update(VERA_DB_BACKEND='sqlite', VERA_DB=os.path.join(folder, 'invoices.db'), VERA_STORAGE_BACKEND='local')
    import service
    from fastapi.testclient import TestClient
    staff = TestClient(service.app)

    def post(path, body=None, code=200):
        response = staff.post('/api/' + path, json=body)
        assert response.status_code == code, (path, response.status_code, response.text)
        return response.json()

    token = post('auth/login', {'username': 'dylan', 'password': os.getenv('VERA_DEMO_PASSWORD', 'vera-demo')})['token']
    staff.headers['Authorization'] = 'Bearer ' + token
    customer = post('operations/customers', {'company': 'Lifecycle Test', 'contact_name': 'Test', 'email': 'lifecycle@example.invalid',
                    'username': 'lifecycle@example.invalid', 'password': 'test-password', 'customer_code': 'LC', 'customer_type': 'wholesale'})
    cid = customer['customer_id']

    def manual(key):
        return post('operations/invoices/manual', {'customer_id': cid, 'operation_key': key,
                    'items': [{'description': 'Installation', 'amount': '115.00'}]})

    first = manual('lifecycle-manual-001')
    assert first['invoice_number'].startswith('DRAFT-') and not first.get('fixed_number')
    preview = staff.get('/api/operations/invoices/' + first['id'] + '/mail-preview').json()
    assert 'DRAFT INVOICE' in preview['html'] and 'Assigned when invoice is issued' in preview['html']
    issued = post('operations/invoices/' + first['id'] + '/issue')
    assert issued['fixed_number'] == 'INV-00001'
    assert post('operations/invoices/' + first['id'] + '/issue')['fixed_number'] == 'INV-00001'
    assert 'Payment reference: INV-00001' in staff.get('/api/operations/invoices/' + first['id'] + '/mail-preview').json()['body']
    post('operations/invoices/' + first['id'] + '/delete-draft', {'note': 'Test deletion'}, 409)
    void = post('operations/invoices/' + first['id'] + '/void', {'note': 'Test cancellation'})
    assert void['fixed_number'] == 'INV-00001' and void['status'] == 'void'
    post('operations/invoices/' + first['id'] + '/issue', code=409)
    post('operations/invoices/' + first['id'] + '/send', code=409)
    post('operations/invoices/' + first['id'] + '/received', {'note': 'Rejected payment'}, 409)
    draft = manual('lifecycle-manual-002')
    post('operations/invoices/' + draft['id'] + '/delete-draft', {'note': 'Test removal'})
    assert draft['id'] not in [invoice['id'] for invoice in staff.get('/api/operations/invoices').json()]
    following = manual('lifecycle-manual-003')
    assert post('operations/invoices/' + following['id'] + '/issue')['fixed_number'] == 'INV-00002'
    with patch('email_service.configuration', return_value=({'configured': False, 'mode': 'live', 'delivery_enabled': False}, None)):
        assert post('operations/invoices/' + following['id'] + '/send')['fixed_number'] == 'INV-00002'
        assert post('operations/invoices/' + following['id'] + '/send')['fixed_number'] == 'INV-00002'

    oid = 'lifecycle-order'
    order = {'id': oid, 'customer_id': cid, 'company': 'Lifecycle Test', 'project_name': 'Test', 'order_number': 'LC-TEST',
             'order_number_confirmed': True, 'status': 'pending_review', 'payment_status': 'deposit_unpaid', 'total': '1150.00',
             'deposit': '690.00', 'tax_rate': '0.15', 'tax_basis': 'GST inclusive', 'currency': 'NZD', 'lines': [], 'history': [], 'created_at': service.now()}
    with service.db() as c:
        c.execute('INSERT INTO operations_records VALUES(?,?,?,?)', (oid, 'project', cid, json.dumps(order)))
    deposit = post('operations/orders/' + oid + '/review', {'confirm_order_number': True})['invoices'][0]
    assert not deposit.get('fixed_number')
    post('operations/invoices/' + deposit['id'] + '/delete-draft', {'note': 'Return for review'})
    reviewed = post('operations/orders/' + oid + '/review', {'confirm_order_number': True})
    replacement = next(invoice for invoice in reviewed['invoices'] if invoice['status'] != 'void')
    assert replacement['id'] != deposit['id']
    post('operations/invoices/' + replacement['id'] + '/issue')
    post('operations/invoices/' + replacement['id'] + '/void', {'note': 'Correct invoice'})
    reviewed = post('operations/orders/' + oid + '/review', {'confirm_order_number': True})
    current = next(invoice for invoice in reviewed['invoices'] if invoice['status'] == 'draft')
    assert current['id'] != replacement['id']
    paid = post('operations/orders/' + oid + '/deposit-received')
    active = next(invoice for invoice in paid['invoices'] if invoice['id'] == current['id'])
    assert active['fixed_number'] == 'INV-00004' and active['payment_status'] == 'received'
    post('operations/invoices/' + current['id'] + '/void', {'note': 'Cannot cancel paid'}, 409)
    lookup = staff.get('/api/operations/invoices/lookup', params={'reference': 'INV-00004'})
    assert lookup.status_code == 200 and lookup.json()['id'] == current['id']
    with service.db() as c:
        order = json.loads(c.execute('SELECT data FROM operations_records WHERE id=?', (oid,)).fetchone()['data'])
        order['status'] = 'ready'
        c.execute('UPDATE operations_records SET data=? WHERE id=?', (json.dumps(order), oid))
    rebate = post('operations/rebates', {'customer_id': cid, 'source_order_ids': [oid], 'month': '2026-01',
                  'amount': '50.00', 'currency': 'NZD', 'evidence': 'Synthetic confirmed rebate'})
    balance_body = {'order_ids': [oid], 'operation_key': 'lifecycle-balance-001', 'billing_basis': 'all_arrived_remaining_total',
                    'rules_evidence': 'Confirmed synthetic rules', 'rebate_ids': [rebate['id']],
                    'additional_items': [{'description': 'Delivery', 'amount': '115.00'}]}
    balance = post('operations/settlements', balance_body)
    assert balance['amount'] == '525.00' and not balance.get('fixed_number')
    post('operations/invoices/' + balance['id'] + '/delete-draft', {'note': 'Discard draft'})
    available = next(row for row in staff.get('/api/operations/rebates').json()['credits'] if row['id'] == rebate['id'])
    assert available['remaining'] == '50.00' and available['used'] == '0.00' and not available['allocations']
    balance = post('operations/settlements', {**balance_body, 'operation_key': 'lifecycle-balance-002'})
    issued_balance = post('operations/invoices/' + balance['id'] + '/issue')
    post('operations/invoices/' + balance['id'] + '/void', {'note': 'Cancel balance'})
    available = next(row for row in staff.get('/api/operations/rebates').json()['credits'] if row['id'] == rebate['id'])
    assert available['remaining'] == '50.00' and available['used'] == '0.00'
    assert 'VOID INVOICE' in staff.get('/api/operations/invoices/' + balance['id'] + '/mail-preview').json()['html']
    for invoice in (following, issued_balance):
        with service.db() as c:
            c.execute('INSERT INTO invoice_number_audit VALUES(?,?,?,?,?)', (invoice['id'], 'INV-OLD', invoice['fixed_number'] if 'fixed_number' in invoice else 'INV-00002', 'fixture', service.now()))
    assert staff.get('/api/operations/invoices/lookup', params={'reference': 'INV-OLD'}).status_code == 409
    print('PASS invoice lifecycle API: drafts, issue, retries, void/delete, deposit replacements, payments and reference lookup')
