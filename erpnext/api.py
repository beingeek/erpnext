from __future__ import unicode_literals
import frappe

from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import getdate, validate_email_add, today, add_years,add_days,format_datetime, flt
from datetime import datetime
from frappe.model.naming import make_autoname
from frappe import throw, _, scrub
from frappe.utils import cint
import frappe.permissions
from frappe.model.document import Document
import json
import collections
from erpnext.controllers.sales_and_purchase_return import make_return_doc
# import urllib
# import urllib2

import json
from six import string_types, iteritems

@frappe.whitelist()
def test():
	return "test"

@frappe.whitelist()
def submitLcv(doc):
	doc = frappe.get_doc(json.loads(doc))
	set_local_name(doc)
	doc.docstatus=1
	dt=doc.submit();
	if dt:
		return "In"
	else:
		return "out"

def set_local_name(doc):
	def _set_local_name(d):
		if doc.get('__islocal') or d.get('__islocal'):
			d.localname = d.name
			d.name = None

	_set_local_name(doc)
	for child in doc.get_all_children():
		_set_local_name(child)

	if doc.get("__newname"):
		doc.name = doc.get("__newname")

@frappe.whitelist()
def makeReturnReceipt(doc,method):
	make_return_doc("Purchase Receipt",doc)


@frappe.whitelist()
def validateReference(ref_no,party):
	data=frappe.db.sql("""select mjea.idx,mje.name from `tabMaster Journal Entry` as mje inner join `tabMaster Journal Entry Account` as mjea on mje.name=mjea.parent where mjea.reference_name=%s and mjea.party=%s and mje.docstatus=1""",(ref_no,party),as_dict=1)
	#return len(data)
	if len(data)>=1:
		return data[0]
	else:
		return "False"
		
def get_items_from_purchase_receipts(doc):
		doc.set("items", [])
		for pr in doc.get("purchase_receipts"):
			if pr.receipt_document_type and pr.receipt_document:
				pr_items = frappe.db.sql("""select pr_item.item_code, pr_item.item_name, pr_item.description,
					pr_item.qty, pr_item.base_rate, pr_item.base_amount, pr_item.name, 						pr_item.cost_center,pr_item.gross_weight_lbs
					from `tab{doctype} Item` pr_item where parent = %s
					and exists(select name from tabItem where name = pr_item.item_code and is_stock_item = 1)
					""".format(doctype=pr.receipt_document_type), pr.receipt_document, as_dict=True)

				for d in pr_items:
					item = doc.append("items")
					item.item_code = d.item_code
					item.description = d.item_name
					item.qty = d.qty
					item.rate = d.base_rate
					item.cost_center = d.cost_center or \
						erpnext.get_default_cost_center(doc.company)
					item.amount = d.base_amount
					item.receipt_document_type = pr.receipt_document_type
					item.receipt_document = pr.receipt_document
					item.purchase_receipt_item = d.name
					sitem = frappe.get_doc("Item", d.item_code)
					if not d.gross_weight_lbs:
						item.gross_weight=float(d.qty)*float(sitem.gross_weight)
					else:
						item.gross_weight=float(d.qty)*float(d.gross_weight_lbs)

@frappe.whitelist()
def paymentReferenceDate(row,reference_doctype,reference_name):
	result_list2=[]
	d={}
	d["row"]=row
	doc = frappe.get_doc(reference_doctype, reference_name)
	d["cheque_no"] = ""
	d["due_date"] = doc.get("due_date") or doc.get("posting_date")
	if reference_doctype == "Journal Entry":
		d["cheque_no"] = doc.cheque_no
		d["due_date"] = doc.posting_date
	elif reference_doctype == "Purchase Invoice":
		d["cheque_no"] = doc.bill_no
		d["due_date"] = doc.received_date
	elif reference_doctype == "Sales Invoice":
		d["due_date"] = doc.posting_date
	elif reference_doctype == "Landed Cost Voucher":
		d["cheque_no"] = doc.bill_no
		d["cheque_no"] = doc.bill_no
	
	result_list2.append(d)
	return result_list2

