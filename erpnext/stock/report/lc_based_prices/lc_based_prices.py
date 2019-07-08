# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _, scrub
from frappe.utils import flt, nowdate, getdate, add_days, cint
from erpnext.stock.report.stock_ledger.stock_ledger import get_item_group_condition
from six import iteritems, string_types
import json


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.date = getdate(filters.date or nowdate())
	filters.from_date = filters.date
	filters.to_date = frappe.utils.add_days(filters.from_date, 4)
	filters.standard_price_list = frappe.db.get_single_value("Selling Settings", "base_price_list")

	stock_settings = frappe.get_single("Stock Settings")
	filters.item_groups_excluded = [d.item_group for d in stock_settings.price_list_excluded or []]

	data, price_lists = get_data(filters)
	columns = get_columns(filters, price_lists)

	item_group_wise_data = {}
	for d in data:
		item_group_wise_data.setdefault(d.item_group, []).append(d)

	res = []

	for item_group in stock_settings.price_list_order or []:
		if item_group.item_group in item_group_wise_data:
			res += sorted(item_group_wise_data[item_group.item_group], key=lambda d: d.item_code)
			del item_group_wise_data[item_group.item_group]

	for items in item_group_wise_data.values():
		res += sorted(items, key=lambda d: d.item_code)

	return columns, res


def get_data(filters):
	conditions = get_item_conditions(filters, use_doc_name=False)
	item_conditions = get_item_conditions(filters, use_doc_name=True)
	po_conditions = get_po_conditions(filters)

	price_lists, selected_price_list = get_price_lists(filters)
	price_lists_cond = " and p.price_list in ('{0}')".format("', '".join([frappe.db.escape(d) for d in price_lists]))

	item_data = frappe.db.sql("""
		select item.name as item_code, item.item_name, upper(c.code) as origin, item.weight_per_unit as weight,
			item.item_group, item.stock_uom, item.print_in_price_list
		from tabItem item
		left join tabCountry c on c.name = item.country_of_origin
		where disabled != 1 and is_sales_item = 1 {0}
	""".format(item_conditions), filters, as_dict=1)

	#price_list_item_data = frappe.db.sql("""
	#	select item_code from `tabPrice List Item` where parenttype = 'Price List' and parent = %s
	#""", selected_price_list or filters.standard_price_list)

	po_data = frappe.db.sql("""
		select
			item.item_code,
			sum(if(item.qty - item.received_qty < 0, 0, item.qty - item.received_qty)) as po_qty,
			sum(if(item.qty - item.received_qty < 0, 0, item.qty - item.received_qty) * item.landed_rate) as po_lc_amount
		from `tabPurchase Order Item` item
		inner join `tabPurchase Order` po on po.name = item.parent
		where item.docstatus < 2 and po.status != 'Closed' {0} {1}
		group by item.item_code
	""".format(conditions, po_conditions), filters, as_dict=1)

	bin_data = frappe.db.sql("""
		select
			bin.item_code,
			sum(bin.actual_qty) as actual_qty,
			sum(bin.stock_value) as stock_value
		from tabBin bin, tabItem item
		where item.name = bin.item_code {0}
		group by bin.item_code
	""".format(item_conditions), filters, as_dict=1)

	item_price_data = frappe.db.sql("""
		select p.name, p.price_list, p.item_code, p.price_list_rate, ifnull(p.valid_from, '2000-01-01') as valid_from
		from `tabItem Price` p
		inner join `tabItem` item on item.name = p.item_code
		where %(date)s between ifnull(p.valid_from, '2000-01-01') and ifnull(p.valid_upto, '2500-12-31')
			{0} {1}
	""".format(item_conditions, price_lists_cond), filters, as_dict=1)

	previous_item_prices = frappe.db.sql("""
		select p.price_list, p.item_code, p.price_list_rate, ifnull(p.valid_from, '2000-01-01') as valid_from
		from `tabItem Price` as p
		inner join `tabItem` item on item.name = p.item_code
		where ifnull(p.valid_from, '2000-01-01') < %(date)s {0} {1}
		order by ifnull(p.valid_from, '2000-01-01') desc
	""".format(item_conditions, price_lists_cond), filters, as_dict=1)

	items_map = {}
	for d in item_data:
		items_map[d.item_code] = d

	#for d in price_list_item_data:
	#	if d.item_code in items_map:
	#		items_map[d.item_code].in_price_list_item = 1

	for d in po_data:
		if d.item_code in items_map:
			items_map[d.item_code].update(d)

	for d in bin_data:
		if d.item_code in items_map:
			items_map[d.item_code].update(d)

	item_price_map = {}
	for d in item_price_data:
		if d.item_code in items_map:
			if d.price_list == filters.standard_price_list:
				items_map[d.item_code].standard_rate = d.price_list_rate

			price = item_price_map.setdefault(d.item_code, {}).setdefault(d.price_list, frappe._dict())
			price.current_price = d.price_list_rate
			price.valid_from = d.valid_from
			price.item_price = d.name

	for d in previous_item_prices:
		if d.item_code in item_price_map and d.price_list in item_price_map[d.item_code]:
			price = item_price_map[d.item_code][d.price_list]
			if 'previous_price' not in price and d.valid_from < price.valid_from:
				price.previous_price = d.price_list_rate

	for item_code, d in iteritems(items_map):
		d.actual_qty = flt(d.actual_qty)
		d.po_qty = flt(d.po_qty)

		d.po_lc_rate = flt(d.po_lc_amount) / d.po_qty if d.po_qty else 0
		d.valuation_rate = flt(d.stock_value) / d.actual_qty if d.actual_qty else 0

		d.balance_qty = d.actual_qty + d.po_qty
		d.avg_lc_rate = (flt(d.stock_value) + flt(d.po_lc_amount)) / d.balance_qty if d.balance_qty else 0
		d.margin_rate = (d.standard_rate - d.avg_lc_rate) * 100 / d.standard_rate if d.standard_rate else None

		for price_list, price in iteritems(item_price_map.get(item_code, {})):
			d["rate_" + scrub(price_list)] = price.current_price
			if d.standard_rate is not None:
				d["rate_diff_" + scrub(price_list)] = flt(price.current_price) - flt(d.standard_rate)
			if price.previous_price is not None:
				d["rate_old_" + scrub(price_list)] = price.previous_price
			if price.item_price:
				d["item_price_" + scrub(price_list)] = price.item_price

		d['print_rate'] = d.get("rate_" + scrub(selected_price_list)) if selected_price_list else d.standard_rate

	if filters.filter_items_without_price:
		to_remove = []
		for item_code, d in iteritems(items_map):
			if not d.get('print_rate'):
				to_remove.append(item_code)
		for item_code in to_remove:
			del items_map[item_code]

	return items_map.values(), price_lists


