# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.api5 import qtyAdjust
from six import string_types
import json


class QtyAdjust(Document):
	def qty_adjust_sales_orders(self):
		sales_orders = filter(lambda d: not d.docstatus and d.dt == "Sales Order", self.sales_orders)

		# Validate
		for d in sales_orders:
			if flt(d.back_order_qty) and not d.back_order_date:
				frappe.throw(_("Row #{0}: Please select Back Order Date for {1}").format(d.idx, d.dn))

		# Change Item Code
		for d in sales_orders:
			if d.new_item_code and d.new_item_code != self.item_code:
				change_item_code(d.dn, d.so_detail, d.new_item_code, self.item_code)

		# Adjust
		for d in sales_orders:
			qtyAdjust(d.customer, d.dn, d.new_item_code or self.item_code, d.qty, d.allocated_qty,
				d.back_order_qty, d.back_order_date or d.date)

		frappe.msgprint("Sales Orders Adjusted")


def change_item_code(sales_order, so_detail, new_item_code, old_item_code):
	from erpnext.api2 import customerPriceList
	from erpnext.stock.get_item_details import get_conversion_factor

	doc = frappe.get_doc("Sales Order", sales_order)
	row = filter(lambda d: d.name == so_detail, doc.items)
	if not row:
		frappe.throw(_("Could not find Item {0} in {1}").format(old_item_code, sales_order))
	else:
		row = row[0]

	rate = flt(customerPriceList(row.idx, row.idx, doc.customer, new_item_code, doc.selling_price_list)[0].get('price'))
	item_details = frappe.db.get_value("Item", new_item_code, ["item_name", "description",
		"sale_pallets", "gross_weight", "sales_uom", "stock_uom", "hst", "weight_per_unit", "weight_uom", "cost_center"], as_dict=1)

	row.update(item_details)
	row.item_code = new_item_code
	row.rate = rate
	row.uom = item_details.sales_uom or item_details.stock_uom
	row.conversion_factor = get_conversion_factor(new_item_code, row.uom)['conversion_factor']
	row.weight_lbs = item_details.weight_per_unit
	row.gross_weight_lbs = item_details.gross_weight
	row.weight_kgs = flt(item_details.weight_per_unit * 0.45359237, 2)
	row.hst = 1 if item_details.hst == "Yes" else 0

	doc.total_boxes = 0
	doc.total_pallets = 0
	doc.total_gross_weight_lbs = 0
	for d in doc.items:
		doc.total_boxes += flt(d.qty)
		doc.total_gross_weight_lbs += flt(d.qty) * flt(d.gross_weight_lbs)
		if flt(d.sale_pallets) > 0:
			doc.total_pallets += flt(d.qty)/flt(d.sale_pallets)

	doc.total_weight_kg = flt(doc.total_gross_weight_lbs * 0.45359237, 2)
	doc.save()


@frappe.whitelist()
def get_sales_orders_for_qty_adjust(item_code, from_date, to_date=None):
	date_condition = "and so.delivery_date >= %(from_date)s"
	if to_date:
		date_condition += "and so.delivery_date <= %(to_date)s"
	date_condition_si = date_condition.replace("so.", "sinv.")

	so_data = frappe.db.sql("""
		select 'Sales Order' as dt, so.name as dn, so.docstatus, so.customer, so.delivery_date as date, i.name as so_detail,
			i.qty - ifnull(i.delivered_qty, 0) as qty
		from `tabSales Order Item` i
		inner join `tabSales Order` so on so.name = i.parent
		where so.docstatus < 2 and ifnull(i.delivered_qty, 0) < ifnull(i.qty, 0) and so.status != 'Closed'
			and i.item_code = %(item_code)s {0}
		
		union all
		
		select 'Sales Invoice' as dt, sinv.name as dn, sinv.docstatus, sinv.customer, sinv.delivery_date as date, i.name as so_detail,
			i.qty as qty
		from `tabSales Invoice Item` i
		inner join `tabSales Invoice` sinv on sinv.name = i.parent
		where sinv.docstatus = 0 and ifnull(i.sales_order, '') = ''
			and i.item_code = %(item_code)s {1}

		order by date, dt, dn
	""".format(date_condition, date_condition_si), {"from_date": from_date, "to_date": to_date, "item_code": item_code}, as_dict=1)

	return so_data