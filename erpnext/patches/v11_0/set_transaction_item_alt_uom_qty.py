# Copyright (c) 2017, Frappe and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe

def execute():
	frappe.reload_doc('selling', 'doctype', 'quotation', force=1)
	frappe.reload_doc('selling', 'doctype', 'quotation_item', force=1)
	frappe.reload_doc('selling', 'doctype', 'sales_order', force=1)
	frappe.reload_doc('selling', 'doctype', 'sales_order_item', force=1)
	frappe.reload_doc('stock', 'doctype', 'delivery_note', force=1)
	frappe.reload_doc('stock', 'doctype', 'delivery_note_item', force=1)
	frappe.reload_doc('accounts', 'doctype', 'sales_invoice', force=1)
	frappe.reload_doc('accounts', 'doctype', 'sales_invoice_item', force=1)
	frappe.reload_doc('buying', 'doctype', 'supplier_quotation', force=1)
	frappe.reload_doc('buying', 'doctype', 'supplier_quotation_item', force=1)
	frappe.reload_doc('buying', 'doctype', 'purchase_order', force=1)
	frappe.reload_doc('buying', 'doctype', 'purchase_order_item', force=1)
	frappe.reload_doc('stock', 'doctype', 'purchase_receipt', force=1)
	frappe.reload_doc('stock', 'doctype', 'purchase_receipt_item', force=1)
	frappe.reload_doc('accounts', 'doctype', 'purchase_invoice', force=1)
	frappe.reload_doc('accounts', 'doctype', 'purchase_invoice_item', force=1)
	frappe.reload_doc('stock', 'doctype', 'stock_entry_detail', force=1)

	doctypes = [
		'Sales Order', 'Delivery Note', 'Sales Invoice',
		'Purchase Order', 'Purchase Receipt', 'Purchase Invoice',
		'Quotation', 'Supplier Quotation'
	]

	# Calculate and update database
	for dt in doctypes:
		print(dt)
		frappe.db.sql("""
			update `tab{dt} Item`
			set alt_uom_size = 1, alt_uom_qty = stock_qty
			where ifnull(alt_uom, '') = ''
		""".format(dt=dt))

		frappe.db.sql("""
			update `tab{dt}` m
			set total_alt_uom_qty = (
				select ifnull(sum(d.alt_uom_qty), 0)
				from `tab{dt} Item` d where d.parent = m.name and d.parenttype = '{dt}'
			)
		""".format(dt=dt))

	frappe.db.sql("""
		update `tabStock Entry Detail`
		set alt_uom_size = 1, alt_uom_qty = transfer_qty
		where ifnull(alt_uom, '') = ''
	""")
