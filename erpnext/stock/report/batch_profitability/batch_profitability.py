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
	source_pinv_data = get_pinv_data(batch_nos)
	source_reco_data = get_reco_data(batch_nos)

	target_repack_data, target_raw_material_data, source_consumed_qty, repacked_batch_nos, target_batch_source_contribution = get_repack_entry_data(batch_nos)
	apply_source_repack_contribution(target_repack_data, filters.get('batch_no'), target_batch_source_contribution)
	apply_source_repack_contribution(target_raw_material_data, filters.get('batch_no'), target_batch_source_contribution)

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

	out.append(get_total(source_prec_data, "Unbilled Purchase Receipts"))
	out += source_prec_data
	out.append({})

	out.append(get_total(source_pinv_data, "Purchase Invoices"))
	out += source_pinv_data
	out.append({})

	out.append(get_total(source_lcv_data, "Landed Costs"))
	out += source_lcv_data
	out.append({})

	out.append(get_total(target_repack_data, "Repack Additional Costs"))
	out += target_repack_data
	out.append({})

	out.append(get_total(target_raw_material_data, "Repack Material Costs"))
	out += target_raw_material_data
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
		d.repack_contribution = target_batch_source_contribution\
			.get(d.get('for_target_batch') or d.batch_no, {})\
			.get(source_batch, 100)

		if d.revenue is not None:
			d.revenue = d.revenue * d.repack_contribution / 100
		if d.cost is not None:
			d.cost = d.cost * d.repack_contribution / 100

def get_pinv_data(batch_nos, exclude_pinv=None):
	if batch_nos:
		exclude_pinv_cond = " and inv.name != {0}".format(frappe.db.escape(exclude_pinv)) if exclude_pinv else ""

		return frappe.db.sql("""
			select 'Purchase Invoice' as doctype, 'Supplier' as party_type, inv.supplier as party,
				inv.name, item.item_code, item.batch_no, item.stock_qty as qty, item.stock_uom as uom,
				item.base_net_amount as cost, item.base_net_rate * item.conversion_factor as rate, inv.update_stock,
				inv.posting_date
			from `tabPurchase Invoice Item` item, `tabPurchase Invoice` inv
			where inv.name = item.parent and inv.docstatus = 1 and item.batch_no in ({0}) {1}
		""".format(", ".join(['%s'] * len(batch_nos)), exclude_pinv_cond), batch_nos, as_dict=1)
	else:
		return []

