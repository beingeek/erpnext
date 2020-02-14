# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
from __future__ import unicode_literals

no_cache = 1
no_sitemap = 1

import frappe
from erpnext.shopping_cart.cart import get_cart_quotation

def get_context(context):
	context.no_cache = 1
	
	if frappe.session.user == "Guest":
		raise frappe.PermissionError, "Please login first"
	
	context.update(get_cart_quotation())
