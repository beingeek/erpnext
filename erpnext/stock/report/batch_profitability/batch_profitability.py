# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt
from six import string_types, iteritems
import json


def execute(filters=None):
	columns = get_columns(filters)

	if not filters.get('batch_no'):
		return columns, []

	data = get_data([filters.get('batch_no')])

	out = []

	out.append(get_total(data.source_sinv, "Direct Sales"))
	out += data.source_sinv
	out.append({})

	out.append(get_total(data.target_sinv, "Repacked Sales"))
	out += data.target_sinv
	out.append({})

	out.append(get_total(data.source_lcv, "Landed Costs"))
	out += data.source_lcv
	out.append({})

	out.append(get_total(data.target_repack, "Repack Costs"))
	out += data.target_repack

	return columns, out


def get_total(data, label):
	total_row = frappe._dict({
		"doctype": _(label), "indent": 0, "_bold": 1, "revenue": 0, "cost": 0, "qty": 0
	})
	for d in data:
		total_row.revenue += flt(d.revenue)
		total_row.cost += flt(d.cost)
		total_row.qty += flt(d.qty)
		d.indent = 1

	return total_row


def get_data(batch_nos):
	source_sinv_data = frappe.db.sql("""
		select 'Sales Invoice' as doctype, inv.name, item.item_code, item.batch_no, item.stock_qty as qty,
		item.base_net_amount as revenue, inv.update_stock
		from `tabSales Invoice Item` item, `tabSales Invoice` inv
		where inv.name = item.parent and inv.docstatus = 1 and item.batch_no in ({0})
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	target_repack_data = []
	repacked_batch_map = {}
	repacked_batch_nos = []
	for source_batch_no in batch_nos:
		repack_entry_data = frappe.db.sql("""
			select 'Stock Entry' as doctype, p.name, tar.item_code, tar.batch_no, tar.transfer_qty as qty,
				tar.additional_cost as cost
			from `tabStock Entry` p
			inner join `tabStock Entry Detail` tar on tar.parent = p.name
			where p.docstatus = 1 and p.purpose = 'Repack' and ifnull(tar.t_warehouse, '') != '' and exists(
				select src.name from `tabStock Entry Detail` src where src.parent = p.name and src.batch_no = %s
					and ifnull(src.t_warehouse, '') = '')
		""", source_batch_no, as_dict=1)
		target_repack_data += repack_entry_data

		for d in repack_entry_data:
			repacked_batch_dict = repacked_batch_map.setdefault(d.target_batch, frappe._dict({
				"source_batch_nos": set(), "cost": 0
			}))
			repacked_batch_dict.source_batch_nos.add(source_batch_no)
			repacked_batch_dict.cost += d.cost
			repacked_batch_nos.append(d.target_batch)

	repacked_batch_nos = list(set(repacked_batch_nos))

	target_sinv_data = []
	if repacked_batch_nos:
		target_sinv_data = frappe.db.sql("""
			select 'Sales Invoice' as doctype, inv.name, item.item_code, item.batch_no, item.stock_qty as qty,
				item.base_net_amount as revenue, inv.update_stock
			from `tabSales Invoice Item` item, `tabSales Invoice` inv
			where inv.name = item.parent and inv.docstatus = 1 and item.batch_no in ({0})
		""".format(", ".join(['%s'] * len(repacked_batch_nos))), repacked_batch_nos, as_dict=1)

	source_lcv_data = frappe.db.sql("""
		select 'Landed Cost Voucher' as doctype, lci.parent as name, lci.item_code, pri.batch_no, lci.applicable_charges as cost
		from `tabLanded Cost Item` lci, `tabPurchase Receipt Item` pri
		where pri.name = lci.purchase_receipt_item and lci.docstatus = 1 and pri.batch_no in ({0})
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	source_actual_qty = frappe.db.sql("""
		select batch_no, sum(actual_qty) as qty
		from `tabStock Ledger Entry`
		where batch_no in ({0}) and is_cancelled = 'No'
		group by batch_no
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	return frappe._dict({
		"source_sinv": source_sinv_data,
		"target_sinv": target_sinv_data,
		"source_lcv": source_lcv_data,
		"target_repack": target_repack_data,
		"source_actual_qty": source_actual_qty,
		"repacked_batch_map": repacked_batch_map
	})


@frappe.whitelist()
def get_batch_cost_and_revenue(batch_nos):
	if isinstance(batch_nos, string_types):
		batch_nos = json.loads(batch_nos)
	batch_nos = list(set(batch_nos))

	if not batch_nos:
		return {}

	# Prepare output
	out = {}
	for batch_no in batch_nos:
		out[batch_no] = frappe._dict({
			"direct_revenue": 0, "direct_qty_sold": 0,
			"repacked_revenue": 0, "repacked_qty_sold": 0,
			"lcv_cost": 0, "repack_cost": 0, "actual_batch_qty": 0,
			"batch_revenue": 0, "repacked_batches": []
		})

	data = get_data(batch_nos)

	for d in data.source_actual_qty:
		out[d.batch_no].actual_batch_qty = d.qty

	for d in data.source_sinv:
		out[d.batch_no].direct_revenue += d.revenue
		if d.update_stock:
			out[d.batch_no].direct_qty_sold += d.qty

	for d in data.source_lcv:
		out[d.batch_no].lcv_cost += d.cost

	for d in data.target_sinv:
		repacked_batch_dict = data.repacked_batch_map[d.batch_no]
		source_batch_nos = list(repacked_batch_dict.get('source_batch_nos', set()))
		for source_batch in source_batch_nos:
			out[source_batch].repacked_revenue += d.revenue / len(source_batch_nos)
			if d.update_stock:
				out[source_batch].repacked_qty_sold += d.qty / len(source_batch_nos)

	for target_batch, repacked_batch_dict in iteritems(data.repacked_batch_map):
		source_batch_nos = list(repacked_batch_dict.get('source_batch_nos', set()))
		if len(source_batch_nos) > 1:
			frappe.msgprint(_("Multiple Source Batches found for Repacked Batch {0}. This may result in inaccurate values. Source Batches: {1}")
				.format(target_batch, ", ".join(source_batch_nos)))

		for source_batch in source_batch_nos:
			out[source_batch].repack_cost += repacked_batch_dict.cost / len(source_batch_nos)
			out[source_batch].repacked_batches += source_batch

	for d in out.values():
		d.batch_revenue = flt(d.direct_revenue) + flt(d.repacked_revenue)
		d.repacked_batches = json.dumps(list(set(d.repacked_batches)))

	return out


def get_columns(filters):
	return [
		{
			"label": _("Document Type"),
			"fieldname": "doctype",
			"fieldtype": "Data",
			"width": 160
		},
		{
			"label": _("Document No"),
			"fieldname": "name",
			"fieldtype": "Dynamic Link",
			"options": "doctype",
			"width": 120
		},
		{
			"label": _("Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 80
		},
		{
			"label": _("Batch"),
			"fieldname": "batch_no",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 150
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 80
		},
		{
			"label": _("Revenue"),
			"fieldname": "revenue",
			"fieldtype": "Currency",
			"width": 100
		},
		{
			"label": _("Cost"),
			"fieldname": "cost",
			"fieldtype": "Currency",
			"width": 100
		}
	]
