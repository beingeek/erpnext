# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe, erpnext
import frappe.defaults
from frappe import msgprint, _
from frappe.utils import cstr, flt, cint
from erpnext.stock.stock_ledger import update_entries_after
from erpnext.controllers.stock_controller import StockController
from erpnext.accounts.utils import get_company_default
from erpnext.stock.utils import get_stock_balance
from erpnext.stock.doctype.batch.batch import get_batch_qty
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from frappe.model.meta import get_field_precision
import json
from six import string_types

class OpeningEntryAccountError(frappe.ValidationError): pass
class EmptyStockReconciliationItemsError(frappe.ValidationError): pass

class StockReconciliation(StockController):
	def __init__(self, *args, **kwargs):
		super(StockReconciliation, self).__init__(*args, **kwargs)
		self.head_row = ["Item Code", "Warehouse", "Quantity", "Valuation Rate"]

	def validate(self):
		if not self.expense_account:
			self.expense_account = frappe.get_cached_value('Company',  self.company,  "stock_adjustment_account")
		if not self.cost_center:
			self.cost_center = frappe.get_cached_value('Company',  self.company,  "cost_center")
		self.validate_posting_time()
		self.remove_items_with_no_change()
		self.validate_data()
		self.validate_expense_account()
		self.set_total_qty_and_amount()

	def on_submit(self):
		self.update_stock_ledger()
		self.make_gl_entries()

	def on_cancel(self):
		self.update_stock_ledger()
		self.make_gl_entries_on_cancel()

	def remove_items_with_no_change(self):
		"""Remove items if qty or rate is not changed"""
		self.difference_amount = 0.0
		def _changed(item):
			qty, rate = get_stock_balance_for(item.item_code, item.warehouse,
					self.posting_date, self.posting_time, item.batch_no, with_valuation_rate=True)
			if (item.qty==None or item.qty==qty) and (item.valuation_rate==None or item.valuation_rate==rate):
				return False
			else:
				# set default as current rates
				if item.qty==None:
					item.qty = qty

				if item.valuation_rate==None:
					item.valuation_rate = rate

				item.current_qty = qty
				item.current_valuation_rate = rate
				self.difference_amount += (flt(item.qty) * flt(item.valuation_rate or rate)) - (flt(qty) * flt(rate))
				return True

		items = list(filter(lambda d: _changed(d), self.items))

		if not items:
			frappe.throw(_("None of the items have any change in quantity or value."),
				EmptyStockReconciliationItemsError)

		elif len(items) != len(self.items):
			self.items = items
			for i, item in enumerate(self.items):
				item.idx = i + 1
			#frappe.msgprint(_("Removed items with no change in quantity or value."))

	def validate_data(self):
		def _get_msg(row_num, msg):
			return _("Row # {0}: ").format(row_num+1) + msg

		self.validation_messages = []
		item_warehouse_combinations = []

		default_currency = frappe.db.get_default("currency")

		for row_num, row in enumerate(self.items):
			# find duplicates
			if [row.item_code, row.warehouse] in item_warehouse_combinations:
				self.validation_messages.append(_get_msg(row_num, _("Duplicate entry")))
			else:
				item_warehouse_combinations.append([row.item_code, row.warehouse])

			self.validate_item(row.item_code, row_num+1)

			# validate warehouse
			if not frappe.db.get_value("Warehouse", row.warehouse):
				self.validation_messages.append(_get_msg(row_num, _("Warehouse not found in the system")))

			# if both not specified
			if row.qty in ["", None] and row.valuation_rate in ["", None]:
				self.validation_messages.append(_get_msg(row_num,
					_("Please specify either Quantity or Valuation Rate or both")))

			# do not allow negative quantity
			if flt(row.qty) < 0:
				self.validation_messages.append(_get_msg(row_num,
					_("Negative Quantity is not allowed")))

			# do not allow negative valuation
			if flt(row.valuation_rate) < 0:
				self.validation_messages.append(_get_msg(row_num,
					_("Negative Valuation Rate is not allowed")))

			if row.qty and row.valuation_rate in ["", None]:
				row.valuation_rate = get_stock_balance_for(row.item_code, row.warehouse,
							self.posting_date, self.posting_time, row.batch_no, with_valuation_rate=True)[1]
				if not row.valuation_rate:
					# try if there is a buying price list in default currency
					buying_rate = frappe.db.get_value("Item Price", {"item_code": row.item_code,
						"buying": 1, "currency": default_currency}, "price_list_rate")
					if buying_rate:
						row.valuation_rate = buying_rate

					else:
						# get valuation rate from Item
						row.valuation_rate = frappe.get_value('Item', row.item_code, 'valuation_rate')

		# throw all validation messages
		if self.validation_messages:
			for msg in self.validation_messages:
				msgprint(msg)

			raise frappe.ValidationError(self.validation_messages)

	def validate_item(self, item_code, row_num):
		from erpnext.stock.doctype.item.item import validate_end_of_life, \
			validate_is_stock_item, validate_cancelled_item

		# using try except to catch all validation msgs and display together

		try:
			item = frappe.get_doc("Item", item_code)

			# end of life and stock item
			validate_end_of_life(item_code, item.end_of_life, item.disabled, verbose=0)
			validate_is_stock_item(item_code, item.is_stock_item, verbose=0)

			# item should not be serialized
			if item.has_serial_no == 1:
				raise frappe.ValidationError(_("Serialized Item {0} cannot be updated using Stock Reconciliation, please use Stock Entry").format(item_code))

			# item managed batch-wise not allowed
			#if item.has_batch_no == 1:
			#	raise frappe.ValidationError(_("Batched Item {0} cannot be updated using Stock Reconciliation, instead use Stock Entry").format(item_code))

			# docstatus should be < 2
			validate_cancelled_item(item_code, item.docstatus, verbose=0)

		except Exception as e:
			self.validation_messages.append(_("Row # ") + ("%d: " % (row_num)) + cstr(e))

	def update_stock_ledger(self):
		sl_entries = []

		for d in self.items:
			sl_entries.append(self.get_sl_entries(d, {
				"actual_qty": flt(d.quantity_difference)
			}))

		if self.docstatus == 2:
			sl_entries.reverse()

		self.make_sl_entries(sl_entries, self.amended_from and 'Yes' or 'No')

	def get_gl_entries(self, warehouse_account=None):
		if not self.cost_center:
			msgprint(_("Please enter Cost Center"), raise_exception=1)

		return super(StockReconciliation, self).get_gl_entries(warehouse_account,
			self.expense_account, self.cost_center)

	def validate_expense_account(self):
		if not cint(erpnext.is_perpetual_inventory_enabled(self.company)):
			return

		if not self.expense_account:
			msgprint(_("Please enter Expense Account"), raise_exception=1)
		elif not frappe.db.sql("""select name from `tabStock Ledger Entry` limit 1"""):
			if frappe.db.get_value("Account", self.expense_account, "report_type") == "Profit and Loss":
				frappe.throw(_("Difference Account must be a Asset/Liability type account, since this Stock Reconciliation is an Opening Entry"), OpeningEntryAccountError)

	def set_total_qty_and_amount(self):
		for d in self.get("items"):
			d.amount = flt(d.qty, d.precision("qty")) * flt(d.valuation_rate, d.precision("valuation_rate"))
			d.current_amount = (flt(d.current_qty,
				d.precision("current_qty")) * flt(d.current_valuation_rate, d.precision("current_valuation_rate")))

			d.quantity_difference = flt(d.qty) - flt(d.current_qty)
			d.amount_difference = flt(d.amount) - flt(d.current_amount)

	def get_items_for(self, warehouse):
		self.items = []
		for item in get_items(warehouse, self.posting_date, self.posting_time, self.company):
			self.append("items", item)

	def submit(self):
		if len(self.items) > 100:
			msgprint(_("The task has been enqueued as a background job. In case there is any issue on processing in background, the system will add a comment about the error on this Stock Reconciliation and revert to the Draft stage"))
			self.queue_action('submit')
		else:
			self._submit()

	def cancel(self):
		if len(self.items) > 100:
			self.queue_action('cancel')
		else:
			self._cancel()