def get_price_lists(filters):
	def get_additional_price_lists():
		res = []
		for i in range(3):
			if filters.get('price_list_' + str(i+1)):
				res.append(filters.get('price_list_' + str(i+1)))
		return res

	if filters.filter_price_list_by == "All Price Lists":
		price_list_filter_cond = ""
	elif filters.filter_price_list_by == "Disabled":
		price_list_filter_cond = " and enabled = 0"
	else:
		price_list_filter_cond = " and enabled = 1"

	price_lists = [filters.standard_price_list]

	if filters.customer:
		filters.selected_price_list = frappe.db.get_value("Customer", filters.customer, 'default_price_list')

	if filters.selected_price_list:
		price_lists.append(filters.selected_price_list)

	additional_price_lists = get_additional_price_lists()
	if additional_price_lists:
		price_lists += additional_price_lists

	if not additional_price_lists and not filters.selected_price_list:
		price_lists += frappe.db.sql_list("select name from `tabPrice List` where selling = 1 {0}".format(price_list_filter_cond))

	return price_lists, filters.selected_price_list


def get_item_conditions(filters, use_doc_name):
	conditions = []

	if filters.get("item_code"):
		conditions.append("item.{} = %(item_code)s".format("name" if use_doc_name else "item_code"))
	else:
		if filters.get("brand"):
			conditions.append("item.brand=%(brand)s")
		if filters.get("item_group"):
			conditions.append(get_item_group_condition(filters.get("item_group")))

	if filters.get("item_groups_excluded"):
		conditions.append("item.item_group not in ('{}')".format("', '".join([frappe.db.escape(d) for d in filters.get("item_groups_excluded")])))

	return " and " + " and ".join(conditions) if conditions else ""


def get_po_conditions(filters):
	po_conditions = []
	if filters.get('po_from_date'):
		po_conditions.append("po.schedule_date >= %(po_from_date)s")
	if filters.get('po_to_date'):
		po_conditions.append("po.schedule_date <= %(po_to_date)s")
	return "and {0}".format(" and ".join(po_conditions)) if po_conditions else ""