@frappe.whitelist()
def get_item_custom_projected_qty(date, item_codes, exclude_so=None):
	from_date = frappe.utils.getdate(date)
	to_date = frappe.utils.add_days(from_date, 4)

	if isinstance(item_codes, string_types):
		item_codes = json.loads(item_codes)

	po_data = frappe.db.sql("""
		select
			i.item_code, po.schedule_date as date,
			sum((i.qty - ifnull(i.received_qty, 0)) * i.conversion_factor) as qty
		from `tabPurchase Order Item` i
		inner join `tabPurchase Order` po on po.name = i.parent
		where po.docstatus < 2 and po.status != 'Closed' and ifnull(i.received_qty, 0) < ifnull(i.qty, 0)
			and po.schedule_date between %s and %s and i.item_code in ({0})
		group by i.item_code, po.schedule_date
	""".format(", ".join(['%s']*len(item_codes))), [from_date, to_date] + item_codes, as_dict=1)

	exclude_so_cond = " and so.name != '{0}'".format(frappe.db.escape(exclude_so)) if exclude_so else ""

	so_data = frappe.db.sql("""
		select
			i.item_code, so.delivery_date as date,
			sum((i.qty - ifnull(i.delivered_qty, 0)) * i.conversion_factor) as qty
		from `tabSales Order Item` i
		inner join `tabSales Order` so on so.name = i.parent
		where so.docstatus < 2 and so.status != 'Closed' and ifnull(i.delivered_qty, 0) < ifnull(i.qty, 0)
			and so.delivery_date between %s and %s and i.item_code in ({0}) {1}
		group by i.item_code, so.delivery_date
	""".format(", ".join(['%s'] * len(item_codes)), exclude_so_cond), [from_date, to_date] + item_codes, as_dict=1)

	sinv_data = frappe.db.sql("""
		select
			i.item_code, sinv.delivery_date as date,
			sum(i.stock_qty) as qty
		from `tabSales Invoice Item` i
		inner join `tabSales Invoice` sinv on sinv.name = i.parent
		where sinv.docstatus = 0 and ifnull(i.sales_order, '') = ''
			and sinv.delivery_date between %s and %s and i.item_code in ({0})
		group by i.item_code, sinv.delivery_date
	""".format(", ".join(['%s'] * len(item_codes))), [from_date, to_date] + item_codes, as_dict=1)

	bin_data = frappe.db.sql("""
		select item_code, sum(actual_qty) as actual_qty, sum(projected_qty) as projected_qty
		from tabBin
		where item_code in ({0})
		group by item_code
	""".format(", ".join(['%s']*len(item_codes))), item_codes, as_dict=1)

	out = {}

	template = {
		"po_day_1": 0, "po_day_2": 0, "po_day_3": 0, "po_day_4": 0, "po_day_5": 0,
		"so_day_1": 0, "so_day_2": 0, "so_day_3": 0, "so_day_4": 0, "so_day_5": 0,
		"actual_qty": 0, "projected_qty": 0
	}

	for d in po_data:
		out.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, from_date)
		out[d.item_code]['po_day_' + str(i+1)] = d.qty

	for d in so_data:
		out.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, from_date)
		out[d.item_code].setdefault('so_day_' + str(i+1), 0)
		out[d.item_code]['so_day_' + str(i+1)] += d.qty

	for d in sinv_data:
		out.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, from_date)
		out[d.item_code].setdefault('so_day_' + str(i+1), 0)
		out[d.item_code]['so_day_' + str(i+1)] += d.qty

	for d in bin_data:
		out.setdefault(d.item_code, template.copy())
		out[d.item_code]['actual_qty'] = d.actual_qty

	for item_code, d in iteritems(out):
		d['projected_qty'] = d['actual_qty']
		for i in range(2):
			d['projected_qty'] += d['po_day_' + str(i+1)]
			d['projected_qty'] -= d['so_day_' + str(i+1)]

	return out

