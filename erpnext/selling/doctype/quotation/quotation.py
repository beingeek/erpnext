# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt, nowdate, getdate, formatdate
from frappe import _

from erpnext.controllers.selling_controller import SellingController

form_grid_templates = {
	"items": "templates/form_grid/item_grid.html"
}

class Quotation(SellingController):
	def __setup__(self):
		super(Quotation, self).__setup__()
		self.cart_warnings = []
		self.cart_errors = []

	def set_indicator(self):
		if self.docstatus==1:
			if self.status == "Ordered":
				self.indicator_color = 'green'
				self.indicator_title = 'Confirmed'
			else:
				self.indicator_color = 'orange'
				self.indicator_title = 'Received by Sundine'

			if self.valid_till and getdate(self.valid_till) < getdate(nowdate()):
				self.indicator_color = 'darkgrey'
				self.indicator_title = 'Expired'
		else:
			if self.confirmed_by_customer:
				self.indicator_color = 'red'
				self.indicator_title = 'Sent to Sundine'
			else:
				self.indicator_color = 'yellow'
				self.indicator_title = 'Draft'


	def validate(self):
		super(Quotation, self).validate()
		self.set_status()
		self.update_opportunity()
		self.validate_order_type()
		self.validate_uom_is_integer("stock_uom", "qty")
		self.validate_quotation_to()
		self.validate_valid_till()
		self.validate_delivery_date()
		if self.items:
			self.with_items = 1

	def get_cart_warnings(self):
		if self.delivery_date:
			same_date_quotations = frappe.get_all("Quotation", filters={
				"name": ['!=', self.name],
				"docstatus": ['<', 2],
				"quotation_to": "Customer",
				"customer": self.customer,
				"delivery_date": self.delivery_date,
			})
			if same_date_quotations:
				links = ["<b><a href='/purchase-orders/{0}' target='_blank'>{0}</a></b>".format(d.name) for d in same_date_quotations]
				self.cart_warnings.append(_("Purchase Orders already exist for Delivery Date {0}: {1}")
					.format(formatdate(self.delivery_date, "EEE, MMMM d, Y"), ", ".join(links)))

			same_date_sales_orders = frappe.get_all("Sales Order", filters={
				"docstatus": ['<', 2],
				"customer": self.customer,
				"delivery_date": self.delivery_date
			})
			if same_date_sales_orders:
				links = ["<b><a href='/sales-orders/{0}' target='_blank'>{0}</a></b>".format(d.name) for d in same_date_sales_orders]
				self.cart_warnings.append(_("Sales Orders already exist for Delivery Date {0}: {1}")
					.format(formatdate(self.delivery_date, "EEE, MMMM d, Y"), ", ".join(links)))

	def get_cart_errors(self):
		pass
		# if not self.delivery_date:
		# 	self.cart_errors.append(_("Delivery Date is mandatory"))
			
	def validate_valid_till(self):
		if self.valid_till and self.valid_till < self.transaction_date:
			frappe.throw(_("Valid till date cannot be before transaction date"))

	def validate_delivery_date(self):
		if self.order_type not in ['Sales', 'Shopping Cart']:
			return

		raise_exception = self._action == "Submit" or self.confirmed_by_customer

		if self.delivery_date and getdate(self.delivery_date) < getdate(self.transaction_date):
			message = _("Delivery Date <b>{0}</b> cannot be before Order Date").format(
				formatdate(self.delivery_date, "EEE, MMMM d, Y"))
			frappe.msgprint(message, raise_exception=raise_exception, indicator="red")
			self.cart_errors.append(message)
			self.delivery_date = None

		if self.confirmed_by_customer and not self.delivery_date:
			frappe.throw(_("Delivery Date is mandatory"))

	def has_sales_order(self):
		return frappe.db.get_value("Sales Order Item", {"prevdoc_docname": self.name, "docstatus": 1})

	def validate_order_type(self):
		super(Quotation, self).validate_order_type()

	def validate_quotation_to(self):
		if self.customer:
			self.quotation_to = "Customer"
			self.lead = None
		elif self.lead:
			self.quotation_to = "Lead"

	def update_lead(self):
		if self.lead:
			frappe.get_doc("Lead", self.lead).set_status(update=True)

	def update_opportunity(self):
		for opportunity in list(set([d.prevdoc_docname for d in self.get("items")])):
			if opportunity:
				self.update_opportunity_status(opportunity)

		if self.opportunity:
			self.update_opportunity_status()

	def update_opportunity_status(self, opportunity=None):
		if not opportunity:
			opportunity = self.opportunity

		opp = frappe.get_doc("Opportunity", opportunity)
		opp.status = None
		opp.set_status(update=True)

	def declare_order_lost(self, reason):
		if not self.has_sales_order():
			frappe.db.set(self, 'status', 'Lost')
			frappe.db.set(self, 'order_lost_reason', reason)
			self.update_opportunity()
			self.update_lead()
		else:
			frappe.throw(_("Cannot set as Lost as Sales Order is made."))

	def on_submit(self):
		# Check for Approving Authority
		frappe.get_doc('Authorization Control').validate_approving_authority(self.doctype,
			self.company, self.base_grand_total, self)

		#update enquiry status
		self.update_opportunity()
		self.update_lead()

	def before_submit(self):
		self.validate_confirmed_by_customer()

	def validate_confirmed_by_customer(self):
		if self.order_type == "Shopping Cart" and not self.confirmed_by_customer:
			frappe.throw(_("Order not yet confirmed by customer"))

	def on_cancel(self):
		#update enquiry status
		self.set_status(update=True)
		self.update_opportunity()
		self.update_lead()

	def print_other_charges(self,docname):
		print_lst = []
		for d in self.get('taxes'):
			lst1 = []
			lst1.append(d.description)
			lst1.append(d.total)
			print_lst.append(lst1)
		return print_lst

	def on_recurring(self, reference_doc, auto_repeat_doc):
		self.valid_till = None

