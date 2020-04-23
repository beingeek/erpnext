from __future__ import unicode_literals
import frappe
from frappe import throw, _
import frappe.defaults
from frappe.utils import cint, flt, get_fullname, cstr, nowdate
from six import iteritems
from collections import OrderedDict
from erpnext.shopping_cart.cart import _get_cart_quotation, get_party
from erpnext.utilities.product import get_price


def get_context(context):
	stock_settings = frappe.get_single("Stock Settings")
	selling_settings = frappe.get_single("Selling Settings")
	cart_settings = frappe.get_single("Shopping Cart Settings")

	item_conditions = []

	item_groups_excluded = [d.item_group for d in stock_settings.price_list_excluded or []]
	if item_groups_excluded:
		item_conditions.append("item.item_group not in ('{}')".format("', '".join([frappe.db.escape(d) for d in item_groups_excluded])))

	item_groups_filter = []
	item_group_arg = frappe.form_dict.item_group
	if item_group_arg:
		lft_rgt = frappe.db.get_value("Item Group", item_group_arg, ['lft', 'rgt'])
		if lft_rgt:
			lft, rgt = lft_rgt
			item_groups_filter = frappe.db.sql_list("select name from `tabItem Group` where lft >= %s and rgt <= %s",
				[lft, rgt])

	if item_groups_filter:
		item_conditions.append("item.item_group in ('{}')".format("', '".join([frappe.db.escape(d) for d in item_groups_filter])))

	filters = frappe._dict({
		'today': nowdate()
	})

	item_data = frappe.db.sql("""
		select item.name as item_code, item.item_name, item.item_group, item.route,
			item.stock_uom, item.sales_uom, item.alt_uom, item.alt_uom_size,
			item.thumbnail, item.website_image, item.image,
			item.country_of_origin
		from tabItem item
		left join tabCountry c on c.name = item.country_of_origin
		where item.disabled != 1 and item.is_sales_item = 1 and item.show_in_website = 1 and item.print_in_price_list = 1
		and (ifnull(item.end_of_life, '0000-00-00') = '0000-00-00' or item.end_of_life > %(today)s) and {0}
	""".format(" and ".join(item_conditions)), filters, as_dict=1)

	item_map = {}
	for d in item_data:
		item_map[d.item_code] = d

	item_group_unsorted = OrderedDict()
	for d in item_data:
		item_group_unsorted.setdefault(d.item_group, []).append(d)

	item_group_sorted = OrderedDict()
	for item_group in [d.item_group for d in stock_settings.price_list_order or []]:
		if item_group in item_group_unsorted:
			items = item_group_unsorted[item_group]
			item_group_sorted.setdefault(item_group, [])
			item_group_sorted[item_group] = sorted(items, key=lambda d: d.item_name)
			del item_group_unsorted[item_group]

	for item_group, items in iteritems(item_group_unsorted):
		item_group_sorted[item_group] = sorted(items, key=lambda d: d.item_name)

	party = get_party() if frappe.session.user != "Guest" else frappe._dict()

	price_list = party.default_price_list or cart_settings.price_list or selling_settings.selling_price_list
	customer_group = party.customer_group or cart_settings.default_customer_group or selling_settings.customer_group
	set_item_prices(item_data, price_list, customer_group, cart_settings.company)

	if party:
		quotation = _get_cart_quotation(party)
		set_quotation_item_details(item_map, quotation)

	context.item_group_map = item_group_sorted

def set_quotation_item_details(item_map, quotation):
	for d in quotation.items:
		item = item_map.get(d.item_code)
		if item:
			item['qty'] = d.qty

def set_item_prices(item_data, price_list, customer_group, company):
	for d in item_data:
		price_obj = get_price(d.item_code, price_list, customer_group, company)
		if price_obj:
			d.update(price_obj)
