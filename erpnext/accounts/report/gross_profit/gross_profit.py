# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _, scrub
from erpnext.stock.utils import get_incoming_rate
from erpnext.controllers.queries import get_match_cond
from frappe.utils import flt, cint
from six import string_types
import json


def execute(filters=None):
	if not filters: filters = frappe._dict()
	filters.currency = frappe.get_cached_value('Company',  filters.company,  "default_currency")

	gross_profit_data = GrossProfitGenerator(filters)

	data = []

	group_wise_columns = frappe._dict({
		"invoice": ["parent", "customer", "customer_group", "posting_date","item_code", "item_name","item_group", "brand", "description", \
			"warehouse", "qty", "base_rate", "buying_rate", "base_amount",
			"buying_amount", "gross_profit", "gross_profit_percent", "project"],
		"item_code": ["item_code", "item_name", "brand", "description", "qty", "base_rate",
			"buying_rate", "base_amount", "buying_amount", "gross_profit", "gross_profit_percent"],
		"warehouse": ["warehouse", "qty", "base_rate", "buying_rate", "base_amount", "buying_amount",
			"gross_profit", "gross_profit_percent"],
		"brand": ["brand", "qty", "base_rate", "buying_rate", "base_amount", "buying_amount",
			"gross_profit", "gross_profit_percent"],
		"item_group": ["item_group", "qty", "base_rate", "buying_rate", "base_amount", "buying_amount",
			"gross_profit", "gross_profit_percent"],
		"customer": ["customer", "customer_group", "qty", "base_rate", "buying_rate", "base_amount", "buying_amount",
			"gross_profit", "gross_profit_percent"],
		"customer_group": ["customer_group", "qty", "base_rate", "buying_rate", "base_amount", "buying_amount",
			"gross_profit", "gross_profit_percent"],
		"sales_person": ["sales_person", "allocated_amount", "qty", "base_rate", "buying_rate", "base_amount", "buying_amount",
			"gross_profit", "gross_profit_percent"],
		"project": ["project", "base_amount", "buying_amount", "gross_profit", "gross_profit_percent"],
		"territory": ["territory", "base_amount", "buying_amount", "gross_profit", "gross_profit_percent"]
	})

	columns = get_columns(group_wise_columns, filters)

	for src in gross_profit_data.grouped_data:
		row = []
		for col in group_wise_columns.get(scrub(filters.group_by)):
			row.append(src.get(col))

		row.append(filters.currency)
		data.append(row)

	return columns, data

def get_columns(group_wise_columns, filters):
	columns = []
	column_map = frappe._dict({
		"parent": _("Sales Invoice") + ":Link/Sales Invoice:120",
		"posting_date": _("Posting Date") + ":Date:100",
		"posting_time": _("Posting Time") + ":Data:100",
		"item_code": _("Item Code") + ":Link/Item:100",
		"item_name": _("Item Name") + ":Data:100",
		"item_group": _("Item Group") + ":Link/Item Group:100",
		"brand": _("Brand") + ":Link/Brand:100",
		"description": _("Description") +":Data:100",
		"warehouse": _("Warehouse") + ":Link/Warehouse:100",
		"qty": _("Qty") + ":Float:80",
		"base_rate": _("Avg. Selling Rate") + ":Currency/currency:100",
		"buying_rate": _("Valuation Rate") + ":Currency/currency:100",
		"base_amount": _("Selling Amount") + ":Currency/currency:100",
		"buying_amount": _("Buying Amount") + ":Currency/currency:100",
		"gross_profit": _("Gross Profit") + ":Currency/currency:100",
		"gross_profit_percent": _("Gross Profit %") + ":Percent:100",
		"project": _("Project") + ":Link/Project:100",
		"sales_person": _("Sales person"),
		"allocated_amount": _("Allocated Amount") + ":Currency/currency:100",
		"customer": _("Customer") + ":Link/Customer:100",
		"customer_group": _("Customer Group") + ":Link/Customer Group:100",
		"territory": _("Territory") + ":Link/Territory:100"
	})

	for col in group_wise_columns.get(scrub(filters.group_by)):
		columns.append(column_map.get(col))

	columns.append({
		"fieldname": "currency",
		"label" : _("Currency"),
		"fieldtype": "Link",
		"options": "Currency",
		"hidden": 1
	})

	return columns

