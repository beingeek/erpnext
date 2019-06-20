# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_data(filters):
	conditions = []
	if filters.get('item_code'):
		conditions.append("item_code = %(item_code)s")
	if filters.get('from_date'):
		conditions.append("`tabPurchase Order`.`schedule_date` >= %(from_date)s")
	if filters.get('to_date'):
		conditions.append("`tabPurchase Order`.`schedule_date` <= %(to_date)s")
	conditions_sql = "and {0}".format(" and ".join(conditions)) if conditions else ""

	data = frappe.db.sql("""
		select
			`tabPurchase Order`.`name` as "Purchase Order:Link/Purchase Order:120",
			`tabPurchase Order`.`transaction_date` as "Order Date:Date:100",
			`tabPurchase Order Item`.`schedule_date` as "Arrival Date:Date:110",
			`tabPurchase Order`.`supplier` as "Supplier:Link/Supplier:120",
			`tabPurchase Order Item`.item_code as "Item Code:Link/Item:80",
			`tabPurchase Order Item`.item_name as "Item Name::150",
			`tabPurchase Order Item`.qty as "Ordered Qty:Float:70",
			`tabPurchase Order Item`.received_qty as "Received Qty:Float:70",
			(`tabPurchase Order Item`.qty - ifnull(`tabPurchase Order Item`.received_qty, 0)) as "Qty to Receive:Float:70"
		from
			`tabPurchase Order`, `tabPurchase Order Item`
		where
			`tabPurchase Order Item`.`parent` = `tabPurchase Order`.`name`
			and `tabPurchase Order`.docstatus < 2
			and `tabPurchase Order`.status not in ('Stopped', 'Closed')
			and ifnull(`tabPurchase Order Item`.received_qty, 0) < ifnull(`tabPurchase Order Item`.qty, 0) {0}
		order by `tabPurchase Order`.schedule_date asc
	""".format(conditions_sql), filters)

	return data


def get_columns():
	columns = [
		"Purchase Order:Link/Purchase Order:120",
		"Order Date:Date:100",
		"Arrival Date:Date:110",
		"Supplier:Link/Supplier:120",
		"Item Code:Link/Item:80",
		"Item Name::150",
		"Ordered Qty:Float:70",
		"Received Qty:Float:70",
		"Qty to Receive:Float:70"
	]

	return columns