def get_sinv_data(batch_nos):
	if batch_nos:
		return frappe.db.sql("""
			select 'Sales Invoice' as doctype, 'Customer' as party_type, inv.customer as party,
				inv.name, item.item_code, item.batch_no, item.stock_qty as qty, item.stock_uom as uom,
				item.base_net_amount as revenue, item.base_net_rate * item.conversion_factor as rate, inv.update_stock,
				inv.posting_date
			from `tabSales Invoice Item` item, `tabSales Invoice` inv
			where inv.name = item.parent and inv.docstatus = 1 and item.batch_no in ({0})
		""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)
	else:
		return []


def get_lcv_data(batch_nos):
	if batch_nos:
		return frappe.db.sql("""
			select 'Landed Cost Voucher' as doctype, lcv.party_type, lcv.party, pri.stock_uom as uom,
				lci.parent as name, lci.item_code, pri.batch_no, lci.applicable_charges as cost,
				lcv.posting_date
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
				item.base_net_amount as cost, item.base_net_rate * item.conversion_factor as rate,
				(item.qty - item.billed_qty) / item.qty * 100 as unbilled,
				prec.posting_date
			from `tabPurchase Receipt Item` item, `tabPurchase Receipt` prec
			where prec.name = item.parent and prec.docstatus = 1 and item.billed_qty < item.qty and item.batch_no in ({0})
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
				sle.stock_value_difference / sle.actual_qty as rate,
				sle.posting_date
			from `tabStock Ledger Entry` sle
			left join `tabStock Entry` ste on ste.name = sle.voucher_no and sle.voucher_type = 'Stock Entry'
				and ste.purpose in ('Material Receipt', 'Material Issue')
			where sle.batch_no in ({0}) and (sle.voucher_type = 'Stock Reconciliation' or ste.name is not null)
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
			item.stock_uom as uom, item.t_warehouse, item.s_warehouse, item.amount, m.is_sales_item,
			ste.posting_date
		from `tabStock Entry` ste, `tabStock Entry Detail` item, `tabItem` m
		where ste.name = item.parent and m.name = item.item_code
			and ste.docstatus = 1 and ste.purpose = 'Repack' and exists(
			select src_item.name from `tabStock Entry Detail` src_item where src_item.parent = ste.name
				and src_item.batch_no in ({0}) and ifnull(src_item.t_warehouse, '') = '')
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	# Target Rows
	target_repack_data = []
	target_raw_material_data = []
	repacked_batch_nos = []
	stock_entry_to_target_batch = {}
	warned = set()
	for d in repack_entry_data:
		if d.t_warehouse:
			target_repack_data.append(d)
			repacked_batch_nos.append(d.batch_no)

			if d.name in stock_entry_to_target_batch:
				if d.name not in warned:
					frappe.msgprint(_(
						"Warning: Repack Entry {0} has multiple target batches. Gross Profit calculation may be inaccurate")
						.format(frappe.get_desk_link("Stock Entry", d.name)))
					warned.add(d.name)
			else:
				stock_entry_to_target_batch[d.name] = d.batch_no

	# Consumed Qty
	source_consumed_qty = {}
	for batch_no in batch_nos:
		source_consumed_qty[batch_no] = 0

	# Source Rows
	target_batch_source_values = {}
	for d in repack_entry_data:
		if not d.t_warehouse and stock_entry_to_target_batch.get(d.name):
			target_batch = stock_entry_to_target_batch[d.name]

			if d.is_sales_item:
				if d.batch_no in source_consumed_qty:
					source_consumed_qty[d.batch_no] += d.qty

				source_batch_values = target_batch_source_values.setdefault(target_batch, {})
				source_batch_values.setdefault(d.batch_no, 0)
				source_batch_values[d.batch_no] += d.amount
			else:
				d.cost = d.amount
				d.rate = d.amount / d.qty if d.qty else 0
				d.for_target_batch = target_batch
				target_raw_material_data.append(d)

	# Source Batch Repack Contribution
	target_batch_source_contribution = {}
	for target_batch, source_batch_values in iteritems(target_batch_source_values):
		target_batch_source_contribution[target_batch] = {}
		total_value = sum(source_batch_values.values())
		for source_batch, value in iteritems(source_batch_values):
			if source_batch in batch_nos:
				target_batch_source_contribution[target_batch][source_batch] = value / total_value * 100

	repacked_batch_nos = list(set(repacked_batch_nos))
	return target_repack_data, target_raw_material_data, source_consumed_qty, repacked_batch_nos, target_batch_source_contribution


@frappe.whitelist()
def get_purchase_batch_cost_and_revenue(batch_nos, exclude_pinv=None):
	if isinstance(batch_nos, string_types):
		batch_nos = json.loads(batch_nos)
	batch_nos = list(set(batch_nos))

	if not batch_nos:
		return {}

	# Prepare output
	out = {}
	for batch_no in batch_nos:
		out[batch_no] = frappe._dict({
			"source_sales_revenue": 0, "source_sales_qty": 0, "source_actual_qty": 0, "source_reconciled_qty": 0,
			"source_lcv_cost": 0, "source_repack_qty": 0, "source_purchase_cost": 0,
			"repacked_sales_revenue": 0, "repacked_sales_qty": 0, "repacked_repack_qty": 0, "repacked_actual_qty": 0,
			"repacked_reconciled_qty": 0, "repacked_additional_cost": 0,
			"batch_revenue": 0,
		})

	source_pinv_data = get_pinv_data(batch_nos, exclude_pinv)
	source_sinv_data = get_sinv_data(batch_nos)
	source_lcv_data = get_lcv_data(batch_nos)
	target_repack_data, target_raw_material_data, source_consumed_qty, repacked_batch_nos, target_batch_source_contribution = get_repack_entry_data(batch_nos)
	target_sinv_data = get_sinv_data(repacked_batch_nos)
	source_reco_data = get_reco_data(batch_nos)
	target_reco_data = get_reco_data(repacked_batch_nos)
	source_actual_qty = get_batch_actual_qty(batch_nos)
	target_actual_qty = get_batch_actual_qty(repacked_batch_nos)

	for d in source_pinv_data:
		out[d.batch_no].source_purchase_cost += d.cost

	for d in source_sinv_data:
		out[d.batch_no].source_sales_revenue += d.revenue
		if d.update_stock:
			out[d.batch_no].source_sales_qty += d.qty

	for d in source_lcv_data:
		out[d.batch_no].source_lcv_cost += d.cost

	for d in target_sinv_data:
		source_batch_contributions = target_batch_source_contribution.get(d.batch_no, {})
		for source_batch, contribution in iteritems(source_batch_contributions):
			out[source_batch].repacked_sales_revenue += d.revenue * contribution / 100
			if d.update_stock:
				out[source_batch].repacked_sales_qty += d.qty

	for d in target_repack_data:
		source_batch_contributions = target_batch_source_contribution.get(d.batch_no, {})
		for source_batch, contribution in iteritems(source_batch_contributions):
			out[source_batch].repacked_additional_cost += d.cost * contribution / 100
			out[source_batch].repacked_repack_qty += d.qty

	for d in target_raw_material_data:
		source_batch_contributions = target_batch_source_contribution.get(d.for_target_batch, {})
		for source_batch, contribution in iteritems(source_batch_contributions):
			out[source_batch].repacked_additional_cost += d.cost * contribution / 100

	for source_batch, consumed_qty in iteritems(source_consumed_qty):
		out[source_batch].source_repack_qty = consumed_qty

	for d in source_actual_qty:
		out[d.batch_no].source_actual_qty = d.qty

	for d in target_actual_qty:
		source_batch_contributions = target_batch_source_contribution.get(d.batch_no, {})
		for source_batch in source_batch_contributions.keys():
			out[source_batch].repacked_actual_qty += d.qty

	for d in source_reco_data:
		out[d.batch_no].source_reconciled_qty += d.qty

	for d in target_reco_data:
		source_batch_contributions = target_batch_source_contribution.get(d.batch_no, {})
		for source_batch in source_batch_contributions.keys():
			out[source_batch].repacked_reconciled_qty += d.qty

	for d in out.values():
		d.batch_revenue = flt(d.source_sales_revenue) + flt(d.repacked_sales_revenue)

	return out


def update_item_batch_incoming_rate(items, from_date=None, to_date=None):
	incoming_rate_data = get_sales_item_batch_incoming_rate(items, from_date=from_date, to_date=to_date)

	for d in items:
		if d.get('item_code') or d.get('batch_no'):
			batch_or_item = 'batch_incoming_rate' if d.get('batch_no') else 'item_incoming_rate'
			d.valuation_rate = flt(incoming_rate_data[batch_or_item].get(d.get('batch_no') or d.get('item_code')))


def get_sales_item_batch_incoming_rate(items, from_date=None, to_date=None):
	if isinstance(items, string_types):
		items = json.loads(items)

	item_codes = list(set([d.get('item_code') for d in items if d.get('item_code') and not d.get('batch_no')]))
	batch_nos = list(set([d.get('batch_no') for d in items if d.get('batch_no')]))

	return frappe._dict({
		"batch_incoming_rate": get_batch_incoming_rate(batch_nos),
		"item_incoming_rate": get_item_valuation_rate(item_codes, from_date, to_date)
	})


def get_item_valuation_rate(item_codes, from_date=None, to_date=None):
	if not item_codes:
		return {}

	item_values = {item_code: frappe._dict({'cost': 0, 'qty': 0}) for item_code in item_codes}

	bin_data = frappe.db.sql("""
		select bin.item_code, sum(bin.actual_qty) as qty, sum(bin.stock_value) as cost
		from tabBin bin
		where bin.item_code in %s
		group by bin.item_code
	""", [item_codes], as_dict=1)

	for d in bin_data:
		item_values[d.item_code].cost += d.cost
		item_values[d.item_code].qty += d.qty

	po_conditions = []
	po_values = {'item_codes': item_codes}
	if from_date:
		po_conditions.append("po.schedule_date >= %(from_date)s")
		po_values['from_date'] = from_date
	if to_date:
		po_conditions.append("po.schedule_date <= %(to_date)s")
		po_values['to_date'] = to_date

	po_conditions = "and {0}".format(" and ".join(po_conditions)) if po_conditions else ""

	po_data = frappe.db.sql("""
		select
			item.item_code,
			sum(if(item.qty - item.received_qty < 0, 0, item.qty - item.received_qty) * item.conversion_factor) as qty,
			sum(if(item.qty - item.received_qty < 0, 0, item.qty - item.received_qty) * item.conversion_factor * item.landed_rate) as cost
		from `tabPurchase Order Item` item
		inner join `tabPurchase Order` po on po.name = item.parent
		where item.docstatus < 2 and po.status != 'Closed' and item.item_code in %(item_codes)s {0}
		group by item.item_code
	""".format(po_conditions), po_values, as_dict=1)

	for d in po_data:
		item_values[d.item_code].cost += d.cost
		item_values[d.item_code].qty += d.qty

	out = {item_code: item_value.cost / item_value.qty if item_value.qty else 0 for (item_code, item_value) in item_values.items()}
	return out

def get_batch_incoming_rate(batch_nos):
	if not batch_nos:
		return {}

	# get repack entries that have batch_nos as target
	repack_entry_data = frappe.db.sql("""
		select ste.name, item.batch_no, item.s_warehouse, item.t_warehouse, item.amount, item.transfer_qty as qty,
			item.additional_cost
		from `tabStock Entry` ste, `tabStock Entry Detail` item
		where ste.name = item.parent and ste.purpose = 'Repack' and ste.docstatus = 1 and exists(
			select t_item.name from `tabStock Entry Detail` t_item where t_item.parent = ste.name
				and t_item.batch_no in %s and ifnull(t_item.t_warehouse, '') != '')
	""", [batch_nos], as_dict=1)

	# create maps for stock entry -> target repack rows and stock_entry -> source repack rows
	stock_entry_to_target_items = {}
	stock_entry_to_source_items = {}
	for repack_entry_row in repack_entry_data:
		if repack_entry_row.s_warehouse:
			stock_entry_to_source_items.setdefault(repack_entry_row.name, []).append(repack_entry_row)
		if repack_entry_row.t_warehouse:
			stock_entry_to_target_items.setdefault(repack_entry_row.name, []).append(repack_entry_row)

	# create map for repacked batch -> data about its source items and costs
	target_batch_source_map = {}
	source_batch_nos = []
	for ste_name, target_items in stock_entry_to_target_items.items():
		total_incoming = sum([d.amount for d in target_items])

		for target_item in target_items:
			target_batch_data = target_batch_source_map.setdefault(target_item.batch_no, {}).setdefault(ste_name, frappe._dict())
			target_batch_data.qty = target_item.qty
			target_batch_data.additional_cost = target_item.additional_cost
			target_batch_data.contribution = (target_item.amount / total_incoming) * 100 if total_incoming\
				else 100 / len(target_items)

			source_rows = stock_entry_to_source_items.get(ste_name, [])
			target_batch_data.source_batches = [(d.batch_no, d.qty) for d in source_rows if d.batch_no]
			target_batch_data.source_non_batch_cost = sum([d.amount for d in source_rows if not d.batch_no])

			source_batch_nos += list(set([d.batch_no for d in source_rows if d.batch_no]))

	# get cost of batch_nos in argument and batch_nos in repack entry
	all_batch_nos = list(set(batch_nos + source_batch_nos))
	sle_data = frappe.db.sql("""
		select sle.batch_no, sum(sle.stock_value_difference) as cost, sum(sle.actual_qty) as qty
		from `tabStock Ledger Entry` sle
		where sle.batch_no in %s and sle.actual_qty > 0 and sle.voucher_type in ('Purchase Receipt', 'Purchase Invoice')
		group by sle.batch_no
	""", [all_batch_nos], as_dict=1) if all_batch_nos else []

	# create map for batch_no -> {'cost': ..., 'qty': ...}
	batch_to_incoming_values = {}
	for d in sle_data:
		batch_to_incoming_values[d.batch_no] = d

	# add repack raw material costs
	for target_batch_no, stes in target_batch_source_map.items():
		for ste_name, target_batch_data in stes.items():
			target_batch_incoming_value = batch_to_incoming_values.setdefault(target_batch_no, frappe._dict({'cost': 0, 'qty': 0}))

			target_batch_cost = target_batch_data.source_non_batch_cost
			target_batch_cost += target_batch_data.additional_cost

			for source_batch_no, source_batch_qty in target_batch_data.source_batches:
				source_batch_incoming_value = batch_to_incoming_values.get(source_batch_no, frappe._dict())
				target_batch_cost += flt(source_batch_incoming_value.cost) / flt(source_batch_incoming_value.qty) * source_batch_qty\
					if flt(source_batch_incoming_value.qty) else 0

			target_batch_cost = target_batch_cost * target_batch_data.contribution / 100

			target_batch_incoming_value.qty += target_batch_data.qty
			target_batch_incoming_value.cost += target_batch_cost

	out = {}
	for batch_no in batch_nos:
		batch_incoming_value = batch_to_incoming_values.get(batch_no, frappe._dict())
		out[batch_no] = batch_incoming_value.cost / batch_incoming_value.qty if batch_incoming_value else 0

	return out

def get_columns(filters):
	return [
		{
			"label": _("Document Type"),
			"fieldname": "doctype",
			"fieldtype": "Data",
			"width": 190
		},
		{
			"label": _("Document No"),
			"fieldname": "name",
			"fieldtype": "Dynamic Link",
			"options": "doctype",
			"width": 100
		},
		{
			"label": _("Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 80
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
			"label": _("% Contribution"),
			"fieldname": "repack_contribution",
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"label": _("% Unbilled"),
			"fieldname": "unbilled",
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
