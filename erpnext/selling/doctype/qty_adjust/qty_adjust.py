# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.api5 import qtyAdjust
from six import string_types
import json


class QtyAdjust(Document):
	def qty_adjust_sales_orders(self):
		if isinstance(self.sales_orders, string_types):
			sales_orders = json.loads(self.sales_orders)

		# Validate
		for d in self.sales_orders:
			if flt(d.back_order_qty) and not d.back_order_date:
				frappe.throw(_("Row #{0}: Please select Back Order Date for SO {1}").format(d.idx, d.sales_order))

		# Adjust
		for d in self.sales_orders:
			qtyAdjust(d.customer, d.sales_order, self.item_code, d.ordered_qty, d.allocated_qty, d.back_order_qty,
					d.back_order_date or d.date)

		frappe.msgprint("Sales Orders Adjusted")
