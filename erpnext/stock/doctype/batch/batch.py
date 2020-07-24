# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
from six import text_type
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname, revert_series_if_last
from frappe.utils import flt, cint, cstr, get_link_to_form
from frappe.utils.jinja import render_template
from frappe.utils.data import add_days
from six import string_types
import math

class UnableToSelectBatchError(frappe.ValidationError):
	pass


def get_name_from_hash():
	"""
	Get a name for a Batch by generating a unique hash.
	:return: The hash that was generated.
	"""
	temp = None
	while not temp:
		temp = frappe.generate_hash()[:7].upper()
		if frappe.db.exists('Batch', temp):
			temp = None

	return temp


def batch_uses_naming_series():
	"""
	Verify if the Batch is to be named using a naming series
	:return: bool
	"""
	use_naming_series = cint(frappe.db.get_single_value('Stock Settings', 'use_naming_series'))
	return bool(use_naming_series)


def _get_batch_prefix():
	"""
	Get the naming series prefix set in Stock Settings.

	It does not do any sanity checks so make sure to use it after checking if the Batch
	is set to use naming series.
	:return: The naming series.
	"""
	naming_series_prefix = frappe.db.get_single_value('Stock Settings', 'naming_series_prefix')
	if not naming_series_prefix:
		naming_series_prefix = 'BATCH-'

	return naming_series_prefix


def _make_naming_series_key(prefix):
	"""
	Make naming series key for a Batch.

	Naming series key is in the format [prefix].[#####]
	:param prefix: Naming series prefix gotten from Stock Settings
	:return: The derived key. If no prefix is given, an empty string is returned
	"""
	if not text_type(prefix):
		return ''
	elif not prefix.find('#'):
		return prefix.upper() + '.#####'
	else:
		return prefix.upper()


def get_batch_naming_series():
	"""
	Get naming series key for a Batch.

	Naming series key is in the format [prefix].[#####]
	:return: The naming series or empty string if not available
	"""
	series = ''
	if batch_uses_naming_series():
		prefix = _get_batch_prefix()
		key = _make_naming_series_key(prefix)
		series = key

	return series


class Batch(Document):
	def autoname(self):
		"""Generate random ID for batch if not specified"""
		if not self.batch_id:
			create_new_batch, batch_number_series = frappe.db.get_value('Item', self.item,
				['create_new_batch', 'batch_number_series'])

			if create_new_batch:
				if batch_number_series:
					batch_number_series = self.replace_supplier_code_namng_series(batch_number_series)
					self.batch_id = make_autoname(batch_number_series, self.doctype, self)
				elif batch_uses_naming_series():
					self.batch_id = self.get_name_from_naming_series()
				else:
					self.batch_id = get_name_from_hash()
			else:
				frappe.throw(_('Batch ID is mandatory'), frappe.MandatoryError)

		self.name = self.batch_id

	def onload(self):
		self.image = frappe.db.get_value('Item', self.item, 'image')

	def after_delete(self):
		revert_series_if_last(get_batch_naming_series(), self.name)

	def validate(self):
		self.item_has_batch_enabled()
		self.update_item_details()

	def update_item_details(self):
		item_details = frappe.db.get_value("Item", self.item, ["item_name", "item_group"], as_dict=1)
		self.item_name = item_details.item_name
		self.item_group = item_details.item_group

	def item_has_batch_enabled(self):
		if frappe.db.get_value("Item", self.item, "has_batch_no") == 0:
			frappe.throw(_("The selected item cannot have Batch"))

	def before_save(self):
		has_expiry_date, shelf_life_in_days = frappe.db.get_value('Item', self.item, ['has_expiry_date', 'shelf_life_in_days'])
		if not self.expiry_date and has_expiry_date and shelf_life_in_days:
			self.expiry_date = add_days(self.manufacturing_date, shelf_life_in_days)

		if has_expiry_date and not self.expiry_date:
			frappe.throw(msg=_("Please set {0} for Batched Item {1}, which is used to set {2} on Submit.") \
				.format(frappe.bold("Shelf Life in Days"),
					get_link_to_form("Item", self.item),
					frappe.bold("Batch Expiry Date")),
				title=_("Expiry Date Mandatory"))

	def get_name_from_naming_series(self):
		"""
		Get a name generated for a Batch from the Batch's naming series.
		:return: The string that was generated.
		"""
		naming_series_prefix = _get_batch_prefix()
		# validate_template(naming_series_prefix)
		naming_series_prefix = self.replace_supplier_code_namng_series(naming_series_prefix)
		name = make_autoname(naming_series_prefix, self.doctype, self)

		return name

	def replace_supplier_code_namng_series(self, series):
		if '.{SC}.' in series:
			supplier_code = None
			if self.supplier:
				supplier_code = frappe.get_cached_value("Supplier", self.supplier, 'supplier_code')

			if supplier_code:
				series = series.replace('.{SC}.', supplier_code)
			else:
				if self.supplier:
					frappe.throw(_("Cannot automatically create Batch No for Item {0} because Supplier Code not set for Supplier {1}. Please set Supplier Code or create Batch manually.")
						.format(self.item, self.supplier))
				else:
					frappe.throw(_("Cannot automatically create Batch No for Item {0} because no Supplier can be found. Please create Batch manually.")
						.format(self.item))

		return series