@frappe.whitelist()
def get_batch_cost_and_revenue(batch_nos):
	if isinstance(batch_nos, string_types):
		batch_nos = json.loads(batch_nos)
	batch_nos = list(set(batch_nos))

	if not batch_nos:
		return {}

	# Get Data
	repacked_batch_map = {}
	repacked_batch_nos = []
	for source_batch_no in batch_nos:
		repacked_batches = frappe.db.sql("""
			select tar.batch_no as target_batch, sum(tar.additional_cost) as additional_cost
			from `tabStock Entry` p
			inner join `tabStock Entry Detail` tar on tar.parent = p.name
			where p.docstatus = 1 and p.purpose = 'Repack' and ifnull(tar.t_warehouse, '') != '' and exists(
				select src.name from `tabStock Entry Detail` src where src.parent = p.name and src.batch_no = %s
					and ifnull(src.t_warehouse, '') = '')
			group by tar.batch_no
		""", source_batch_no, as_dict=1)

		for d in repacked_batches:
			repacked_batch_dict = repacked_batch_map.setdefault(d.target_batch, frappe._dict({
				"source_batch_nos": set(), "additional_cost": 0
			}))
			repacked_batch_dict.source_batch_nos.add(source_batch_no)
			repacked_batch_dict.additional_cost += d.additional_cost
			repacked_batch_nos.append(d.target_batch)

	source_actual_batch_qty = frappe.db.sql("""
		select batch_no, sum(actual_qty) as qty
		from `tabStock Ledger Entry`
		where batch_no in ({0}) and is_cancelled = 'No'
		group by batch_no
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	source_batch_revenue = frappe.db.sql("""
		select batch_no, sum(base_net_amount) as amount, sum(stock_qty) as qty
		from `tabSales Invoice Item`
		where docstatus = 1 and batch_no in ({0})
		group by batch_no
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	source_batch_qty_sold = frappe.db.sql("""
		select item.batch_no, sum(item.stock_qty) as qty
		from `tabSales Invoice Item` item, `tabSales Invoice` inv
		where inv.name = item.parent and inv.docstatus = 1 and inv.update_stock = 1 and item.batch_no in ({0})
		group by item.batch_no
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	target_batch_revenue = []
	target_batch_qty_sold = []
	if repacked_batch_nos:
		target_batch_revenue = frappe.db.sql("""
			select batch_no, sum(base_net_amount) as amount
			from `tabSales Invoice Item`
			where docstatus = 1 and batch_no in ({0})
			group by batch_no
		""".format(", ".join(['%s'] * len(repacked_batch_nos))), repacked_batch_nos, as_dict=1)

		target_batch_qty_sold = frappe.db.sql("""
			select item.batch_no, sum(item.stock_qty) as qty
			from `tabSales Invoice Item` item, `tabSales Invoice` inv
			where inv.name = item.parent and inv.docstatus = 1 and inv.update_stock = 1 and item.batch_no in ({0})
			group by item.batch_no
		""".format(", ".join(['%s'] * len(repacked_batch_nos))), repacked_batch_nos, as_dict=1)

	batch_lc_amount = frappe.db.sql("""
		select batch_no, sum(landed_cost_voucher_amount) as amount
		from `tabPurchase Receipt Item`
		where docstatus = 1 and batch_no in ({0})
		group by batch_no
	""".format(", ".join(['%s'] * len(batch_nos))), batch_nos, as_dict=1)

	# Prepare output
	out = {}
	for batch_no in batch_nos:
		out[batch_no] = frappe._dict({
			"direct_revenue": 0, "direct_qty_sold": 0,
			"repacked_revenue": 0, "repacked_qty_sold": 0,
			"lcv_cost": 0, "repack_cost": 0, "actual_batch_qty": 0,
			"batch_revenue": 0
		})

	for d in source_actual_batch_qty:
		out[d.batch_no].actual_batch_qty = d.qty

	for d in batch_lc_amount:
		out[d.batch_no].lcv_cost = d.amount

	for d in source_batch_revenue:
		out[d.batch_no].direct_revenue = d.amount
	for d in source_batch_qty_sold:
		out[d.batch_no].direct_qty_sold = d.qty

	for d in target_batch_revenue:
		repacked_batch_dict = repacked_batch_map[d.batch_no]
		source_batch_nos = list(repacked_batch_dict.get('source_batch_nos', set()))
		for source_batch in source_batch_nos:
			out[source_batch].repacked_revenue += d.amount / len(source_batch_nos)

	for d in target_batch_qty_sold:
		repacked_batch_dict = repacked_batch_map[d.batch_no]
		source_batch_nos = list(repacked_batch_dict.get('source_batch_nos', set()))
		for source_batch in source_batch_nos:
			out[source_batch].repacked_qty_sold += d.qty / len(source_batch_nos)

	for target_batch, repacked_batch_dict in iteritems(repacked_batch_map):
		source_batch_nos = list(repacked_batch_dict.get('source_batch_nos', set()))
		if len(source_batch_nos) > 1:
			frappe.msgprint(_("Multiple Source Batches found for Repacked Batch {0}. This may result in inaccurate values. Source Batches: {1}")
				.format(target_batch, ", ".join(source_batch_nos)))

		for source_batch in source_batch_nos:
			out[source_batch].repack_cost += repacked_batch_dict.additional_cost / len(source_batch_nos)

	for d in out.values():
		d.batch_revenue = flt(d.direct_revenue) + flt(d.repacked_revenue)

	return out

@frappe.whitelist()
def get_party_default_items(args, existing_item_codes=None):
	from erpnext.stock.get_item_details import get_item_details

	if not existing_item_codes:
		existing_item_codes = []
	if isinstance(args, string_types):
		args = json.loads(args)
	if isinstance(existing_item_codes, string_types):
		existing_item_codes = json.loads(existing_item_codes)

	if not args.get('customer') and not args.get('supplier'):
		return []

	if args.get('customer'):
		party_type = 'Customer'
		party = args.get('customer')
	else:
		party_type = 'Supplier'
		party = args.get('supplier')

	default_items = frappe.get_all("Customer Default Item", fields=['item_code'],
		filters={"parenttype": party_type, "parent": party})
	item_codes = [d.item_code for d in default_items
		if d.item_code not in existing_item_codes and not cint(frappe.get_cached_value("Item", d.item_code, "disabled"))]

	out = []
	for item_code in item_codes:
		item_args = args.copy()
		item_args['item_code'] = item_code

		out.append(get_item_details(item_args))

	return out

@frappe.whitelist()
def add_item_codes_to_party_default_items(party_type, party, item_codes):
	if isinstance(item_codes, string_types):
		item_codes = json.loads(item_codes)

	doc = frappe.get_doc(party_type, party)

	existing_item_codes = map(lambda d: d.item_code, doc.default_items_tbl)
	item_codes = filter(lambda item_code: item_code not in existing_item_codes, item_codes)

	if not item_codes:
		frappe.msgprint(_("Selected items already exists in {0} Default Items").format(party_type))
		return

	for item_code in item_codes:
		doc.append("default_items_tbl", {
			"item_code": item_code,
			"item_name": frappe.get_cached_value("Item", item_code, "item_name")
		})

	doc.save()

	frappe.msgprint(_("Selected items added to {0} Default Items").format(party_type))

@frappe.whitelist()
def remove_item_codes_from_party_default_items(party_type, party, item_codes):
	if isinstance(item_codes, string_types):
		item_codes = json.loads(item_codes)

	doc = frappe.get_doc(party_type, party)
	doc.default_items_tbl = filter(lambda d: d.item_code not in item_codes, doc.default_items_tbl)
	for i, d in enumerate(doc.default_items_tbl):
		d.idx = i + 1

	doc.save()

	frappe.msgprint(_("Selected items removed from {0} Default Items").format(party_type))

@frappe.whitelist()
def update_special_price(args):
	from erpnext.accounts.doctype.pricing_rule.pricing_rule import get_pricing_rules, filter_pricing_rules
	from erpnext.stock.get_item_details import process_args

	if isinstance(args, string_types):
		args = json.loads(args)

	args.update(args['items'][0])
	args = process_args(args)

	pricing_rules = get_pricing_rules(args)
	existing_pricing_rule = filter_pricing_rules(args, pricing_rules)

	if not existing_pricing_rule or cint(args.create_new):
		doc = frappe.new_doc("Pricing Rule")
		doc.update({
			"applicable_for": "Customer",
			"customer": args.customer,
			"apply_on": "Item Code",
			"item_code": args.item_code,
			"title": frappe.model.naming.make_autoname("{}/{}".format(args.customer, args.item_code) + "-.#####", "Pricing Rule"),
			"selling": 1
		})

		if existing_pricing_rule:
			priority = cint(frappe.db.get_value("Pricing Rule", existing_pricing_rule.name, "priority")) + 1
			doc.priority = priority
	else:
		doc = frappe.get_doc("Pricing Rule", existing_pricing_rule.name)

	doc.rate_or_discount = "Rate"
	doc.rate = args.new_rate
	doc.valid_from = args.valid_from
	doc.valid_upto = args.valid_upto
	doc.reason = args.reason

	doc.margin_type = ""
	doc.save()
