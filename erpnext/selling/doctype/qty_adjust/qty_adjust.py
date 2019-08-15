# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import cint
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.api5 import qtyAdjust
from six import string_types
import json


class QtyAdjust(Document):
	def qty_adjust_sales_orders(self):
		sales_orders = filter(lambda d: d.docstatus == 0 and d.dt == "Sales Order", self.sales_orders)

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
			qtyAdjust(d.customer, d.dn, d.new_item_code or self.item_code, d.qty / d.conversion_factor, d.allocated_qty / d.conversion_factor,
				d.back_order_qty / d.conversion_factor, d.back_order_date or d.date)

		frappe.msgprint("Sales Orders Adjusted")


def change_item_code(sales_order, so_detail, new_item_code, old_item_code):
	from erpnext.stock.get_item_details import get_item_details

	doc = frappe.get_doc("Sales Order", sales_order)
	row = filter(lambda d: d.name == so_detail, doc.items)
	if not row:
		frappe.throw(_("Could not find Item {0} in {1}").format(old_item_code, sales_order))
	else:
		row = row[0]

	item_details = get_item_details({
		'item_code': new_item_code,
		'set_warehouse': doc.set_warehouse,
		'warehouse': row.warehouse,
		'customer': doc.customer,
		'currency': doc.currency,
		'conversion_rate': doc.conversion_rate,
		'price_list': doc.selling_price_list,
		'price_list_currency': doc.price_list_currency,
		'plc_conversion_rate': doc.plc_conversion_rate,
		'company': doc.company,
		'order_type': doc.order_type,
		'transaction_date': doc.transaction_date or doc.get('posting_date'),
		'delivery_date': doc.delivery_date or doc.transaction_date or doc.get('posting_date'),
		'ignore_pricing_rule': cint(row.override_price_list_rate or doc.ignore_pricing_rule),
		'doctype': doc.doctype,
		'name': doc.name,
		'project': row.get('project') or doc.project,
		'qty': row.qty or 0,
		'stock_qty': row.stock_qty,
		'uom': row.uom,
		'tax_category': doc.tax_category
	})

	for f in ['meta', 'name', 'doctype']:
		if f in item_details:
			del item_details[f]

	row.update(item_details)
	doc.save()


@frappe.whitelist()
def get_sales_orders_for_qty_adjust(item_code, from_date, to_date=None):
	date_condition = "and so.delivery_date >= %(from_date)s"
	if to_date:
		date_condition += "and so.delivery_date <= %(to_date)s"
	date_condition_si = date_condition.replace("so.", "sinv.")

	so_data = frappe.db.sql("""
		select 'Sales Order' as dt, so.name as dn, so.docstatus, so.customer, so.delivery_date as date, i.name as so_detail,
			(i.qty - ifnull(i.delivered_qty, 0)) * i.conversion_factor as qty, i.conversion_factor
		from `tabSales Order Item` i
		inner join `tabSales Order` so on so.name = i.parent
		where so.docstatus < 2 and ifnull(i.delivered_qty, 0) < ifnull(i.qty, 0) and so.status != 'Closed'
			and i.item_code = %(item_code)s {0}
		
		union all
		
		select 'Sales Invoice' as dt, sinv.name as dn, sinv.docstatus, sinv.customer, sinv.delivery_date as date, i.name as so_detail,
			i.stock_qty as qty, i.conversion_factor
		from `tabSales Invoice Item` i
		inner join `tabSales Invoice` sinv on sinv.name = i.parent
		where sinv.docstatus = 0 and ifnull(i.sales_order, '') = ''
			and i.item_code = %(item_code)s {1}

		order by date, dt, dn
	""".format(date_condition, date_condition_si), {"from_date": from_date, "to_date": to_date, "item_code": item_code}, as_dict=1)

	return so_data