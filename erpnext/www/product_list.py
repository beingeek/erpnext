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
	
	item_groups_excluded = [d.item_group for d in stock_settings.price_list_excluded or []]

	item_conditions = []
	if item_groups_excluded:
		item_conditions.append("item.item_group not in ('{}')".format("', '".join([frappe.db.escape(d) for d in item_groups_excluded])))

	filters = {
		'today': nowdate()
	}

	item_data = frappe.db.sql("""
		select item.name as item_code, item.item_name, upper(c.code) as origin, item.item_group, item.print_in_price_list,
			item.stock_uom, item.sales_uom, item.alt_uom, item.alt_uom_size, item.thumbnail, item.website_image, item.image, item.valuation_rate
		from tabItem item
		left join tabCountry c on c.name = item.country_of_origin
		where item.disabled != 1 and item.is_sales_item = 1 and item.show_in_website = 1
		and (ifnull(item.end_of_life, '0000-00-00') = '0000-00-00' or item.end_of_life > %(today)s) and {0}
	""".format(" and ".join(item_conditions)), filters, as_dict=1)

	item_group_unsorted = OrderedDict()
	for d in item_data:
		item_group_unsorted.setdefault(d.item_group, []).append(d)

	item_group_sorted = OrderedDict()
	for item_group_order in stock_settings.price_list_order or []:
		if item_group_order.item_group in item_group_unsorted:
			item_group_sorted.setdefault(item_group_order.item_group, [])
			item_group_sorted[item_group_order.item_group] = sorted(item_group_unsorted[item_group_order.item_group], key=lambda d: d.item_name)
			del item_group_unsorted[item_group_order.item_group]

	for items in item_group_unsorted.values():
		item_group_sorted[item_group_order.item_group] = sorted(items, key=lambda d: d.item_name)

	party = get_party()
	quotation = _get_cart_quotation(party)

	price_list = party.default_price_list or cart_settings.price_list or selling_settings.selling_price_list
	customer_group = party.customer_group or cart_settings.default_customer_group or selling_settings.customer_group

	set_quotation_item_details(item_group_sorted, quotation)
	set_item_prices(item_data, price_list, customer_group, cart_settings.company)

	context.item_group_map = item_group_sorted

def set_quotation_item_details(item_group_sorted, quotation):
	for item in quotation.items:
		for sort_item in item_group_sorted.get(item.item_group):
			if item.item_code == sort_item.get('item_code'):
				sort_item.update({'qty':item.qty})

def set_item_prices(item_data, price_list, customer_group, company):
	for d in item_data:
		price_obj = get_price(d.item_code, price_list, customer_group, company)
		if price_obj:
			d.update(price_obj)