@frappe.whitelist()
def get_batch_qty(batch_no=None, warehouse=None, item_code=None):
	"""Returns batch actual qty if warehouse is passed,
		or returns dict of qty by warehouse if warehouse is None

	The user must pass either batch_no or batch_no + warehouse or item_code + warehouse

	:param batch_no: Optional - give qty for this batch no
	:param warehouse: Optional - give qty for this warehouse
	:param item_code: Optional - give qty for this item"""

	out = 0
	if batch_no and warehouse:
		out = flt(frappe.db.sql("""select sum(actual_qty)
			from `tabStock Ledger Entry`
			where warehouse=%s and batch_no=%s""",
			(warehouse, batch_no))[0][0] or 0)

	if batch_no and not warehouse:
		out = frappe.db.sql('''select warehouse, sum(actual_qty) as qty
			from `tabStock Ledger Entry`
			where batch_no=%s
			group by warehouse''', batch_no, as_dict=1)

	if not batch_no and item_code and warehouse:
		out = frappe.db.sql('''select batch_no, sum(actual_qty) as qty
			from `tabStock Ledger Entry`
			where item_code = %s and warehouse=%s
			group by batch_no''', (item_code, warehouse), as_dict=1)

	return out

def get_batch_qty_on(batch_no, warehouse, posting_date, posting_time):
	res = frappe.db.sql("""
		select sum(actual_qty)
		from `tabStock Ledger Entry`
		where timestamp(posting_date, posting_time) <= timestamp(%s, %s)
			and ifnull(is_cancelled, 'No') = 'No' and warehouse=%s and batch_no=%s""",
	(posting_date, posting_time, warehouse, batch_no))

	return flt(res[0][0]) if res else 0.0


@frappe.whitelist()
def get_batches_by_oldest(item_code, warehouse):
	"""Returns the oldest batch and qty for the given item_code and warehouse"""
	batches = get_batch_qty(item_code=item_code, warehouse=warehouse)
	batches_dates = [[batch, frappe.get_value('Batch', batch.batch_no, 'expiry_date')] for batch in batches]
	batches_dates.sort(key=lambda tup: tup[1])
	return batches_dates


@frappe.whitelist()
def split_batch(batch_no, item_code, warehouse, qty, new_batch_id=None):
	"""Split the batch into a new batch"""
	batch = frappe.get_doc(dict(doctype='Batch', item=item_code, batch_id=new_batch_id)).insert()

	company = frappe.db.get_value('Stock Ledger Entry', dict(
			item_code=item_code,
			batch_no=batch_no,
			warehouse=warehouse
		), ['company'])

	stock_entry = frappe.get_doc(dict(
		doctype='Stock Entry',
		purpose='Repack',
		company=company,
		items=[
			dict(
				item_code=item_code,
				qty=float(qty or 0),
				s_warehouse=warehouse,
				batch_no=batch_no
			),
			dict(
				item_code=item_code,
				qty=float(qty or 0),
				t_warehouse=warehouse,
				batch_no=batch.name
			),
		]
	))
	stock_entry.set_stock_entry_type()
	stock_entry.insert()
	stock_entry.submit()

	return batch.name


