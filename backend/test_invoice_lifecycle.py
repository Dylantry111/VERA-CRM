"""Invoice reservations and repair policy, in-memory SQLite only."""
import json
import sqlite3
import unittest

import invoice_mail
import invoice_numbering as numbering
from operations import number_invoice


class InvoiceNumbers(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.execute('CREATE TABLE operations_records(id TEXT PRIMARY KEY,kind TEXT,customer_id INTEGER,data TEXT)')

    def tearDown(self):
        self.c.close()

    def put(self, invoice):
        self.c.execute('INSERT INTO operations_records VALUES(?,?,?,?)', (invoice['id'], 'invoice', 1, json.dumps(invoice)))

    def test_drafts_bulk_issue_delete_and_database_constraint(self):
        numbering.migrate(self.c, 'sqlite')
        drafts = [{'id': str(i), 'created_at': '2026-11-14', 'status': 'draft'} for i in range(7)]
        for invoice in drafts:
            number_invoice(self.c, invoice)
        self.assertEqual(len({d['draft_number'] for d in drafts}), 7)
        self.assertTrue(all(not d.get('fixed_number') for d in drafts))
        for invoice in drafts:
            numbering.reserve(self.c, invoice)
            self.put(invoice)
        self.assertEqual(len({d['fixed_number'] for d in drafts}), 7)
        self.assertEqual(numbering.reserve(self.c, drafts[0])['fixed_number'], 'INV-00001')
        self.c.execute('DELETE FROM operations_records WHERE id=?', ('6',))
        next_invoice = {'id': 'next', 'created_at': '2026-11-14'}
        number_invoice(self.c, next_invoice)
        numbering.reserve(self.c, next_invoice)
        self.assertEqual(next_invoice['fixed_number'], 'INV-00008')
        self.assertEqual(invoice_mail.invoice_reference(next_invoice, {}), 'INV-00008')
        self.assertEqual(invoice_mail.invoice_reference({'draft_number': 'DRAFT-00999'}, {}), '')
        with self.assertRaises(sqlite3.IntegrityError):
            self.put({'id': 'bad-import', 'fixed_number': 'INV-00001'})
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute('INSERT INTO invoice_number_registry VALUES(?,?,?,?)', ('INV-00001', 'bad', 100, 'today'))

    def test_repair_seven_paid_imports_preserves_money_and_links(self):
        for i in range(7):
            self.put({'id': str(i), 'fixed_number': 'INV-00025', 'invoice_number': 'INV-00025', 'sequence': 25,
                      'created_at': f'2026-10-{i+10}', 'status': 'draft', 'payment_status': 'received',
                      'amount': '690.00', 'order_ids': [f'order-{i}'], 'received_at': '2026-10-20'})
        numbering.migrate(self.c, 'sqlite')
        saved = [json.loads(row['data']) for row in self.c.execute("SELECT data FROM operations_records WHERE kind='invoice'")]
        self.assertEqual(len({d['fixed_number'] for d in saved}), 7)
        self.assertEqual(len(self.c.execute('SELECT * FROM invoice_number_audit').fetchall()), 6)
        self.assertTrue(all(d['amount'] == '690.00' and d['payment_status'] == 'received' and len(d['order_ids']) == 1 for d in saved))
        numbering.migrate(self.c, 'sqlite')
        self.assertEqual(len(self.c.execute('SELECT * FROM invoice_number_audit').fetchall()), 6)
        self.assertEqual(numbering.reserve(self.c, {'id': 'next'})['fixed_number'], 'INV-00032')

    def test_sent_duplicate_is_not_silently_renumbered(self):
        for i in range(2):
            self.put({'id': str(i), 'fixed_number': 'INV-00025', 'status': 'sent', 'notification_id': str(i)})
        with self.assertRaisesRegex(RuntimeError, 'delivery history'):
            numbering.migrate(self.c, 'sqlite')

    def test_paid_historical_batch_reserves_before_any_invoice_is_saved(self):
        numbering.migrate(self.c, 'sqlite')
        prepared = []
        for i in range(7):
            invoice = {'id': str(i), 'created_at': '2026-11-14', 'payment_status': 'received'}
            number_invoice(self.c, invoice)
            prepared.append(invoice)
        self.assertEqual(len({d['fixed_number'] for d in prepared}), 7)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM operations_records WHERE kind='invoice'").fetchone()[0], 0)
        for invoice in prepared:
            self.put(invoice)


if __name__ == '__main__':
    unittest.main()
