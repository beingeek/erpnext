from __future__ import unicode_literals

import frappe
from frappe import throw, _
import frappe.defaults
from frappe.utils import nowdate
from six import iteritems
from collections import OrderedDict
from erpnext.shopping_cart.cart import _get_cart_quotation, get_party
from erpnext.utilities.product import get_price
from erpnext.stock.doctype.item.item import convert_item_uom_for


def get_context(context):
	context.no_cache = True
	context.parents = [{'title': _('Products'), 'route': 'product-list'}]

	if frappe.session.user == "Guest":
		raise frappe.PermissionError, "Please login first"

	item_group = frappe.form_dict.item_group

	if not item_group:
		frappe.local.flags.redirect_location = "/products"
		raise frappe.Redirect

	if not frappe.db.get_value("Item Group", item_group, 'show_in_website'):
		context.title = _("Invalid Item Group")
		raise frappe.DoesNotExistError

	context.title = item_group

	stock_settings = frappe.get_single("Stock Settings")
	selling_settings = frappe.get_single("Selling Settings")
	cart_settings = frappe.get_single("Shopping Cart Settings")

	item_data = get_items(stock_settings, item_group=item_group)
	item_group_map = group_by_item_group(item_data, stock_settings)
	item_code_map = group_by_item_code(item_data)

	party = get_party() if frappe.session.user != "Guest" else frappe._dict()

	price_list = determine_price_list(party, cart_settings, selling_settings)
	customer_group = determine_customer_group(party, cart_settings, selling_settings)

	if party:
		quotation = _get_cart_quotation(party)
		set_quotation_item_details(item_code_map, quotation)

	set_item_prices(item_data, price_list, customer_group, cart_settings.company)
	set_uom_details(item_data)

	context.item_group_map = item_group_map


def get_items(stock_settings, item_group=None, item_code=None, uom=None):
	conditions = []
	filters = frappe._dict({
		'today': nowdate()
	})

	if item_code:
		conditions.append("item.name = %(item_code)s")
		filters['item_code'] = item_code
	else:
		# standard list filters
		conditions.append("item.print_in_price_list = 1")

		# excluded item groups
		excluded_item_groups = [d.item_group for d in stock_settings.price_list_excluded or []]
		if excluded_item_groups:
			conditions.append("item.item_group not in %(excluded_item_groups)s")
			filters['excluded_item_groups'] = excluded_item_groups

		# filtered item groups
		filtered_item_groups = []
		if item_group:
			lft_rgt = frappe.db.get_value("Item Group", item_group, ['lft', 'rgt'])
			if lft_rgt:
				lft, rgt = lft_rgt
				filtered_item_groups = frappe.db.sql_list("select name from `tabItem Group` where lft >= %s and rgt <= %s",
					[lft, rgt])

		if filtered_item_groups:
			conditions.append("item.item_group in %(filtered_item_groups)s")
			filters['filtered_item_groups'] = filtered_item_groups

	item_data =  frappe.db.sql("""
		select item.name as item_code, item.item_name, item.item_group, item.route,
			item.stock_uom, item.sales_uom, item.alt_uom, item.alt_uom_size,
			item.thumbnail, item.website_image, item.image,
			upper(c.code) as country_code
		from tabItem item
		left join `tabCountry` c on c.name = item.country_of_origin
		where item.disabled = 0 and item.is_sales_item = 1 and item.show_in_website = 1
		and (ifnull(item.end_of_life, '0000-00-00') = '0000-00-00' or item.end_of_life > %(today)s) and {0}
	""".format(" and ".join(conditions)), filters, as_dict=1)

	if item_data and item_code and uom:
		item_data[0].selected_uom = uom

	return item_data


def group_by_item_code(item_data):
	item_code_map = {}
	for d in item_data:
		item_code_map[d.item_code] = d

	return item_code_map


def group_by_item_group(item_data, stock_settings):
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

	return item_group_sorted


def determine_price_list(party, cart_settings, selling_settings):
	return party.default_price_list or cart_settings.price_list or selling_settings.selling_price_list
	

def determine_customer_group(party, cart_settings, selling_settings):
	return party.customer_group or cart_settings.default_customer_group or selling_settings.customer_group


def set_quotation_item_details(item_map, quotation):
	for d in quotation.items:
		item = item_map.get(d.item_code)
		if item:
			item['in_cart'] = 1
			item['qty'] = d.qty
			item['selected_uom'] = d.uom
			item['alt_uom_size'] = d.alt_uom_size


def set_uom_details(item_data):
	for d in item_data:
		d['selected_uom'] = d.get('selected_uom') or d.sales_uom or d.stock_uom
		item = frappe.get_cached_doc("Item", d.item_code)
		if item:
			d['uoms'] = item.uoms

		if not d.get('in_cart'):
			d['alt_uom_size'] = convert_item_uom_for(d.alt_uom_size, d.item_code, d.stock_uom, d.selected_uom)


def set_item_prices(item_data, price_list, customer_group, company):
	for d in item_data:
		price_obj = get_price(d.item_code, price_list, customer_group, company,
			qty=d.get('qty') or 1, uom=d.get('selected_uom') or d.sales_uom or d.stock_uom)
		if price_obj:
			d.update(price_obj)

@frappe.whitelist()
def change_product_uom(item_code, uom):
	stock_settings = frappe.get_single("Stock Settings")
	selling_settings = frappe.get_single("Selling Settings")
	cart_settings = frappe.get_single("Shopping Cart Settings")

	item_data = get_items(stock_settings, item_code=item_code, uom=uom)
	item_code_map = group_by_item_code(item_data)
	
	party = get_party() if frappe.session.user != "Guest" else frappe._dict()

	price_list = determine_price_list(party, cart_settings, selling_settings)
	customer_group = determine_customer_group(party, cart_settings, selling_settings)

	if party:
		quotation = _get_cart_quotation(party)
		set_quotation_item_details(item_code_map, quotation)

	set_item_prices(item_data, price_list, customer_group, cart_settings.company)
	set_uom_details(item_data)

	context = {}
	context['item'] = item_data[0]
	return {
		"item": frappe.render_template("erpnext/www/product-list-row.html", context)
	}