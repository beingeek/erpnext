# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import throw, _
import frappe.defaults
from frappe.utils import cint, flt, get_fullname, cstr, today
from frappe.contacts.doctype.address.address import get_address_display
from erpnext.shopping_cart.doctype.shopping_cart_settings.shopping_cart_settings import get_shopping_cart_settings
from frappe.utils.nestedset import get_root_of
from erpnext.accounts.utils import get_account_name
from erpnext.utilities.product import get_qty_in_stock
from erpnext.accounts.utils import get_balance_on


class WebsitePriceListMissingError(frappe.ValidationError):
	pass

cart_quotation_fields = ['delivery_date']
cart_party_fields = ['customer_name','credit_limit']

def set_cart_count(quotation=None):
	if cint(frappe.db.get_singles_value("Shopping Cart Settings", "enabled")):
		if not quotation:
			quotation = _get_cart_quotation()
		cart_count = cstr(len(quotation.get("items")))

		if hasattr(frappe.local, "cookie_manager"):
			frappe.local.cookie_manager.set_cookie("cart_count", cart_count)

@frappe.whitelist()
def get_cart_quotation(doc=None):
	party = get_party()

	if not doc:
		quotation = _get_cart_quotation(party)
		doc = quotation
		set_cart_count(quotation)

	if hasattr(doc, "set_indicator"):
		doc.set_indicator()

	addresses = get_address_docs(party=party)

	get_balance = get_balance_on(party=party.name, party_type='Customer')

	if not doc.customer_address and addresses:
		update_cart_address("customer_address", addresses[0].name)

	return {
		"customer_balance": get_balance,
		"doc": decorate_quotation_doc(doc),
		"party": party,
		"shipping_addresses": [{"name": address.name, "display": address.display}
			for address in addresses],
		"billing_addresses": [{"name": address.name, "display": address.display}
			for address in addresses],
		"shipping_rules": get_applicable_shipping_rules(party),
		"quotation_fields": cart_quotation_fields,
		"party_fields": cart_party_fields,
		"default_item_groups_allow": default_item_groups_allow()
	}

@frappe.whitelist()
def place_order(confirmed):
	quotation = _get_cart_quotation()
	quotation.company = frappe.db.get_value("Shopping Cart Settings", None, "company")
	if not quotation.get("customer_address"):
		throw(_("{0} is required").format(_(quotation.meta.get_label("customer_address"))))
	if cint(confirmed):
		quotation.confirmed_by_customer = 1
	else:
		quotation.confirmed_by_customer = 0

	quotation.transaction_date = today()
	quotation.flags.ignore_permissions = True
	quotation.save()

	if quotation.lead:
		# company used to create customer accounts
		frappe.defaults.set_user_default("company", quotation.company)

	if hasattr(frappe.local, "cookie_manager"):
		frappe.local.cookie_manager.delete_cookie("cart_count")

	return quotation.name

@frappe.whitelist()
def update_cart_item(item_code, fieldname, value, with_items=False):
	from erpnext.stock.get_item_details import get_conversion_factor
	quotation = _get_cart_quotation()
	if fieldname not in ['qty', 'uom']:
		frappe.throw(_("Invalid Fieldname"))

	if fieldname == 'qty' and not flt(value):
		quotation_items = quotation.get("items", {"item_code": ["!=", item_code]})
		for i, d in enumerate(quotation_items):
			d.idx = i + 1
		quotation.set("items", quotation_items)
	else:
		quotation_items = quotation.get("items", {"item_code": item_code})
		if not quotation_items:
			quotation.append("items", {
				"item_code": item_code,
				fieldname: value
			})
		else:
			quotation_items[0].set(fieldname, value)
			if fieldname == 'uom':
				quotation_items[0].conversion_factor = get_conversion_factor(item_code, value).get('conversion_factor')

	return update_cart(quotation, with_items)
	

@frappe.whitelist()
def update_cart_field(fieldname, value, with_items=False):
	if fieldname not in cart_quotation_fields:
		frappe.throw(_("Invalid Fieldname {0}").format(fieldname))

	quotation = _get_cart_quotation()
	quotation.set(fieldname, value)
	return update_cart(quotation, with_items)