def get_list_context(context=None):
	from erpnext.controllers.website_list_for_contact import get_list_context
	list_context = get_list_context(context)
	list_context.update({
		'show_sidebar': False,
		'show_search': True,
		'no_breadcrumbs': False,
		'title': _('Purchase Orders'),
		'order_by': 'delivery_date desc, transaction_date desc'
	})

	return list_context

@frappe.whitelist()
def make_sales_order(source_name, target_doc=None):
	quotation = frappe.db.get_value("Quotation", source_name, ["transaction_date", "valid_till"], as_dict = 1)
	if quotation.valid_till and (quotation.valid_till < quotation.transaction_date or quotation.valid_till < getdate(nowdate())):
		frappe.throw(_("Validity period of this quotation has ended."))

	sales_order = frappe.get_all("Sales Order Item", fields='distinct parent', filters={"prevdoc_docname": source_name, "docstatus": ['<', 2]})
	if sales_order:
		sales_order_name = [frappe.get_desk_link("Sales Order", d.parent) for d in sales_order]
		frappe.throw(_("Sales Order already exists: {0}").format(", ".join(sales_order_name)))

	return _make_sales_order(source_name, target_doc)

def _make_sales_order(source_name, target_doc=None, ignore_permissions=False):
	customer = _make_customer(source_name, ignore_permissions)

	def set_missing_values(source, target):
		if customer:
			target.customer = customer.name
			target.customer_name = customer.customer_name
		# target.ignore_pricing_rule = 1
		target.flags.ignore_permissions = ignore_permissions
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(obj, target, source_parent):
		target.stock_qty = flt(obj.qty) * flt(obj.conversion_factor)

	doclist = get_mapped_doc("Quotation", source_name, {
			"Quotation": {
				"doctype": "Sales Order",
				"field_map": {
					"delivery_date": "delivery_date"
				},
				"validation": {
					"docstatus": ["=", 1]
				}
			},
			"Quotation Item": {
				"doctype": "Sales Order Item",
				"field_map": {
					"parent": "prevdoc_docname"
				},
				"postprocess": update_item
			},
			"Sales Taxes and Charges": {
				"doctype": "Sales Taxes and Charges",
				"add_if_empty": True
			},
			"Sales Team": {
				"doctype": "Sales Team",
				"add_if_empty": True
			}
		}, target_doc, set_missing_values, ignore_permissions=ignore_permissions)

	# postprocess: fetch shipping address, set missing values

	return doclist

@frappe.whitelist()
def make_sales_invoice(source_name, target_doc=None):
	return _make_sales_invoice(source_name, target_doc)

def _make_sales_invoice(source_name, target_doc=None, ignore_permissions=False):
	customer = _make_customer(source_name, ignore_permissions)

	def set_missing_values(source, target):
		if customer:
			target.customer = customer.name
			target.customer_name = customer.customer_name
		# target.ignore_pricing_rule = 1
		target.flags.ignore_permissions = ignore_permissions
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(obj, target, source_parent):
		target.cost_center = None
		target.stock_qty = flt(obj.qty) * flt(obj.conversion_factor)

	doclist = get_mapped_doc("Quotation", source_name, {
			"Quotation": {
				"doctype": "Sales Invoice",
				"validation": {
					"docstatus": ["=", 1]
				}
			},
			"Quotation Item": {
				"doctype": "Sales Invoice Item",
				"postprocess": update_item
			},
			"Sales Taxes and Charges": {
				"doctype": "Sales Taxes and Charges",
				"add_if_empty": True
			},
			"Sales Team": {
				"doctype": "Sales Team",
				"add_if_empty": True
			}
		}, target_doc, set_missing_values, ignore_permissions=ignore_permissions)

	return doclist	

def _make_customer(source_name, ignore_permissions=False):
	quotation = frappe.db.get_value("Quotation", source_name, ["lead", "order_type", "customer"])
	if quotation and quotation[0] and not quotation[2]:
		lead_name = quotation[0]
		customer_name = frappe.db.get_value("Customer", {"lead_name": lead_name},
			["name", "customer_name"], as_dict=True)
		if not customer_name:
			from erpnext.crm.doctype.lead.lead import _make_customer
			customer_doclist = _make_customer(lead_name, ignore_permissions=ignore_permissions)
			customer = frappe.get_doc(customer_doclist)
			customer.flags.ignore_permissions = ignore_permissions
			if quotation[1] == "Shopping Cart":
				customer.customer_group = frappe.db.get_value("Shopping Cart Settings", None,
					"default_customer_group")

			try:
				customer.insert()
				return customer
			except frappe.NameError:
				if frappe.defaults.get_global_default('cust_master_name') == "Customer Name":
					customer.run_method("autoname")
					customer.name += "-" + lead_name
					customer.insert()
					return customer
				else:
					raise
			except frappe.MandatoryError:
				frappe.local.message_log = []
				frappe.throw(_("Please create Customer from Lead {0}").format(lead_name))
		else:
			return customer_name
