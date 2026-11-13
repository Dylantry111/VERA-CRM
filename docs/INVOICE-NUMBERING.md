# Invoice numbering and payment references

New invoices receive a unique `DRAFT-xxxxx` label. Confirmation/issuance reserves
an `INV-xxxxx` number permanently. Sending also issues an unissued draft for API
clients that combine those actions. Recording a receipt likewise formalizes the
invoice. Retrying any of these actions keeps the existing reservation.

The independent `invoice_number_registry` survives invoice cancellation/deletion.
The allocator advances an internal counter under the existing database write
lock. Registry number, owner and numeric sequence have unique constraints; an
additional unique expression index protects public numbers in invoice JSON.

Unpaid, unissued drafts can be soft-deleted. Numbered invoices can only be voided
with a reason; paid invoices require a separate adjustment. Cancellation releases
rebate allocations and the balance-invoice association. Cancelled deposit drafts
return their order to review; replacement deposits use a new internal ID.

Payment reference is the immutable invoice number. Order IDs remain invoice
line-item associations. Draft previews have no payable reference. A lookup of a
historical number shared by multiple invoices returns a conflict for manual
customer/amount reconciliation rather than selecting one arbitrarily.

Before email delivery is queued, existing invoices use the currently saved
template and payment settings, including legacy imports with blank snapshots.
Queueing saves that presentation for the email and PDF. Pending, sent, and
uncertain deliveries retain their saved version when settings later change.

The versioned `invoice-numbering-v2` migration preserves unique existing numbers,
repairs unsent duplicate historical records, and records old/new mappings in
`invoice_number_audit` and invoice metadata. It refuses to silently renumber a
duplicate with delivery history. Amounts, payment facts, orders and allocations
are preserved. The admin **Number changes** button exposes the mapping.

Production disables full `VERA_AUTO_INIT`. A per-worker first-request guard runs
only this invoice migration under the PostgreSQL advisory lock; the persistent
version marker makes later starts a no-op. The allocator also adopts numbers
committed by a previous deployment during rollout.

Verification: SQLite reservation/lifecycle regressions, isolated API workflows,
and a separate disposable PostgreSQL schema for first-request migration and 12
concurrent issuances. Tests must not send real email or use production invoices.