def get_columns(filters, price_lists):
	columns = [
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 80},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "print_in_price_list", "label": _("Print"), "fieldtype": "Check", "width": 50, "editable": True},
		# {"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"fieldname": "po_qty", "label": _("PO Qty"), "fieldtype": "Float", "width": 70, "restricted": True},
		{"fieldname": "po_lc_rate", "label": _("PO LC"), "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 70, "restricted": True},
		{"fieldname": "actual_qty", "label": _("Stock Qty"), "fieldtype": "Float", "width": 80, "restricted": True},
		{"fieldname": "valuation_rate", "label": _("Stock LC"), "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 70, "restricted": True},
		{"fieldname": "avg_lc_rate", "label": _("Avg LC"), "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 70, "restricted": True},
		{"fieldname": "standard_rate", "label": _("Base Price"), "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 80,
			"editable": True, "price_list": filters.standard_price_list, "is_base_price": True},
		{"fieldname": "margin_rate", "label": _("% Margin"), "fieldtype": "Percent", "width": 80, "restricted": True},
	]

	for price_list in sorted(price_lists):
		if price_list != filters.standard_price_list:
			columns.append({
				"fieldname": "rate_diff_" + scrub(price_list),
				"label": "+/-",
				"fieldtype": "Currency",
				"options": "Company:company:default_currency",
				"width": 40,
				"editable": True,
				"price_list": price_list,
				"is_diff": True,
				"restricted": True
			})
			columns.append({
				"fieldname": "rate_" + scrub(price_list),
				"label": price_list,
				"fieldtype": "Currency",
				"options": "Company:company:default_currency",
				"width": 70,
				"editable": True,
				"price_list": price_list,
			})

	show_amounts_role = frappe.db.get_single_value("Stock Settings", "restrict_amounts_in_report_to_role")
	show_amounts = show_amounts_role and show_amounts_role in frappe.get_roles()
	if not show_amounts:
		columns = filter(lambda d: not d.get('restricted'), columns)
		for c in columns:
			if c.get('editable'):
				del c['editable']

	return columns

@frappe.whitelist()
def set_item_pl_rate(effective_date, item_code, price_list, price_list_rate, is_diff=False, filters={}):
	effective_date = frappe.utils.getdate(effective_date)
	standard_price_list = frappe.db.get_single_value("Selling Settings", "base_price_list")

	old_standard_rate = frappe.db.sql_list("""
		select price_list_rate
		from `tabItem Price`
		where price_list = %s and item_code = %s
			and %s between ifnull(valid_from, '2000-01-01') and ifnull(valid_upto, '2500-12-31')
		order by datediff(%s, valid_from)
		limit 1
	""", [standard_price_list, item_code, effective_date, effective_date])

	if cint(is_diff):
		if not old_standard_rate:
			frappe.throw(_("Could not find Base Price for item {0}").format(item_code))
		else:
			price_list_rate = flt(old_standard_rate[0]) + flt(price_list_rate)

	dependent_item_prices = []
	if price_list == standard_price_list and old_standard_rate:
		dependent_item_prices = frappe.db.sql("""
			select p.price_list, p.price_list_rate - %s as diff
			from `tabItem Price` p
			inner join `tabPrice List` pl on pl.name = p.price_list and pl.enabled = 1 and pl.selling = 1
			where p.item_code = %s and p.price_list != %s and pl.prices_independent_of_base_price != 1
				and %s between ifnull(valid_from, '2000-01-01') and ifnull(valid_upto, '2500-12-31')
		""", [old_standard_rate[0], item_code, price_list, effective_date], as_dict=1)

	_set_item_pl_rate(effective_date, item_code, price_list, price_list_rate)

	dependent_price_list_visited = set()
	for d in dependent_item_prices:
		if d.price_list not in dependent_price_list_visited:
			dependent_price_list_visited.add(d.price_list)
			_set_item_pl_rate(effective_date, item_code, d.price_list, flt(price_list_rate) + flt(d.diff))

	if isinstance(filters, string_types):
		filters = json.loads(filters)
	filters['item_code'] = item_code
	return execute(filters)


def _set_item_pl_rate(effective_date, item_code, price_list, price_list_rate):
	from frappe.model.utils import get_fetch_values

	item_prices = frappe.db.sql("""
		select name, valid_from, valid_upto
		from `tabItem Price`
		where selling = 1 and item_code = %s and price_list = %s
		order by valid_from
	""", [item_code, price_list], as_dict=1)

	existing_item_price = filter(lambda d: d.valid_from == effective_date, item_prices)
	existing_item_price = existing_item_price[0] if existing_item_price else None
	past_item_price = filter(lambda d: not d.valid_from or d.valid_from < effective_date, item_prices)
	past_item_price = past_item_price[-1] if past_item_price else None
	future_item_price = filter(lambda d: d.valid_from and d.valid_from > effective_date, item_prices)
	future_item_price = future_item_price[0] if future_item_price else None

	# Update or add item price
	if existing_item_price:
		doc = frappe.get_doc("Item Price", existing_item_price.name)
	else:
		doc = frappe.new_doc("Item Price")
		doc.item_code = item_code
		doc.price_list = price_list
		doc.update(get_fetch_values("Item Price", 'item_code', item_code))
		doc.update(get_fetch_values("Item Price", 'price_list', price_list))

	doc.price_list_rate = flt(price_list_rate)
	doc.valid_from = effective_date
	if future_item_price:
		doc.valid_upto = frappe.utils.add_days(future_item_price.valid_from, -1)
	doc.save()

	# Update previous item price
	before_effective_date = frappe.utils.add_days(effective_date, -1)
	if past_item_price and past_item_price.valid_upto != before_effective_date:
		frappe.set_value("Item Price", past_item_price.name, 'valid_upto', before_effective_date)
