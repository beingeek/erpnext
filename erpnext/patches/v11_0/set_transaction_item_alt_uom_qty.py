# Copyright (c) 2017, Frappe and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe

from frappe.model.utils.rename_field import rename_field

def execute():
	doctypes = [
		'Sales Order', 'Delivery Note', 'Sales Invoice',
		'Purchase Order', 'Purchase Receipt', 'Purchase Invoice',
		'Quotation', 'Supplier Quotation'
	]

	# Convert Data/Read Only fields to Float
	frappe.db.sql("update `tabItem` set purchase_pallets = 0 where ifnull(purchase_pallets, '') = '' or purchase_pallets = 'NaN'")
	frappe.db.sql("update `tabItem` set sale_pallets = 0 where ifnull(sale_pallets, '') = '' or sale_pallets = 'NaN'")
	frappe.db.sql("update `tabItem` set weight_of_pallet = 0 where ifnull(weight_of_pallet, '') = '' or weight_of_pallet = 'NaN'")

	for dt in doctypes:
		if frappe.get_meta(dt).has_field('total_boxes'):
			frappe.db.sql("update `tab{0}` set total_boxes = total_qty where ifnull(total_boxes, '') = '' or total_boxes = 'NaN'".format(dt))
		if frappe.get_meta(dt).has_field('qty_per_pallet'):
			frappe.db.sql("update `tab{0}` set qty_per_pallet = 0 where ifnull(qty_per_pallet, '') = '' or qty_per_pallet = 'NaN'".format(dt))

	# Rename total_net_weight to total_gross_weight
	for dt in doctypes:
		if frappe.get_meta(dt).has_field('total_net_weight'):
			rename_field(dt, 'total_net_weight', 'total_gross_weight')

	# Load updated DocType
	frappe.reload_doc('stock', 'doctype', 'item', force=1)
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

	# Item Master
	for item in frappe.db.sql("select name, gross_weight from tabItem", as_dict=1):
		doc = frappe.get_doc('Item', item.name)
		doc.alt_uom = doc.weight_uom
		doc.alt_uom_size = doc.weight_per_unit
		doc.weight_per_unit = item.gross_weight
		doc.save()

	# Transactions
	for dt in doctypes:
		print(dt)

		# Transaction Item fields
		frappe.db.sql("""
			update `tab{dt} Item` set
				alt_uom_size = weight_per_unit,
				alt_uom = weight_uom
		""".format(dt=dt))

		frappe.db.sql("""update `tab{dt} Item` set weight_per_unit = weight_lbs""".format(dt=dt))

		frappe.db.sql("""
			update `tab{dt} Item` set
				alt_uom_qty = alt_uom_size * stock_qty,
				total_weight = weight_per_unit * stock_qty
		""".format(dt=dt))

		# Items without Contents UOM
		frappe.db.sql("""
			update `tab{dt} Item`
			set alt_uom_size = 1, alt_uom_qty = stock_qty
			where ifnull(alt_uom, '') = ''
		""".format(dt=dt))

		# Total Contents Qty and Gross Weight
		frappe.db.sql("""
			update `tab{dt}` m
			set total_alt_uom_qty = (
				select ifnull(sum(d.alt_uom_qty), 0)
				from `tab{dt} Item` d where d.parent = m.name and d.parenttype = '{dt}'
			), total_gross_weight = total_gross_weight_lbs
		""".format(dt=dt))

	# Stock Entry special case
	print("Stock Entry")
	frappe.db.sql("""
		update `tabStock Entry Detail`
		set alt_uom_size = 1, alt_uom_qty = transfer_qty
		where ifnull(alt_uom, '') = ''
	""")