def set_batch_nos(doc, warehouse_field, throw=False):
	"""Automatically select `batch_no` for outgoing items in item table"""
	for d in doc.items:
		qty = d.get('stock_qty') or d.get('transfer_qty') or d.get('qty') or 0
		has_batch_no = frappe.db.get_value('Item', d.item_code, 'has_batch_no')
		warehouse = d.get(warehouse_field, None)
		if has_batch_no and warehouse and qty > 0:
			if not d.batch_no:
				d.batch_no = get_batch_no(d.item_code, warehouse, qty, throw, d.serial_no)
			else:
				batch_qty = get_batch_qty(batch_no=d.batch_no, warehouse=warehouse)
				if flt(batch_qty, d.precision("qty")) < flt(qty, d.precision("qty")) and throw:
					frappe.throw(_("Row #{0}: The batch {1} has only {2} qty. Please select another batch which has {3} qty available or split the row into multiple rows, to deliver/issue from multiple batches").format(d.idx, d.batch_no, batch_qty, qty))


def auto_select_and_split_batches(doc, warehouse_field):
	iuw_qty_map = {}
	iuw_boxes_map = {}
	iw_qty_map = {}
	for d in doc.items:
		warehouse = d.get(warehouse_field)
		if warehouse and frappe.get_cached_value("Item", d.item_code, "has_batch_no"):
			iuw_key = (d.item_code, cstr(d.get('uom')), warehouse)
			iw_key = (d.item_code, warehouse)

			iuw_qty_map.setdefault(iuw_key, 0)
			iuw_qty_map[iuw_key] += flt(d.get('qty'))

			if d.meta.get_field('boxes'):
				iuw_boxes_map.setdefault(iuw_key, 0)
				iuw_boxes_map[iuw_key] += flt(d.get('boxes'))

			iw_qty_map.setdefault(iw_key, 0)
			iw_qty_map[iw_key] += flt(d.get('qty'))

	visited = set()
	to_remove = []
	for d in doc.items:
		warehouse = d.get(warehouse_field)
		if warehouse and frappe.get_cached_value("Item", d.item_code, "has_batch_no"):
			iuw_key = (d.item_code, cstr(d.get('uom')), warehouse)
			if iuw_key not in visited:
				visited.add(iuw_key)
				d.batch_no = None
				d.qty = flt(iuw_qty_map.get(iuw_key))

				if d.meta.get_field('boxes'):
					d.boxes = flt(iuw_boxes_map.get(iuw_key))
			else:
				to_remove.append(d)

	for d in to_remove:
		doc.remove(d)

	updated_rows = []
	batches_used = {}
	for d in doc.items:
		updated_rows.append(d)
		warehouse = d.get(warehouse_field)
		if warehouse and frappe.get_cached_value("Item", d.item_code, "has_batch_no"):
			batches = get_sufficient_batch_or_fifo(d.item_code, warehouse, flt(d.qty), flt(d.conversion_factor),
				batches_used=batches_used, include_empty_batch=True, precision=d.precision('qty'))

			rows = [d]
			total_qty = flt(d.qty)
			total_boxes = flt(d.boxes) if d.meta.get_field('boxes') else 0

			for i in range(1, len(batches)):
				new_row = frappe.copy_doc(d)
				rows.append(new_row)
				updated_rows.append(new_row)

			for row, batch in zip(rows, batches):
				row.qty = batch.selected_qty
				row.batch_no = batch.batch_no

				if row.meta.get_field('boxes'):
					row.boxes = total_boxes * row.qty / total_qty if total_qty else 0

	# Replace with updated list
	for i, row in enumerate(updated_rows):
		row.idx = i + 1
	doc.items = updated_rows

	if doc.doctype == 'Stock Entry':
		doc.run_method("set_transfer_qty")
	else:
		doc.run_method("calculate_taxes_and_totals")


@frappe.whitelist()
def get_batch_no(item_code, warehouse, qty=1, throw=False, serial_no=None):
	"""
	Get batch number using First Expiring First Out method.
	:param item_code: `item_code` of Item Document
	:param warehouse: name of Warehouse to check
	:param qty: quantity of Items
	:return: String represent batch number of batch with sufficient quantity else an empty String
	"""

	batch_no = None
	batches = get_batches(item_code, warehouse)

	for batch in batches:
		if flt(qty) <= flt(batch.qty):
			batch_no = batch.name
			break

	if not batch_no:
		batch_no=""
		return batch_no
		frappe.msgprint(_('Please select a Batch for Item {0}. Unable to find a single batch that fulfills this requirement').format(frappe.bold(item_code)))
		if throw:
			raise UnableToSelectBatchError

	return batch_no


