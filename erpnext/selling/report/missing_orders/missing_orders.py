# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import cint, getdate
from frappe import _

def execute(filters=None):
	if not filters: filters ={}
	doctype = filters.get("doctype")
	reference_delivery_date = getdate(filters.get('delivery_date'))
	enable_disable = filters.get('enable_disable')

	columns = get_columns()
	customers = get_sales_details(doctype, reference_delivery_date, enable_disable)

	for d in customers:
		d.last_order_amount = get_last_sales_amt(d.customer, doctype)
	
	return columns, customers

def get_sales_details(doctype, reference_delivery_date, enable_disable):
	condition = ''
	if enable_disable == 'Enabled':
		condition = 'and disabled = 0'
	elif enable_disable == 'Disabled':
		condition = 'and disabled = 1'

	cond = """sum(so.base_net_total) as 'total_order_considered',
			max(so.delivery_date) as 'last_delivery_date',
			DATEDIFF(CURDATE(), max(so.delivery_date)) as 'days_since_last_order' """
	if doctype == "Sales Order":
		cond = """sum(if(so.status = "Closed",
				so.base_net_total * so.per_delivered/100,
				so.base_net_total)) as 'total_order_considered',
			max(so.delivery_date) as 'last_delivery_date',
			DATEDIFF(CURDATE(), max(so.delivery_date)) as 'days_since_last_order'"""

	return frappe.db.sql("""select
			cust.name as customer,
			cust.customer_name,
			cust.territory,
			cust.customer_group,
			count(distinct(so.name)) as 'num_of_order',
			sum(base_net_total) as 'total_order_value', {0}
		from `tabCustomer` cust, `tab{1}` so
		where cust.name = so.customer and so.docstatus < 2 {2}
		group by cust.name
		having last_delivery_date < %s
		order by 'days_since_last_order' desc
	""".format(cond, doctype, condition), reference_delivery_date, as_dict=1)

def get_last_sales_amt(customer, doctype):
	cond = "delivery_date"
	res =  frappe.db.sql("""select base_net_total from `tab{0}`
		where customer = %s and docstatus < 2 order by {1} desc
		limit 1""".format(doctype, cond), customer)

	return res and res[0][0] or 0

def get_columns():
	return [
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 240},
		{"fieldname": "last_delivery_date", "label": _("Last Delivery Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_since_last_order", "label": _("Day Since Last Order"), "fieldtype": "Int", "width": 100},
		{"fieldname": "last_order_amount", "label": _("Last Order Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "num_of_order", "label": _("Number Of Orders"), "fieldtype": "Int", "width": 120},
		{"fieldname": "total_order_considered", "label": _("Total Order Considered"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "total_order_value", "label": _("Total Order Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "customer_group", "label": _("Customer Group"), "fieldtype": "Link", "options": "Customer Group", "width": 120},
		{"fieldname": "territory", "label": _("Territory"), "fieldtype": "Link", "options": "Territory", "width": 120}
	]