@frappe.whitelist()
def get_items(warehouse, posting_date, posting_time, company, item_group=None):
	wh_lft, wh_rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
	item_group_cond = ""
	if item_group:
		ig_lft, ig_rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"])
		item_group_cond = "and exists (select name from `tabItem Group` where lft >= {0} and rgt <= {1} and name=i.item_group)"\
			.format(ig_lft, ig_rgt)

	items = frappe.db.sql("""
		select i.name, bin.warehouse
		from tabBin bin, tabItem i
		where i.name=bin.item_code and i.disabled=0
		and exists(select name from `tabWarehouse` where lft >= %s and rgt <= %s and name=bin.warehouse)
		{0}
	""".format(item_group_cond), (wh_lft, wh_rgt))

	items += frappe.db.sql("""
		select i.name, id.default_warehouse
		from tabItem i, `tabItem Default` id
		where i.name = id.parent
			and exists(select name from `tabWarehouse` where lft >= %s and rgt <= %s and (name=id.default_warehouse or name=i.default_warehouse))
			and i.is_stock_item = 1 and i.has_serial_no = 0
			and i.has_variants = 0 and i.disabled = 0 and id.company=%s
			{0}
		group by i.name
	""".format(item_group_cond), (wh_lft, wh_rgt, company))

	res = []
	for d in set(items):
		item_details = get_item_details({
			"company": company,
			"posting_date": posting_date,
			"posting_time": posting_time,
			"item_code": d[0],
			"warehouse": d[1],
		})
		res.append(item_details)

	res = sorted(res, key=lambda d: not bool(d.get('current_qty')))

	return res

