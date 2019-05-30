# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, add_days
from erpnext.stock.report.stock_ledger.stock_ledger import get_item_group_condition
from six import iteritems


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.date = getdate(filters.date or nowdate())
	filters.from_date = filters.date
	filters.to_date = frappe.utils.add_days(filters.from_date, 4)

	columns = get_columns(filters)
	data = get_data(filters)

	return columns, data


def get_data(filters):
	conditions = get_item_conditions(filters)

	po_data = frappe.db.sql("""
		select
			item.item_code, item.item_name, po.schedule_date as date,
			sum(if(item.qty - item.received_qty < 0, 0, item.qty - item.received_qty)) as qty
		from `tabPurchase Order Item` item
		inner join `tabPurchase Order` po on po.name = item.parent
		where po.docstatus < 2 and po.schedule_date between %(from_date)s and %(to_date)s {0}
		group by item.item_code, po.schedule_date
	""".format(conditions), filters, as_dict=1)

	so_data = frappe.db.sql("""
		select
			item.item_code, item.item_name, so.delivery_date as date,
			sum(item.qty) as qty
		from `tabSales Order Item` item
		inner join `tabSales Order` so on so.name = item.parent
		where so.docstatus = 0 and so.delivery_date between %(from_date)s and %(to_date)s {0}
		group by item.item_code, so.delivery_date
	""".format(conditions), filters, as_dict=1)

	item_codes = list(set([d.item_code for d in po_data] + [d.item_code for d in so_data]))

	bin_data = frappe.db.sql("""
		select item_code, sum(actual_qty) as actual_qty
		from tabBin
		where item_code in ({0})
		group by item_code
	""".format(", ".join(['%s']*len(item_codes))), item_codes, as_dict=1) if item_codes else []

	item_map = {}
	template = frappe._dict({"actual_qty": 0, "total_so_qty": 0, "total_po_qty": 0})

	for d in so_data:
		item_map.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, filters.from_date)
		item_map[d.item_code]['item_code'] = d.item_code
		item_map[d.item_code]['item_name'] = d.item_name
		item_map[d.item_code]['so_day_' + str(i+1)] = d.qty
		item_map[d.item_code]['total_so_qty'] += d.qty

	for d in po_data:
		item_map.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, filters.from_date)
		item_map[d.item_code]['item_code'] = d.item_code
		item_map[d.item_code]['item_name'] = d.item_name
		item_map[d.item_code]['po_day_' + str(i+1)] = d.qty
		item_map[d.item_code]['total_po_qty'] += d.qty

	for d in bin_data:
		item_map[d.item_code]['actual_qty'] = d.actual_qty

	data = sorted(item_map.values(), key=lambda d: d.total_so_qty, reverse=True)
	return data


def get_item_conditions(filters):
	conditions = []

	if filters.get("item_code"):
		conditions.append("item.item_code = %(item_code)s")
	else:
		if filters.get("brand"):
			conditions.append("item.brand=%(brand)s")
		if filters.get("item_group"):
			conditions.append(get_item_group_condition(filters.get("item_group")))

	conditions = " and ".join(conditions)
	return "and {0}".format(conditions) if conditions else ""


def get_columns(filters):
	columns = [
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 80},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "actual_qty", "label": _("In Stock"), "fieldtype": "Float", "width": 70},
		{"fieldname": "total_so_qty", "label": _("Total SO"), "fieldtype": "Float", "width": 70,
			"is_so_qty": 1, "from_date": filters.date, "to_date": add_days(filters.date, 4)}
	]
	for i in range(5):
		date = add_days(filters.date, i)
		columns.append({
			"fieldname": "so_day_{0}".format(i+1),
			"label": _("SO {0}").format(frappe.utils.formatdate(date, "EEE")),
			"fieldtype": "Float",
			"is_so_qty": 1,
			"from_date": date,
			"to_date": date,
			"width": 65
		})

	columns.append({"fieldname": "total_po_qty", "label": _("Total PO"), "fieldtype": "Float", "width": 70})
	for i in range(5):
		columns.append({
			"fieldname": "po_day_{0}".format(i+1),
			"label": _("PO {0}").format(frappe.utils.formatdate(add_days(filters.date, i), "EEE")),
			"fieldtype": "Float",
			"width": 65
		})

	return columns
