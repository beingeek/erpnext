# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_data(filters):
	conditions = []
	if filters.get('item_code'):
		conditions.append("item_code = %(item_code)s")
	if filters.get('from_date'):
		conditions.append("po.`schedule_date` >= %(from_date)s")
	if filters.get('to_date'):
		conditions.append("po.`schedule_date` <= %(to_date)s")
	conditions_sql = "and {0}".format(" and ".join(conditions)) if conditions else ""

	data = frappe.db.sql("""
		select
			po.`name` as "Purchase Order",
			i.`schedule_date` as "Arrival Date",
			po.`supplier` as "Supplier",
			i.item_code as "Item Code",
			i.qty as "Ordered Qty",
			(i.qty - ifnull(i.received_qty, 0)) as "Balance Qty",
			i.landed_rate as "LC/Unit",
			i.landed_cost_voucher_amount / i.qty as "Expenses/Unit",
			po.order_type as "Shipping Mode",
			po.status as "Status"
		from
			`tabPurchase Order` po, `tabPurchase Order Item` i
		where
			i.`parent` = po.`name`
			and po.docstatus < 2
			and po.status not in ('Stopped', 'Closed')
			and ifnull(i.received_qty, 0) < ifnull(i.qty, 0) {0}
		order by po.schedule_date asc
	""".format(conditions_sql), filters, as_dict=1)

	for d in data:
		d["LC/Unit"] = flt(d.get("LC/Unit"), 2)
		d["Expenses/Unit"] = flt(d.get("Expenses/Unit"), 2)

	return data


def get_columns():
	columns = [
		"Purchase Order:Link/Purchase Order:100",
		"Arrival Date:Date:80",
		"Supplier:Link/Supplier:120",
		"Item Code:Link/Item:80",
		"Ordered Qty:Float:70",
		"Balance Qty:Float:90",
	]

	show_amounts_role = frappe.db.get_single_value("Stock Settings", "restrict_amounts_in_report_to_role")
	show_amounts = show_amounts_role and show_amounts_role in frappe.get_roles()
	if show_amounts:
		columns += [
			"LC/Unit:Currency:70",
			"Expenses/Unit:Currency:70",
		]

	columns += [
		"Shipping Mode:Link/Master Purchase Order Type:110",
		"Status::120",
	]

	return columns