def round_down(value, decimals):
	factor = 10 ** decimals
	db_precision = 6 if decimals <= 6 else 9

	value = math.floor(flt(value * factor, db_precision)) / factor
	value = flt(value, db_precision)
	return value


@frappe.whitelist()
def get_sufficient_batch_or_fifo(item_code, warehouse, qty=1, conversion_factor=1, batches_used=None,
		include_empty_batch=False, precision=None):
	if not warehouse or not qty:
		return []

	if not precision:
		precision = cint(frappe.db.get_default("float_precision")) or 3

	batches = get_batches(item_code, warehouse)

	if batches_used:
		for batch in batches:
			if batch.name in batches_used:
				batch.qty -= flt(batches_used.get(batch.name))

		batches = [d for d in batches if d.qty > 0]

	selected_batches = []

	qty = flt(qty)
	conversion_factor = flt(conversion_factor or 1)
	stock_qty = qty * conversion_factor
	remaining_stock_qty = stock_qty

	for batch in batches:
		if remaining_stock_qty <= 0:
			break
		'''if stock_qty <= flt(batch.qty):
			return [{
				'batch_no': batch.name,
				'available_qty': batch.qty / conversion_factor,
				'selected_qty': qty
			}]'''

		selected_stock_qty = min(remaining_stock_qty, batch.qty)
		selected_qty = round_down(selected_stock_qty / conversion_factor, precision)
		if not selected_qty:
			continue

		selected_stock_qty = selected_qty * conversion_factor
		selected_batches.append(frappe._dict({
			'batch_no': batch.name,
			'available_qty': batch.qty / conversion_factor,
			'selected_qty': selected_qty
		}))

		if isinstance(batches_used, dict):
			batches_used.setdefault(batch.name, 0)
			batches_used[batch.name] += selected_stock_qty

		remaining_stock_qty -= selected_stock_qty

	if remaining_stock_qty > 0:
		if include_empty_batch:
			selected_batches.append(frappe._dict({
				'batch_no': None,
				'available_qty': 0,
				'selected_qty': remaining_stock_qty
			}))

		total_selected_qty = stock_qty - remaining_stock_qty
		frappe.msgprint(_("Only {0} {1} found in {2}".format(total_selected_qty, item_code, warehouse)))

	return selected_batches

def get_batch_received_date(batch_no, warehouse):
	date = frappe.db.sql("""
		select min(timestamp(posting_date, posting_time))
		from `tabStock Ledger Entry`
		where batch_no = %s and warehouse = %s
	""", [batch_no, warehouse])

	return date[0][0] if date else None

def get_batches(item_code, warehouse, posting_date=None, posting_time=None, qty_condition="positive"):
	if qty_condition == "both":
		having = "having qty != 0"
	elif qty_condition == "negative":
		having = "having qty < 0"
	else:
		having = "having qty > 0"

	date_cond = ""
	if posting_date:
		date_cond = "and (b.expiry_date is null or b.expiry_date >= %(posting_date)s)"
		if posting_time:
			date_cond += " and (sle.posting_date, sle.posting_time) <= (%(posting_date)s, %(posting_time)s)"
		else:
			date_cond += " and sle.posting_date <= %(posting_date)s"

	args = {
		'item_code': item_code,
		'warehouse': warehouse,
		'posting_date': posting_date,
		'posting_time': posting_time
	}

	batches = frappe.db.sql("""
		select b.name, sum(sle.actual_qty) as qty, b.expiry_date,
			min(timestamp(sle.posting_date, sle.posting_time)) received_date
		from `tabBatch` b
		join `tabStock Ledger Entry` sle ignore index (item_code, warehouse) on b.name = sle.batch_no
		where sle.item_code = %(item_code)s and sle.warehouse = %(warehouse)s {0}
		group by b.name
		{1}
	""".format(date_cond, having), args, as_dict=True)

	return sorted(batches, key=lambda d: (d.expiry_date, d.received_date))