@frappe.whitelist()
def get_item_details(args):
	if isinstance(args, string_types):
		args = json.loads(args)

	args = frappe._dict(args)
	out = frappe._dict()

	if not args.item_code or not args.posting_date or not args.posting_time or not args.company:
		return out

	item = frappe.get_cached_doc("Item", args.item_code)
	item_defaults = get_item_defaults(item.name, args.company)
	item_group_defaults = get_item_group_defaults(item.name, args.company)

	out.item_code = args.item_code
	out.item_name = args.item_name or item.item_name

	if args.warehouse:
		out.warehouse = args.warehouse
	else:
		from frappe.defaults import get_user_default_as_list
		user_default_warehouse_list = get_user_default_as_list('Warehouse')
		user_default_warehouse = user_default_warehouse_list[0] \
			if len(user_default_warehouse_list) == 1 else ""

		out.warehouse = user_default_warehouse or item_defaults.get("default_warehouse") or\
			item_group_defaults.get("default_warehouse")
		args.warehouse = out.warehouse

	if args.item_code and args.warehouse:
		out.current_qty, out.current_valuation_rate = get_stock_balance_for(args.item_code, args.warehouse,
			args.posting_date, args.posting_time, args.batch_no)

	if not item.has_batch_no or args.batch_no:
		out.qty = flt(args.qty) or out.current_qty or None
		out.valuation_rate = out.current_valuation_rate or None

	meta = frappe.get_meta("Stock Reconciliation Item")
	current_qty_precision = get_field_precision(meta.get_field('current_qty'))
	current_val_rate_precision = get_field_precision(meta.get_field('current_valuation_rate'))
	val_rate_precision = get_field_precision(meta.get_field('valuation_rate'))

	out.current_amount = flt(out.current_qty, current_qty_precision) * flt(out.current_valuation_rate, current_val_rate_precision)
	out.amount = flt(out.qty, current_qty_precision) * flt(out.valuation_rate, val_rate_precision)

	if out.qty or out.valuation_rate:
		out.quantity_difference = flt(out.qty) - flt(out.current_qty)
		out.amount_difference = out.amount - out.current_amount

	return out


def get_stock_balance_for(item_code, warehouse, posting_date, posting_time, batch_no=None, with_valuation_rate=True):
	frappe.has_permission("Stock Reconciliation", "write", throw=True)

	item_dict = frappe.get_cached_value("Item", item_code, ["has_batch_no"], as_dict=1)
	qty, rate = get_stock_balance(item_code, warehouse,
		posting_date, posting_time, with_valuation_rate=with_valuation_rate)

	if item_dict.get("has_batch_no") and batch_no:
		qty = flt(get_batch_qty(batch_no, warehouse))

	return qty, rate


@frappe.whitelist()
def get_difference_account(purpose, company):
	if purpose == 'Stock Reconciliation':
		account = get_company_default(company, "stock_adjustment_account")
	else:
		account = frappe.db.get_value('Account', {'is_group': 0,
			'company': company, 'account_type': 'Temporary'}, 'name')

	return account