def update_cart(quotation, with_items=False):
	apply_cart_settings(quotation=quotation)
	quotation.flags.ignore_permissions = True
	quotation.flags.ignore_mandatory = True
	quotation.payment_schedule = []
	quotation.save()

	set_cart_count(quotation)

	context = get_cart_quotation(quotation)
	qtn_fields_dict = {}
	for f in cart_quotation_fields:
		qtn_fields_dict[f] = context['doc'].get(f)
	for f in cart_party_fields:
		qtn_fields_dict[f] = context['party'].get(f)

	
	if cint(with_items):
		return {
			"items": frappe.render_template("templates/includes/cart/cart_items.html",
				context),
			"taxes": frappe.render_template("templates/includes/order/order_taxes.html",
				context),
			"quotation_fields": qtn_fields_dict,
			"name": quotation.name
		}
	else:
		return {
			'name': quotation.name,
			'shopping_cart_menu': get_shopping_cart_menu(context)
		}

@frappe.whitelist()
def get_shopping_cart_menu(context=None):
	if not context:
		context = get_cart_quotation()

	return frappe.render_template('templates/includes/cart/cart_dropdown.html', context)

@frappe.whitelist()
def update_cart_address(address_fieldname, address_name):
	quotation = _get_cart_quotation()
	address_display = get_address_display(frappe.get_doc("Address", address_name).as_dict())

	if address_fieldname == "shipping_address_name":
		quotation.shipping_address_name = address_name
		quotation.shipping_address = address_display

		if not quotation.customer_address:
			address_fieldname = "customer_address"

	if address_fieldname == "customer_address":
		quotation.customer_address = address_name
		quotation.address_display = address_display


	apply_cart_settings(quotation=quotation)

	quotation.flags.ignore_permissions = True
	quotation.flags.ignore_mandatory = True
	quotation.save()

	context = get_cart_quotation(quotation)
	return {
		"taxes": frappe.render_template("templates/includes/order/order_taxes.html",
			context),
		"name": quotation.name
		}

def guess_territory():
	territory = None
	geoip_country = frappe.session.get("session_country")
	if geoip_country:
		territory = frappe.db.get_value("Territory", geoip_country)

	return territory or \
		frappe.db.get_value("Shopping Cart Settings", None, "territory") or \
			get_root_of("Territory")

def decorate_quotation_doc(doc):
	for d in doc.get("items", []):
		d.update(frappe.db.get_value("Item", d.item_code,
			["thumbnail", "website_image", "description", "route"], as_dict=True))

	return doc


def _get_cart_quotation(party=None):
	'''Return the open Quotation of type "Shopping Cart" or make a new one'''
	if not party:
		party = get_party()

	quotation = frappe.get_all("Quotation", fields=["name"], filters=
		{party.doctype.lower(): party.name, "order_type": "Shopping Cart", "docstatus": 0},
		order_by="modified desc", limit_page_length=1)

	if quotation:
		qdoc = frappe.get_doc("Quotation", quotation[0].name)
	else:
		qdoc = frappe.get_doc({
			"doctype": "Quotation",
			"naming_series": get_shopping_cart_settings().quotation_series or "QTN-CART-",
			"quotation_to": party.doctype,
			"company": frappe.db.get_value("Shopping Cart Settings", None, "company"),
			"order_type": "Shopping Cart",
			"status": "Draft",
			"docstatus": 0,
			"__islocal": 1,
			(party.doctype.lower()): party.name
		})

		qdoc.contact_person = frappe.db.get_value("Contact", {"email_id": frappe.session.user})
		qdoc.contact_email = frappe.session.user

		qdoc.flags.ignore_permissions = True
		qdoc.run_method("set_missing_values")
		apply_cart_settings(party, qdoc)

	return qdoc

def update_party(fullname, company_name=None, mobile_no=None, phone=None):
	party = get_party()

	party.customer_name = company_name or fullname
	party.customer_type == "Company" if company_name else "Individual"

	contact_name = frappe.db.get_value("Contact", {"email_id": frappe.session.user})
	contact = frappe.get_doc("Contact", contact_name)
	contact.first_name = fullname
	contact.last_name = None
	contact.customer_name = party.customer_name
	contact.mobile_no = mobile_no
	contact.phone = phone
	contact.flags.ignore_permissions = True
	contact.save()

	party_doc = frappe.get_doc(party.as_dict())
	party_doc.flags.ignore_permissions = True
	party_doc.save()

	qdoc = _get_cart_quotation(party)
	if not qdoc.get("__islocal"):
		qdoc.customer_name = company_name or fullname
		qdoc.run_method("set_missing_lead_customer_details")
		qdoc.flags.ignore_permissions = True
		qdoc.save()

def apply_cart_settings(party=None, quotation=None):
	if not party:
		party = get_party()
	if not quotation:
		quotation = _get_cart_quotation(party)

	cart_settings = frappe.get_doc("Shopping Cart Settings")

	set_price_list_and_rate(quotation, cart_settings)

	quotation.run_method("calculate_taxes_and_totals")

	set_taxes(quotation, cart_settings)

	_apply_shipping_rule(party, quotation, cart_settings)

