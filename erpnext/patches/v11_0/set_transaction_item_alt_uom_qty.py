# Copyright (c) 2017, Frappe and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt

from frappe.model.utils.rename_field import rename_field

def execute():
	doctypes = [
		'Sales Order', 'Delivery Note', 'Sales Invoice',
		'Purchase Order', 'Purchase Receipt', 'Purchase Invoice',
		'Quotation', 'Supplier Quotation'
	]
	item_doctypes = [d + " Item" for d in doctypes]
	all_dts = doctypes + item_doctypes + ['Item']
	quoted_dts = ["'" + dt + "'" for dt in all_dts]

	# Convert Data/Read Only fields to Float
	print("Converting Data/Read Only to Float Convertible for {0}: {1}".format("Item", 'purchase_pallets, sale_pallets, weight_of_pallet'))
	# ppk_calculation
	frappe.db.sql("update `tabItem` set purchase_pallets = 0 where ifnull(purchase_pallets, '') = '' or purchase_pallets = 'NaN'")
	frappe.db.sql("update `tabItem` set sale_pallets = 0 where ifnull(sale_pallets, '') = '' or sale_pallets = 'NaN'")
	frappe.db.sql("update `tabItem` set weight_of_pallet = 0 where ifnull(weight_of_pallet, '') = '' or weight_of_pallet = 'NaN'")

	for dt in doctypes:
		if frappe.get_meta(dt).has_field('total_boxes'):
			print("Converting Data/Read Only to Float Convertible for {0}: {1}".format(dt, 'total_boxes'))
			frappe.db.sql("update `tab{0}` set total_boxes = total_qty where ifnull(total_boxes, '') = '' or total_boxes = 'NaN'".format(dt))

		for f in ['total_pallet', 'total_pallets', 'total_gross_weight_lbs']:
			df = frappe.get_meta(dt).get_field(f)
			if df and df.fieldtype != 'Float':
				print("Converting Data/Read Only to Float Convertible for {0}: {1}".format(dt, f))
				frappe.db.sql("update `tab{0}` set {1} = 0 where ifnull({1}, '') = '' or {1} = 'NaN'".format(dt, f))

	for dt in item_doctypes:
		for f in ['sale_pallets', 'boxes_pallet_for_purchase']:
			df = frappe.get_meta(dt).get_field(f)
			if df and df.fieldtype != 'Float':
				print("Converting Data/Read Only to Float Convertible for {0}: {1}".format(dt, f))
				frappe.db.sql("update `tab{0}` set {1} = 0 where ifnull({1}, '') = '' or {1} = 'NaN'".format(dt, f))

	old_meta = {}
	for dt in all_dts:
		old_meta[dt] = frappe.get_meta(dt)

	# Load updated DocType
	print("Reloading DocTypes")
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

	# Rename fields
	for dt in doctypes:
		for old, new in [('total_net_weight', 'total_gross_weight'), ('total_pallet', 'total_pallets')]:
			if old_meta[dt].has_field(old) and not old_meta[dt].has_field(new):
				print("Rename Field in {0}: {1} -> {2}".format(dt, old, new))
				rename_field(dt, old, new)

	for dt in item_doctypes:
		for old, new in [('sale_pallets', 'qty_per_pallet'), ('boxes_pallet_for_purchase', 'qty_per_pallet'), ('boxes_ordered', 'ordered_qty'), ('is_authorize', 'requires_authorization')]:
			if old_meta[dt].has_field(old) and not old_meta[dt].has_field(new):
				print("Rename Field in {0}: {1} -> {2}".format(dt, old, new))
				rename_field(dt, old, new)

	# Item Master
	print("Item")
	for item in frappe.db.sql("select name, gross_weight from tabItem", as_dict=1):
		doc = frappe.get_doc('Item', item.name)
		doc.alt_uom = doc.weight_uom if doc.weight_uom != doc.stock_uom else "lbs"
		doc.alt_uom_size = flt(doc.weight_per_unit) or 1
		doc.weight_per_unit = item.gross_weight
		doc.save()

	# Transactions
	for dt in doctypes:
		print(dt)

		# Contents Qty from Old Net Weight
		if frappe.get_meta(dt + " Item").has_field('stock_alt_uom_size'):
			frappe.db.sql("""
				update `tab{dt} Item` set
					stock_alt_uom_size = weight_per_unit / conversion_factor,
					stock_alt_uom_size_std = weight_per_unit / conversion_factor,
					alt_uom_size_std = weight_per_unit
			""".format(dt=dt))
		else:
			print("DocType {dt} Item does not have field stock_alt_uom_size".format(dt=dt))

		frappe.db.sql("""
			update `tab{dt} Item` set
				alt_uom_size = weight_per_unit,
				alt_uom = weight_uom
		""".format(dt=dt))

		# Item Gross Weight Per Unit
		if old_meta[dt + " Item"].has_field('gross_weight_lbs'):
			frappe.db.sql("""update `tab{dt} Item` set weight_per_unit = gross_weight_lbs""".format(dt=dt))
		else:
			print("DocType {dt} Item does not have field gross_weight_lbs".format(dt=dt))

		# Item Packed In Qty
		if frappe.get_meta(dt + " Item").has_field('boxes'):
			frappe.db.sql("""update `tab{dt} Item` set boxes = qty""".format(dt=dt))
		else:
			print("DocType {dt} Item does not have field boxes".format(dt=dt))

		# Item # of pallets
		if frappe.get_meta(dt + " Item").has_field('pallets'):
			frappe.db.sql("""update `tab{dt} Item` set pallets = IF(qty_per_pallet=0, 0, qty/qty_per_pallet)""".format(dt=dt))
		else:
			print("DocType {dt} Item does not have field pallets".format(dt=dt))

		# Item Contents Qty and Gross Weight
		frappe.db.sql("""
			update `tab{dt} Item` set
				alt_uom_qty = alt_uom_size * qty,
				total_weight = weight_per_unit * stock_qty
		""".format(dt=dt))

		# Items without Contents UOM
		frappe.db.sql("""
			update `tab{dt} Item`
			set alt_uom_size = 1, alt_uom_qty = stock_qty
			where ifnull(alt_uom, '') = ''
		""".format(dt=dt))

		if frappe.get_meta(dt + " Item").has_field('stock_alt_uom_size'):
			frappe.db.sql("""
				update `tab{dt} Item`
				set
					stock_alt_uom_size = 1/conversion_factor,
					stock_alt_uom_size_std = 1/conversion_factor,
					alt_uom_size_std = 1
				where ifnull(alt_uom, '') = ''
			""".format(dt=dt))

		# Item Contents Rate
		if frappe.get_meta(dt + " Item").has_field('alt_uom_rate'):
			frappe.db.sql("""
				update `tab{dt} Item` i
				inner join `tab{dt}` m on m.name = i.parent
				set
					i.alt_uom_rate = if(i.alt_uom_qty = 0, 0, i.amount / i.alt_uom_qty),
					i.base_alt_uom_rate = if(i.alt_uom_qty = 0, 0, i.amount * m.conversion_rate / i.alt_uom_qty)
			""".format(dt=dt))
		else:
			print("DocType {dt} Item does not have field alt_uom_rate".format(dt=dt))

		# Parent Total Contents Qty
		frappe.db.sql("""
			update `tab{dt}` m
			set total_alt_uom_qty = (
				select ifnull(sum(d.alt_uom_qty), 0)
				from `tab{dt} Item` d where d.parent = m.name and d.parenttype = '{dt}'
			)
		""".format(dt=dt))

		# Parent Total Gross Weight
		if old_meta[dt].has_field('total_gross_weight_lbs'):
			frappe.db.sql("update `tab{dt}` m set total_gross_weight = total_gross_weight_lbs".format(dt=dt))
		else:
			print("DocType {dt} does not have field total_gross_weight_lbs".format(dt=dt))

		if frappe.get_meta(dt).has_field('total_gross_weight_kg'):
			frappe.db.sql("update `tab{dt}` set total_gross_weight_kg = total_gross_weight * 0.45359237")

		# Sales Order Title and Authorization
		if dt == "Sales Order":
			frappe.db.sql("update `tab{dt}` m set title = ifnull(customer_name, customer)".format(dt=dt))
			frappe.db.sql("update `tab{dt}` m set authorize = 'Not Required' where ifnull(authorize, '') = ''".format(dt=dt))

	# Stock Entry special case
	print("Stock Entry")
	frappe.db.sql("""
		update `tabStock Entry Detail`
		set alt_uom_size = 1, alt_uom_qty = transfer_qty
		where ifnull(alt_uom, '') = ''
	""")

	# Remove customizations
	print("Remove Custom Fields and Property Setters")
	custom_fields = frappe.db.sql_list("select name from `tabCustom Field` where dt in ({0})".format(", ".join(quoted_dts)))
	prop_setters = frappe.db.sql_list("select name from `tabProperty Setter` where doc_type in ({0})".format(", ".join(quoted_dts)))
	for name in custom_fields:
		frappe.delete_doc('Custom Field', name)
	for name in prop_setters:
		frappe.delete_doc('Property Setter', name)
	frappe.db.commit()
