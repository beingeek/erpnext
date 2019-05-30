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
		# Validate
		for d in self.sales_orders:
			if flt(d.back_order_qty) and not d.back_order_date:
				frappe.throw(_("Row #{0}: Please select Back Order Date for SO {1}").format(d.idx, d.sales_order))

		# Change Item Code
		for d in self.sales_orders:
			if d.new_item_code and d.new_item_code != self.item_code:
				change_item_code(d.sales_order, d.so_detail, d.new_item_code, self.item_code)

		# Adjust
		for d in self.sales_orders:
			qtyAdjust(d.customer, d.sales_order, d.new_item_code or self.item_code, d.ordered_qty, d.allocated_qty,
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
		doc.total_pallets += flt(d.qty)/flt(d.sale_pallets)
		doc.total_gross_weight_lbs += flt(d.qty) * flt(d.gross_weight_lbs)

	doc.total_weight_kg = flt(doc.total_gross_weight_lbs * 0.45359237, 2)
	doc.save()
