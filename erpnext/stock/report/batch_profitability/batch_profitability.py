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

	batch_nos = [filters.get('batch_no')]

	source_sinv_data = get_sinv_data(batch_nos)
	source_lcv_data = get_lcv_data(batch_nos)
	source_prec_data = get_prec_data(batch_nos)
	source_reco_data = get_reco_data(batch_nos)

	target_repack_data, repacked_batch_nos, target_batch_source_contribution = get_repack_entry_data(batch_nos)
	apply_source_repack_contribution(target_repack_data, filters.get('batch_no'), target_batch_source_contribution)

	target_sinv_data = get_sinv_data(repacked_batch_nos)
	apply_source_repack_contribution(target_sinv_data, filters.get('batch_no'), target_batch_source_contribution)

	target_reco_data = get_reco_data(repacked_batch_nos)
	apply_source_repack_contribution(target_reco_data, filters.get('batch_no'), target_batch_source_contribution)

	# source_actual_qty = get_batch_actual_qty(batch_nos)

	out = []

	out.append(get_total(source_sinv_data, "Direct Sales"))
	out += source_sinv_data
	out.append({})

	out.append(get_total(target_sinv_data, "Repacked Sales"))
	out += target_sinv_data
	out.append({})

	out.append(get_total(source_prec_data, "Purchase Receipts"))
	out += source_prec_data
	out.append({})

	out.append(get_total(source_lcv_data, "Landed Costs"))
	out += source_lcv_data
	out.append({})

	out.append(get_total(target_repack_data, "Repack Costs"))
	out += target_repack_data
	out.append({})

	out.append(get_total(source_reco_data, "Direct Reconciliation"))
	out += source_reco_data
	out.append({})

	out.append(get_total(target_reco_data, "Repacked Reconciliation"))
	out += target_reco_data

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


def apply_source_repack_contribution(data, source_batch, target_batch_source_contribution):
	for d in data:
		d.repack_contribution = target_batch_source_contribution[d.batch_no][source_batch]

		if d.revenue is not None:
			d.revenue = d.revenue * d.repack_contribution / 100
		if d.cost is not None:
			d.cost = d.cost * d.repack_contribution / 100

def get_sinv_data(batch_nos):
	if batch_nos:
		return frappe.db.sql("""
			select 'Sales Invoice' as doctype, 'Customer' as party_type, inv.customer as party,
				inv.name, item.item_code, item.batch_no, item.stock_qty as qty, item.stock_uom as uom,
				item.base_net_amount as revenue, item.base_net_rate * item.conversion_factor as rate, inv.update_stock
			from `tabSales Invoice Item` item, `tabSales Invoice` inv
			where inv.name = item.parent and inv.docstatus = 1 and item.batch_no in ({0})
		""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)
	else:
		return []


def get_lcv_data(batch_nos):
	if batch_nos:
		return frappe.db.sql("""
			select 'Landed Cost Voucher' as doctype, lcv.party_type, lcv.party, pri.stock_uom as uom,
				lci.parent as name, lci.item_code, pri.batch_no, lci.applicable_charges as cost
			from `tabLanded Cost Item` lci, `tabPurchase Receipt Item` pri, `tabLanded Cost Voucher` lcv
			where pri.name = lci.purchase_receipt_item and lcv.name = lci.parent and lci.docstatus = 1 and pri.batch_no in ({0})
		""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)
	else:
		return []


def get_prec_data(batch_nos):
	if batch_nos:
		return frappe.db.sql("""
			select 'Purchase Receipt' as doctype, 'Supplier' as party_type, prec.supplier as party, 1 as update_stock,
				prec.name, item.item_code, item.batch_no, item.stock_qty as qty, item.stock_uom as uom,
				item.base_net_amount as cost, item.base_net_rate * item.conversion_factor as rate
			from `tabPurchase Receipt Item` item, `tabPurchase Receipt` prec
			where prec.name = item.parent and prec.docstatus = 1 and item.batch_no in ({0})
		""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)
	else:
		return []


def get_reco_data(batch_nos):
	if batch_nos:
		return frappe.db.sql("""
			select sle.voucher_type as doctype, 1 as update_stock,
				sle.voucher_no as name, sle.item_code, sle.batch_no, sle.actual_qty as qty, sle.stock_uom as uom,
				if(sle.stock_value_difference > 0, sle.stock_value_difference, 0) as revenue,
				if(sle.stock_value_difference < 0, -sle.stock_value_difference, 0) as cost,
				sle.stock_value_difference / sle.actual_qty as rate
			from `tabStock Ledger Entry` sle
			where sle.batch_no in ({0}) and sle.voucher_type = 'Stock Reconciliation'
		""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)
	else:
		return []