def set_price_list_and_rate(quotation, cart_settings):
	"""set price list based on billing territory"""

	_set_price_list(quotation, cart_settings)

	# reset values
	quotation.price_list_currency = quotation.currency = \
		quotation.plc_conversion_rate = quotation.conversion_rate = None
	for item in quotation.get("items"):
		item.price_list_rate = item.discount_percentage = item.rate = item.amount = None

	# refetch values
	quotation.run_method("set_price_list_and_item_details")

	if hasattr(frappe.local, "cookie_manager"):
		# set it in cookies for using in product page
		frappe.local.cookie_manager.set_cookie("selling_price_list", quotation.selling_price_list)

def _set_price_list(quotation, cart_settings):
	"""Set price list based on customer or shopping cart default"""
	if quotation.selling_price_list:
		return

	# check if customer price list exists
	selling_price_list = None
	if quotation.customer:
		from erpnext.accounts.party import get_default_price_list
		selling_price_list = get_default_price_list(frappe.get_doc("Customer", quotation.customer))

	# else check for territory based price list
	if not selling_price_list:
		selling_price_list = cart_settings.price_list

	quotation.selling_price_list = selling_price_list

def set_taxes(quotation, cart_settings):
	"""set taxes based on billing territory"""
	from erpnext.accounts.party import set_taxes

	customer_group = frappe.db.get_value("Customer", quotation.customer, "customer_group")

	quotation.taxes_and_charges = set_taxes(quotation.customer, "Customer",
		quotation.transaction_date, quotation.company, customer_group=customer_group, supplier_group=None,
		tax_category=quotation.tax_category, billing_address=quotation.customer_address,
		shipping_address=quotation.shipping_address_name, use_for_shopping_cart=1)
#
# 	# clear table
	quotation.set("taxes", [])
#
# 	# append taxes
	quotation.append_taxes_from_master()

def get_party(user=None):
	if not user:
		user = frappe.session.user

	contact_name = get_contact_name(user)
	party_doctype = party = None

	if contact_name:
		contact = frappe.get_doc('Contact', contact_name)
		if contact.links:
			party_doctype = contact.links[0].link_doctype
			party = contact.links[0].link_name

	cart_settings = frappe.get_doc("Shopping Cart Settings")

	debtors_account = ''

	if cart_settings.enable_checkout:
		debtors_account = get_debtors_account(cart_settings)

	if party:
		return frappe.get_doc(party_doctype, party)

	else:
		if not cart_settings.enabled:
			frappe.local.flags.redirect_location = "/contact"
			raise frappe.Redirect
		customer = frappe.new_doc("Customer")
		fullname = get_fullname(user)
		customer.update({
			"customer_name": fullname,
			"customer_type": "Individual",
			"customer_group": get_shopping_cart_settings().default_customer_group,
			"territory": get_root_of("Territory")
		})

		if debtors_account:
			customer.update({
				"accounts": [{
					"company": cart_settings.company,
					"account": debtors_account
				}]
			})

		customer.flags.ignore_mandatory = True
		customer.insert(ignore_permissions=True)

		contact = frappe.new_doc("Contact")
		contact.update({
			"first_name": fullname,
			"email_id": user,
			"user": user
		})
		contact.append('links', dict(link_doctype='Customer', link_name=customer.name))
		contact.flags.ignore_mandatory = True
		contact.insert(ignore_permissions=True)

		return customer

def get_contact_name(user):
	contacts = frappe.db.sql_list("""
		select c.name
		from `tabContact` c
		where (c.user = %(user)s or c.email_id = %(user)s) and exists(select l.name from `tabDynamic Link` l
			where l.parent=c.name and l.parenttype='Contact' and l.link_doctype = 'Customer' and ifnull(l.link_name, '') != '')
	""", {"user": user})

	return contacts[0] if contacts else None

def get_debtors_account(cart_settings):
	payment_gateway_account_currency = \
		frappe.get_doc("Payment Gateway Account", cart_settings.payment_gateway_account).currency

	account_name = _("Debtors ({0})".format(payment_gateway_account_currency))

	debtors_account_name = get_account_name("Receivable", "Asset", is_group=0,\
		account_currency=payment_gateway_account_currency, company=cart_settings.company)

	if not debtors_account_name:
		debtors_account = frappe.get_doc({
			"doctype": "Account",
			"account_type": "Receivable",
			"root_type": "Asset",
			"is_group": 0,
			"parent_account": get_account_name(root_type="Asset", is_group=1, company=cart_settings.company),
			"account_name": account_name,
			"currency": payment_gateway_account_currency
		}).insert(ignore_permissions=True)

		return debtors_account.name

	else:
		return debtors_account_name