class GrossProfitGenerator(object):
	def __init__(self, filters=None):
		self.data = []
		self.average_buying_rate = {}
		self.filters = frappe._dict(filters)
		self.load_invoice_items()
		self.load_stock_ledger_entries()
		self.load_product_bundle()
		self.load_non_stock_items()
		self.get_returned_invoice_items()
		self.process()

	def process(self):
		self.grouped = {}
		self.grouped_data = []

		self.currency_precision = cint(frappe.db.get_default("currency_precision")) or 3
		self.float_precision = cint(frappe.db.get_default("float_precision")) or 2

		for row in self.si_list:
			if self.skip_row(row, self.product_bundles):
				continue

			row.base_amount = flt(row.base_net_amount, self.currency_precision)

			product_bundles = []
			if row.update_stock:
				product_bundles = self.product_bundles.get(row.parenttype, {}).get(row.parent, frappe._dict())
			elif row.dn_detail:
				product_bundles = self.product_bundles.get("Delivery Note", {})\
					.get(row.delivery_note, frappe._dict())
				row.item_row = row.dn_detail

			# get buying amount
			if row.item_code in product_bundles:
				row.buying_amount = flt(self.get_buying_amount_from_product_bundle(row,
					product_bundles[row.item_code]), self.currency_precision)
			else:
				row.buying_amount = flt(self.get_buying_amount(row, row.item_code),
					self.currency_precision)

			# get buying rate
			if row.qty:
				row.buying_rate = flt(row.buying_amount / row.qty, self.float_precision)
				row.base_rate = flt(row.base_amount / row.qty, self.float_precision)
			else:
				row.buying_rate, row.base_rate = 0.0, 0.0

			# calculate gross profit
			row.gross_profit = flt(row.base_amount - row.buying_amount, self.currency_precision)
			if row.base_amount:
				row.gross_profit_percent = flt((row.gross_profit / row.base_amount) * 100.0, self.currency_precision)
			else:
				row.gross_profit_percent = 0.0

			# add to grouped
			self.grouped.setdefault(row.get(scrub(self.filters.group_by)), []).append(row)

		if self.grouped:
			self.get_average_rate_based_on_group_by()

	def get_average_rate_based_on_group_by(self):
		# sum buying / selling totals for group
		for key in list(self.grouped):
			if self.filters.get("group_by") != "Invoice":
				for i, row in enumerate(self.grouped[key]):
					if i==0:
						new_row = row
					else:
						new_row.qty += row.qty
						new_row.buying_amount += flt(row.buying_amount, self.currency_precision)
						new_row.base_amount += flt(row.base_amount, self.currency_precision)
				new_row = self.set_average_rate(new_row)
				self.grouped_data.append(new_row)
			else:
				for i, row in enumerate(self.grouped[key]):
					if row.parent in self.returned_invoices \
							and row.item_code in self.returned_invoices[row.parent]:
						returned_item_rows = self.returned_invoices[row.parent][row.item_code]
						for returned_item_row in returned_item_rows:
							row.qty += returned_item_row.qty
							row.base_amount += flt(returned_item_row.base_amount, self.currency_precision)
						row.buying_amount = flt(row.qty * row.buying_rate, self.currency_precision)
					if row.qty or row.base_amount:
						row = self.set_average_rate(row)
						self.grouped_data.append(row)

	def set_average_rate(self, new_row):
		new_row.gross_profit = flt(new_row.base_amount - new_row.buying_amount, self.currency_precision)
		new_row.gross_profit_percent = flt(((new_row.gross_profit / new_row.base_amount) * 100.0), self.currency_precision) \
			if new_row.base_amount else 0
		new_row.buying_rate = flt(new_row.buying_amount / new_row.qty, self.float_precision) if new_row.qty else 0
		new_row.base_rate = flt(new_row.base_amount / new_row.qty, self.float_precision) if new_row.qty else 0

		return new_row

	def get_returned_invoice_items(self):
		returned_invoices = frappe.db.sql("""
			select
				si.name, si_item.item_code, si_item.stock_qty as qty, si_item.base_net_amount as base_amount, si.return_against
			from
				`tabSales Invoice` si, `tabSales Invoice Item` si_item
			where
				si.name = si_item.parent
				and si.docstatus = 1
				and si.is_return = 1
		""", as_dict=1)

		self.returned_invoices = frappe._dict()
		for inv in returned_invoices:
			self.returned_invoices.setdefault(inv.return_against, frappe._dict())\
				.setdefault(inv.item_code, []).append(inv)

	def skip_row(self, row, product_bundles):
		if self.filters.get("group_by") != "Invoice":
			if not row.get(scrub(self.filters.get("group_by", ""))):
				return True
		elif row.get("is_return") == 1:
			return True

	def get_buying_amount_from_product_bundle(self, row, product_bundle):
		buying_amount = 0.0
		for packed_item in product_bundle:
			if packed_item.get("parent_detail_docname")==row.item_row:
				buying_amount += self.get_buying_amount(row, packed_item.item_code)

		return flt(buying_amount, self.currency_precision)

	def get_buying_amount(self, row, item_code):
		# IMP NOTE
		# stock_ledger_entries should already be filtered by item_code and warehouse and
		# sorted by posting_date desc, posting_time desc
		if item_code in self.non_stock_items:
			#Issue 6089-Get last purchasing rate for non-stock item
			item_rate = self.get_last_purchase_rate(item_code)
			return flt(row.qty) * item_rate

		else:
			my_sle = self.sle.get((item_code, row.warehouse))
			if (row.update_stock or row.dn_detail) and my_sle:
				parenttype, parent = row.parenttype, row.parent
				if row.dn_detail:
					parenttype, parent = "Delivery Note", row.delivery_note

				for i, sle in enumerate(my_sle):
					# find the stock valution rate from stock ledger entry
					if sle.voucher_type == parenttype and parent == sle.voucher_no and \
						sle.voucher_detail_no == row.item_row:
							previous_stock_value = len(my_sle) > i+1 and \
								flt(my_sle[i+1].stock_value) or 0.0
							if previous_stock_value:
								return (previous_stock_value - flt(sle.stock_value)) * flt(row.qty) / abs(flt(sle.qty))
							else:
								return flt(row.qty) * self.get_average_buying_rate(row, item_code)
			else:
				return flt(row.qty) * self.get_average_buying_rate(row, item_code)

		return 0.0

	def get_average_buying_rate(self, row, item_code):
		args = row
		if not item_code in self.average_buying_rate:
			if item_code in self.non_stock_items:
				self.average_buying_rate[item_code] = flt(frappe.db.sql("""
					select sum(base_net_amount) / sum(qty * conversion_factor)
					from `tabPurchase Invoice Item`
					where item_code = %s and docstatus=1""", item_code)[0][0])
			else:
				args.update({
					'voucher_type': row.parenttype,
					'voucher_no': row.parent,
					'allow_zero_valuation': True,
					'company': self.filters.company
				})

				average_buying_rate = get_incoming_rate(args)
				self.average_buying_rate[item_code] =  flt(average_buying_rate)

		return self.average_buying_rate[item_code]

	def get_last_purchase_rate(self, item_code):
		if self.filters.to_date:
			last_purchase_rate = frappe.db.sql("""
			select (a.base_rate / a.conversion_factor)
			from `tabPurchase Invoice Item` a
			where a.item_code = %s and a.docstatus=1
			and modified <= %s
			order by a.modified desc limit 1""", (item_code, self.filters.to_date))
		else:
			last_purchase_rate = frappe.db.sql("""
			select (a.base_rate / a.conversion_factor)
			from `tabPurchase Invoice Item` a
			where a.item_code = %s and a.docstatus=1
			order by a.modified desc limit 1""", item_code)
		return flt(last_purchase_rate[0][0]) if last_purchase_rate else 0

	def load_invoice_items(self):
		conditions = ""
		if self.filters.company:
			conditions += " and company = %(company)s"
		if self.filters.from_date:
			conditions += " and posting_date >= %(from_date)s"
		if self.filters.to_date:
			conditions += " and posting_date <= %(to_date)s"

		if self.filters.group_by=="Sales Person":
			sales_person_cols = ", sales.sales_person, sales.allocated_amount, sales.incentives"
			sales_team_table = "left join `tabSales Team` sales on sales.parent = `tabSales Invoice`.name"
		else:
			sales_person_cols = ""
			sales_team_table = ""

		if self.filters.get("sales_invoice"):
			conditions += " and `tabSales Invoice`.name = %(sales_invoice)s"

		if self.filters.get("item_code"):
			conditions += " and `tabSales Invoice Item`.item_code = %(item_code)s"

		self.si_list = frappe.db.sql("""
			select
				`tabSales Invoice Item`.parenttype, `tabSales Invoice Item`.parent,
				`tabSales Invoice`.posting_date, `tabSales Invoice`.posting_time,
				`tabSales Invoice`.project, `tabSales Invoice`.update_stock,
				`tabSales Invoice`.customer, `tabSales Invoice`.customer_group,
				`tabSales Invoice`.territory, `tabSales Invoice Item`.item_code,
				`tabSales Invoice Item`.item_name, `tabSales Invoice Item`.description,
				`tabSales Invoice Item`.warehouse, `tabSales Invoice Item`.item_group,
				`tabSales Invoice Item`.brand, `tabSales Invoice Item`.dn_detail,
				`tabSales Invoice Item`.delivery_note, `tabSales Invoice Item`.stock_qty as qty,
				`tabSales Invoice Item`.base_net_rate, `tabSales Invoice Item`.base_net_amount,
				`tabSales Invoice Item`.name as "item_row", `tabSales Invoice`.is_return
				{sales_person_cols}
			from
				`tabSales Invoice` inner join `tabSales Invoice Item`
					on `tabSales Invoice Item`.parent = `tabSales Invoice`.name
				{sales_team_table}
			where
				`tabSales Invoice`.docstatus=1 and `tabSales Invoice`.is_opening!='Yes' {conditions} {match_cond}
			order by
				`tabSales Invoice`.posting_date desc, `tabSales Invoice`.posting_time desc"""
			.format(conditions=conditions, sales_person_cols=sales_person_cols,
				sales_team_table=sales_team_table, match_cond = get_match_cond('Sales Invoice')), self.filters, as_dict=1)

	def load_stock_ledger_entries(self):
		res = frappe.db.sql("""select item_code, voucher_type, voucher_no,
				voucher_detail_no, stock_value, warehouse, actual_qty as qty
			from `tabStock Ledger Entry`
			where company=%(company)s
			order by
				item_code desc, warehouse desc, posting_date desc,
				posting_time desc, creation desc""", self.filters, as_dict=True)
		self.sle = {}
		for r in res:
			if (r.item_code, r.warehouse) not in self.sle:
				self.sle[(r.item_code, r.warehouse)] = []

			self.sle[(r.item_code, r.warehouse)].append(r)

	def load_product_bundle(self):
		self.product_bundles = {}

		for d in frappe.db.sql("""select parenttype, parent, parent_item,
			item_code, warehouse, -1*qty as total_qty, parent_detail_docname
			from `tabPacked Item` where docstatus=1""", as_dict=True):
			self.product_bundles.setdefault(d.parenttype, frappe._dict()).setdefault(d.parent,
				frappe._dict()).setdefault(d.parent_item, []).append(d)

	def load_non_stock_items(self):
		self.non_stock_items = frappe.db.sql_list("""select name from tabItem
			where is_stock_item=0""")









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