def get_batch_actual_qty(batch_nos):
	if batch_nos:
		return frappe.db.sql("""
			select batch_no, sum(actual_qty) as qty
			from `tabStock Ledger Entry`
			where batch_no in ({0}) and is_cancelled = 'No'
			group by batch_no
		""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)
	else:
		return []


def get_repack_entry_data(batch_nos):
	repack_entry_data = frappe.db.sql("""
		select 'Stock Entry' as doctype, 1 as update_stock,
			ste.name, item.item_code, item.batch_no, item.transfer_qty as qty, item.additional_cost as cost,
			item.stock_uom as uom, item.t_warehouse, item.s_warehouse, item.amount
		from `tabStock Entry` ste, `tabStock Entry Detail` item
		where ste.name = item.parent and ste.docstatus = 1 and ste.purpose = 'Repack' and exists(
			select src_item.name from `tabStock Entry Detail` src_item where src_item.parent = ste.name
				and src_item.batch_no in ({0}) and ifnull(src_item.t_warehouse, '') = '')
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	# Target Rows
	target_repack_data = []
	repacked_batch_nos = []
	stock_entry_to_target_batch = {}
	for d in repack_entry_data:
		if d.t_warehouse:
			target_repack_data.append(d)
			repacked_batch_nos.append(d.batch_no)

			if d.batch_no in stock_entry_to_target_batch:
				frappe.msgprint(_(
					"Warning: Repack Entry {0} has multiple target batches. Gross Profit calculation may be inaccurate")
					.format(frappe.get_desk_link("Stock Entry", d.name)))
			else:
				stock_entry_to_target_batch[d.name] = d.batch_no

	# Source Rows
	target_batch_source_values = {}
	for d in repack_entry_data:
		if not d.t_warehouse:
			target_batch = stock_entry_to_target_batch[d.name]
			source_batch_values = target_batch_source_values.setdefault(target_batch, {})
			source_batch_values.setdefault(d.batch_no, 0)
			source_batch_values[d.batch_no] += d.amount

	# Source Batch Repack Contribution
	target_batch_source_contribution = {}
	for target_batch, source_batch_values in iteritems(target_batch_source_values):
		target_batch_source_contribution[target_batch] = {}
		total_value = sum(source_batch_values.values())
		for source_batch, value in iteritems(source_batch_values):
			if source_batch in batch_nos:
				target_batch_source_contribution[target_batch][source_batch] = value / total_value * 100

	repacked_batch_nos = list(set(repacked_batch_nos))
	return target_repack_data, repacked_batch_nos, target_batch_source_contribution


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

	source_actual_qty = get_batch_actual_qty(batch_nos)
	source_sinv_data = get_sinv_data(batch_nos)
	source_lcv_data = get_lcv_data(batch_nos)
	target_repack_data, repacked_batch_nos, target_batch_source_contribution = get_repack_entry_data(batch_nos)
	target_sinv_data = get_sinv_data(repacked_batch_nos)

	for d in source_actual_qty:
		out[d.batch_no].actual_batch_qty = d.qty

	for d in source_sinv_data:
		out[d.batch_no].direct_revenue += d.revenue
		if d.update_stock:
			out[d.batch_no].direct_qty_sold += d.qty

	for d in source_lcv_data:
		out[d.batch_no].lcv_cost += d.cost

	for d in target_sinv_data:
		source_batch_contributions = target_batch_source_contribution[d.batch_no]
		for source_batch, contribution in iteritems(source_batch_contributions):
			out[source_batch].repacked_revenue += d.revenue * contribution / 100
			if d.update_stock:
				out[source_batch].repacked_qty_sold += d.qty

	for d in target_repack_data:
		source_batch_contributions = target_batch_source_contribution[d.batch_no]
		for source_batch, contribution in iteritems(source_batch_contributions):
			out[source_batch].repack_cost += d.cost * contribution / 100

	for d in out.values():
		d.batch_revenue = flt(d.direct_revenue) + flt(d.repacked_revenue)

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
			"width": 100
		},
		{
			"label": _("Party"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 150
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
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 50
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 80
		},
		{
			"label": _("Unit Rate"),
			"fieldname": "rate",
			"fieldtype": "Currency",
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
		},
		{
			"label": _("Contribution"),
			"fieldname": "repack_contribution",
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"label": _("Update Stock"),
			"fieldname": "update_stock",
			"fieldtype": "Check",
			"width": 100
		},
	]