def get_address_docs(doctype=None, txt=None, filters=None, limit_start=0, limit_page_length=20,
	party=None):
	if not party:
		party = get_party()

	if not party:
		return []

	address_names = frappe.db.get_all('Dynamic Link', fields=('parent'),
		filters=dict(parenttype='Address', link_doctype=party.doctype, link_name=party.name))

	out = []

	for a in address_names:
		address = frappe.get_doc('Address', a.parent)
		address.display = get_address_display(address.as_dict())
		out.append(address)

	return out

@frappe.whitelist()
def apply_shipping_rule(shipping_rule):
	quotation = _get_cart_quotation()

	quotation.shipping_rule = shipping_rule

	apply_cart_settings(quotation=quotation)

	quotation.flags.ignore_permissions = True
	quotation.flags.ignore_mandatory = True
	quotation.save()

	return get_cart_quotation(quotation)

def _apply_shipping_rule(party=None, quotation=None, cart_settings=None):
	if not quotation.shipping_rule:
		shipping_rules = get_shipping_rules(quotation, cart_settings)

		if not shipping_rules:
			return

		elif quotation.shipping_rule not in shipping_rules:
			quotation.shipping_rule = shipping_rules[0]

	if quotation.shipping_rule:
		quotation.run_method("apply_shipping_rule")
		quotation.run_method("calculate_taxes_and_totals")

def get_applicable_shipping_rules(party=None, quotation=None):
	shipping_rules = get_shipping_rules(quotation)

	if shipping_rules:
		rule_label_map = frappe.db.get_values("Shipping Rule", shipping_rules, "label")
		# we need this in sorted order as per the position of the rule in the settings page
		return [[rule, rule_label_map.get(rule)] for rule in shipping_rules]

def get_shipping_rules(quotation=None, cart_settings=None):
	if not quotation:
		quotation = _get_cart_quotation()

	shipping_rules = []
	if quotation.shipping_address_name:
		country = frappe.db.get_value("Address", quotation.shipping_address_name, "country")
		if country:
			shipping_rules = frappe.db.sql_list("""select distinct sr.name
				from `tabShipping Rule Country` src, `tabShipping Rule` sr
				where src.country = %s and
				sr.disabled != 1 and sr.name = src.parent""", country)

	return shipping_rules

def get_address_territory(address_name):
	"""Tries to match city, state and country of address to existing territory"""
	territory = None

	if address_name:
		address_fields = frappe.db.get_value("Address", address_name,
			["city", "state", "country"])
		for value in address_fields:
			territory = frappe.db.get_value("Territory", value)
			if territory:
				break

	return territory

def show_terms(doc):
	return doc.tc_name

@frappe.whitelist()
def get_default_items(with_items=False, item_group=None):
	quotation = _get_cart_quotation()
	default_items = frappe.get_all("Customer Default Item", fields=['item_code'],
		filters={"parenttype": 'Customer', "parent": quotation.customer})

	if item_group:
		lft, rgt = frappe.get_cached_value("Item Group", item_group, ['lft', 'rgt'])
		if lft and rgt:
			item_groups = frappe.db.sql_list("select name from `tabItem Group` where lft >= %(lft)s and rgt <= %(rgt)s",
			{'lft':lft,'rgt':rgt})

			filtered_default_items = []
			for d in default_items:
				item_group_default_item = frappe.get_cached_value("Item", d.item_code, "item_group")
				if item_group_default_item in item_groups:
					filtered_default_items.append(d)

			default_items = filtered_default_items

	default_item_codes = [d.item_code for d in default_items]
	existing_item_codes = [d.item_code for d in quotation.items]

	for item_code in default_item_codes:
		if item_code not in existing_item_codes:
			quotation.append("items", {"item_code": item_code, "qty": 1})
	
	return update_cart(quotation, with_items)

def default_item_groups_allow():
	item_groups = frappe.get_all("Item Group", filters={"allow_getting_default_items":1})

	return item_groups

@frappe.whitelist()
def add_item(item_code, with_items=False):
	quotation = _get_cart_quotation()
	existing_item_codes = [d.item_code for d in quotation.items]

	if item_code not in existing_item_codes:
		quotation.append("items", {"item_code": item_code, "qty": 1})

	return update_cart(quotation, with_items)
