# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _, throw
from frappe.utils import flt, cint, add_days, cstr, add_months, getdate
import json, copy
from erpnext.accounts.doctype.pricing_rule.pricing_rule import get_pricing_rule_for_item, set_transaction_type
from erpnext.setup.utils import get_exchange_rate
from frappe.model.meta import get_field_precision
from erpnext.stock.doctype.batch.batch import get_batch_no
from erpnext import get_company_currency
from erpnext.stock.doctype.item.item import get_item_defaults, get_uom_conv_factor, convert_item_uom_for
from erpnext.stock.doctype.price_list.price_list import get_price_list_details
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from erpnext.setup.doctype.brand.brand import get_brand_defaults
from erpnext.stock.doctype.item_manufacturer.item_manufacturer import get_item_manufacturer_part_no

from six import string_types, iteritems

sales_doctypes = ['Quotation', 'Sales Order', 'Delivery Note', 'Sales Invoice']
purchase_doctypes = ['Material Request', 'Supplier Quotation', 'Purchase Order', 'Purchase Receipt', 'Purchase Invoice']

@frappe.whitelist()
def get_item_details(args, doc=None, for_validate=False, overwrite_warehouse=True, skip_valuation_rates=False):
	"""
		args = {
			"item_code": "",
			"warehouse": None,
			"customer": "",
			"conversion_rate": 1.0,
			"selling_price_list": None,
			"price_list_currency": None,
			"plc_conversion_rate": 1.0,
			"doctype": "",
			"name": "",
			"supplier": None,
			"transaction_date": None,
			"conversion_rate": 1.0,
			"buying_price_list": None,
			"is_subcontracted": "Yes" / "No",
			"ignore_pricing_rule": 0/1
			"project": ""
			"set_warehouse": ""
		}
	"""

	args = process_args(args)
	item = frappe.get_cached_doc("Item", args.item_code)
	validate_item_details(args, item)

	out = get_basic_details(args, item, overwrite_warehouse)

	if isinstance(doc, string_types):
		doc = json.loads(doc)

	if doc and doc.get('doctype') == 'Purchase Invoice':
		args['bill_date'] = doc.get('bill_date')

	if doc:
		args['posting_date'] = doc.get('posting_date')
		args['transaction_date'] = doc.get('transaction_date')

	get_item_tax_template(args, item, out)
	out["item_tax_rate"] = get_item_tax_map(args.company, args.get("item_tax_template") if out.get("item_tax_template") is None \
		else out.get("item_tax_template"), as_json=True)

	get_party_item_code(args, item, out)

	if not skip_valuation_rates and args.transaction_type == 'selling':
		set_valuation_rate(out, args)

	update_party_blanket_order(args, out)

	get_price_list_rate(args, item, out)

	get_alt_uom_qty(args, item, out)

	if args.customer and cint(args.is_pos):
		out.update(get_pos_profile_item_details(args.company, args))

	if out.get("warehouse"):
		out.update(get_bin_details(args.item_code, out.warehouse))

	# update args with out, if key or value not exists
	for key, value in iteritems(out):
		if args.get(key) is None:
			args[key] = value

	data = get_pricing_rule_for_item(args, out.price_list_rate,
		doc, for_validate=for_validate)

	out.update(data)

	update_stock(args, out)

	if args.transaction_date and item.lead_time_days:
		out.schedule_date = out.lead_time_date = add_days(args.transaction_date,
			item.lead_time_days)

	if args.get("is_subcontracted") == "Yes":
		out.bom = args.get('bom') or get_default_bom(args.item_code)

	if not skip_valuation_rates and args.transaction_type == 'selling':
		get_gross_profit(out)

	if args.doctype == 'Material Request':
		out.rate = args.rate or out.price_list_rate
		out.amount = flt(args.qty * out.rate)

	if args.doctype == 'Sales Order':
		custom_projected_qty = get_item_custom_projected_qty(args.transaction_date, [args.item_code], args.name)
		out.update(custom_projected_qty.get(args.item_code, {}))

	return out

def update_stock(args, out):
	if (args.get("doctype") == "Delivery Note" or
		(args.get("doctype") == "Sales Invoice" and args.get('update_stock'))) \
		and out.warehouse and out.stock_qty > 0:

		'''if out.has_batch_no and not args.get("batch_no"):
			out.batch_no = get_batch_no(out.item_code, out.warehouse, out.qty)
			actual_batch_qty = get_batch_qty(out.batch_no, out.warehouse, out.item_code)
			if actual_batch_qty:
				out.update(actual_batch_qty)'''

		if out.has_serial_no and args.get('batch_no'):
			reserved_so = get_so_reservation_for_item(args)
			out.batch_no = args.get('batch_no')
			out.serial_no = get_serial_no(out, args.serial_no, sales_order=reserved_so)

		elif out.has_serial_no:
			reserved_so = get_so_reservation_for_item(args)
			out.serial_no = get_serial_no(out, args.serial_no, sales_order=reserved_so)


def set_valuation_rate(out, args):
	if frappe.db.exists("Product Bundle", args.item_code, cache=True):
		valuation_rate = 0.0
		bundled_items = frappe.get_doc("Product Bundle", args.item_code)

		for bundle_item in bundled_items.items:
			valuation_rate += flt(get_valuation_rate(bundle_item.item_code, batch_no=args.get('batch_no'),
				company=args.company, warehouse=out.get("warehouse"),
				from_date=args.get('po_cost_from_date'), to_date=args.get('po_cost_to_date'))\
					.get("valuation_rate") * bundle_item.qty)

		out.update({
			"valuation_rate": valuation_rate
		})

	else:
		out.update(get_valuation_rate(args.item_code, batch_no=args.get('batch_no'),
			company=args.company, warehouse=out.get("warehouse"),
			from_date=args.get('po_cost_from_date'), to_date=args.get('po_cost_to_date')))


def process_args(args):
	if isinstance(args, string_types):
		args = json.loads(args)

	args = frappe._dict(args)

	if not args.get("price_list"):
		args.price_list = args.get("selling_price_list") or args.get("buying_price_list")

	if args.barcode:
		args.item_code = get_item_code(barcode=args.barcode)
	elif not args.item_code and args.serial_no:
		args.item_code = get_item_code(serial_no=args.serial_no)

	set_transaction_type(args)
	return args


@frappe.whitelist()
def get_item_code(barcode=None, serial_no=None):
	if barcode:
		item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, fieldname=["parent"])
		if not item_code:
			frappe.throw(_("No Item with Barcode {0}").format(barcode))
	elif serial_no:
		item_code = frappe.db.get_value("Serial No", serial_no, "item_code")
		if not item_code:
			frappe.throw(_("No Item with Serial No {0}").format(serial_no))

	return item_code


def validate_item_details(args, item):
	if not args.company:
		throw(_("Please specify Company"))

	from erpnext.stock.doctype.item.item import validate_end_of_life
	validate_end_of_life(item.name, item.end_of_life, item.disabled)

	if args.transaction_type == "selling" and cint(item.has_variants):
		throw(_("Item {0} is a template, please select one of its variants").format(item.name))

	elif args.transaction_type == "buying" and args.doctype != "Material Request":
		if args.get("is_subcontracted") == "Yes" and item.is_sub_contracted_item != 1:
			throw(_("Item {0} must be a Sub-contracted Item").format(item.name))


def get_basic_details(args, item, overwrite_warehouse=True):
	"""
	:param args: {
			"item_code": "",
			"warehouse": None,
			"customer": "",
			"conversion_rate": 1.0,
			"selling_price_list": None,
			"price_list_currency": None,
			"price_list_uom_dependant": None,
			"plc_conversion_rate": 1.0,
			"doctype": "",
			"name": "",
			"supplier": None,
			"transaction_date": None,
			"conversion_rate": 1.0,
			"buying_price_list": None,
			"is_subcontracted": "Yes" / "No",
			"ignore_pricing_rule": 0/1
			"project": "",
			barcode: "",
			serial_no: "",
			currency: "",
			update_stock: "",
			price_list: "",
			company: "",
			order_type: "",
			is_pos: "",
			project: "",
			qty: "",
			stock_qty: "",
			conversion_factor: ""
		}
	:param item: `item_code` of Item object
	:return: frappe._dict
	"""

	if not item:
		item = frappe.get_cached_doc("Item", args.get("item_code"))

	if item.variant_of:
		item.update_template_tables()

	item_defaults = get_item_defaults(item.name, args.company)
	item_group_defaults = get_item_group_defaults(item.name, args.company)
	brand_defaults = get_brand_defaults(item.name, args.company)

	defaults = frappe._dict({
		'item_defaults': item_defaults,
		'item_group_defaults': item_group_defaults,
		'brand_defaults': brand_defaults
	})

	warehouse = get_item_warehouse(item, args, overwrite_warehouse, defaults)

	if args.get('doctype') == "Material Request" and not args.get('material_request_type'):
		args['material_request_type'] = frappe.db.get_value('Material Request',
			args.get('name'), 'material_request_type', cache=True)

	expense_account = None

	if args.get('doctype') == 'Purchase Invoice' and item.is_fixed_asset:
		from erpnext.assets.doctype.asset_category.asset_category import get_asset_category_account
		expense_account = get_asset_category_account(fieldname = "fixed_asset_account", item = args.item_code, company= args.company)

	#Set the UOM to the Default Sales UOM or Default Purchase UOM if configured in the Item Master
	if not args.get('uom'):
		if args.get('doctype') in sales_doctypes:
			args.uom = item.sales_uom if item.sales_uom else item.stock_uom
		elif (args.get('doctype') in ['Purchase Order', 'Purchase Receipt', 'Purchase Invoice']) or \
			(args.get('doctype') == 'Material Request' and args.get('material_request_type') == 'Purchase'):
			args.uom = item.purchase_uom if item.purchase_uom else item.stock_uom
		else:
			args.uom = item.stock_uom

	out = frappe._dict({
		"item_code": item.name,
		"item_name": item.item_name,
		"description": cstr(item.description).strip(),
		"image": cstr(item.image).strip(),
		"warehouse": warehouse,
		"income_account": get_default_income_account(args, item_defaults, item_group_defaults, brand_defaults),
		"expense_account": expense_account or get_default_expense_account(args, item_defaults, item_group_defaults, brand_defaults) ,
		"cost_center": get_default_cost_center(args, item_defaults, item_group_defaults, brand_defaults),
		'has_serial_no': item.has_serial_no,
		'has_batch_no': item.has_batch_no,
		"batch_no": args.get("batch_no"),
		"uom": args.uom,
		"min_order_qty": flt(item.min_order_qty) if args.doctype == "Material Request" else "",
		"qty": args.qty or 0.0,
		"stock_qty": args.qty or 0.0,
		"alt_uom_qty_editable": item.alt_uom_qty_editable,
		"boxes": args.qty or 0.0,
		"price_list_rate": 0.0,
		"base_price_list_rate": 0.0,
		"rate": 0.0,
		"base_rate": 0.0,
		"amount": 0.0,
		"base_amount": 0.0,
		"net_rate": 0.0,
		"net_amount": 0.0,
		"discount_percentage": 0.0,
		"supplier": get_default_supplier(args, item_defaults, item_group_defaults, brand_defaults),
		"update_stock": args.get("update_stock") if args.get('doctype') in ['Sales Invoice', 'Purchase Invoice'] else 0,
		"delivered_by_supplier": item.delivered_by_supplier if args.get("doctype") in ["Sales Order", "Sales Invoice"] else 0,
		"is_fixed_asset": item.is_fixed_asset,
		"weight_per_unit":item.weight_per_unit,
		"weight_uom":item.weight_uom,
		"volume_per_unit_cuft": item.volume_per_unit_cuft,
		"last_purchase_rate": item.last_purchase_rate if args.get("doctype") in ["Purchase Order"] else 0,
		"transaction_date": args.get("transaction_date")
	})

	if args.get('doctype') in sales_doctypes:
		out.qty_per_pallet = item.sale_pallets
	else:
		out.qty_per_pallet = item.purchase_pallets

	pallets_precision = get_field_precision(frappe.get_meta(args.get('doctype') + " Item").get_field('pallets'))
	out.pallets = flt(flt(out.qty) / flt(out.qty_per_pallet), pallets_precision) if out.qty_per_pallet else 0

	if item.get("enable_deferred_revenue") or item.get("enable_deferred_expense"):
		out.update(calculate_service_end_date(args, item))

	# calculate conversion factor
	if item.stock_uom == args.uom:
		out.conversion_factor = 1.0
	else:
		out.conversion_factor = args.conversion_factor or \
			get_conversion_factor(item.name, args.uom).get("conversion_factor")

	args.conversion_factor = out.conversion_factor
	out.stock_qty = out.qty * out.conversion_factor

	# calculate last purchase rate
	if args.get('doctype') in purchase_doctypes:
		from erpnext.buying.doctype.purchase_order.purchase_order import item_last_purchase_rate
		out.last_purchase_rate = item_last_purchase_rate(args.name, args.conversion_rate, item.name, out.conversion_factor)

	# if default specified in item is for another company, fetch from company
	for d in [
		["Account", "income_account", "default_income_account"],
		["Account", "expense_account", "default_expense_account"],
		["Cost Center", "cost_center", "cost_center"],
		["Warehouse", "warehouse", ""]]:
			if not out[d[1]]:
				out[d[1]] = frappe.get_cached_value('Company',  args.company,  d[2]) if d[2] else None

	for fieldname in ("item_name", "item_group", "barcodes", "brand", "stock_uom"):
		out[fieldname] = item.get(fieldname)

	if args.get("manufacturer"):
		part_no = get_item_manufacturer_part_no(args.get("item_code"), args.get("manufacturer"))
		if part_no:
			out["manufacturer_part_no"] = part_no
		else:
			out["manufacturer_part_no"] = None
			out["manufacturer"] = None
	else:
		data = frappe.get_value("Item", item.name,
			["default_item_manufacturer", "default_manufacturer_part_no"] , as_dict=1)

		if data:
			out.update({
				"manufacturer": data.default_item_manufacturer,
				"manufacturer_part_no": data.default_manufacturer_part_no
			})

	child_doctype = args.doctype + ' Item'
	meta = frappe.get_meta(child_doctype)
	if meta.get_field("barcode"):
		update_barcode_value(out)

	return out

def get_item_warehouse(item, args, overwrite_warehouse, defaults={}):
	if not defaults:
		defaults = frappe._dict({
			'item_defaults' : get_item_defaults(item.name, args.company),
			'item_group_defaults' : get_item_group_defaults(item.name, args.company),
			'brand_defaults' : get_brand_defaults(item.name, args.company)
		})

	if overwrite_warehouse or not args.warehouse:
		warehouse = (
			args.get("set_warehouse") or
			defaults.item_defaults.get("default_warehouse") or
			defaults.item_group_defaults.get("default_warehouse") or
			defaults.brand_defaults.get("default_warehouse") or
			args.get('warehouse')
		)

		if not warehouse:
			defaults = frappe.defaults.get_defaults() or {}
			warehouse_exists = frappe.db.exists("Warehouse", {
				'name': defaults.default_warehouse,
				'company': args.company
			})
			if defaults.get("default_warehouse") and warehouse_exists:
				warehouse = defaults.default_warehouse

	else:
		warehouse = args.get('warehouse')

	return warehouse

def update_barcode_value(out):
	from erpnext.accounts.doctype.sales_invoice.pos import get_barcode_data
	barcode_data = get_barcode_data([out])

	# If item has one barcode then update the value of the barcode field
	if barcode_data and len(barcode_data.get(out.item_code)) == 1:
		out['barcode'] = barcode_data.get(out.item_code)[0]

def get_alt_uom_qty(args, item, out):
	meta = frappe.get_meta((args.parenttype or args.doctype) + " Item")
	alt_uom_qty_precision = get_field_precision(meta.get_field("alt_uom_qty"))

	out.alt_uom = item.alt_uom
	out.stock_alt_uom_size = out.stock_alt_uom_size_std = item.alt_uom_size if out.alt_uom else 1.0 / out.conversion_factor
	out.alt_uom_size = out.alt_uom_size_std = out.stock_alt_uom_size * out.conversion_factor if out.alt_uom else 1.0
	out.alt_uom_qty = flt(out.stock_qty * out.stock_alt_uom_size, alt_uom_qty_precision) if out.alt_uom else out.qty

	rate = flt(out.rate or args.rate)
	out.alt_uom_rate = flt(rate / out.alt_uom_size_std)

	return out

@frappe.whitelist()
def get_item_tax_info(company, tax_category, item_codes):
	out = {}
	if isinstance(item_codes, string_types):
		item_codes = json.loads(item_codes)

	for item_code in item_codes:
		if not item_code or item_code in out:
			continue
		out[item_code] = {}
		item = frappe.get_cached_doc("Item", item_code)
		get_item_tax_template({"tax_category": tax_category}, item, out[item_code])
		out[item_code]["item_tax_rate"] = get_item_tax_map(company, out[item_code].get("item_tax_template"), as_json=True)

	return out

def get_item_tax_template(args, item, out):
	"""
		args = {
			"tax_category": None
			"item_tax_template": None
		}
	"""
	item_tax_template = args.get("item_tax_template")

	if not item_tax_template:
		item_tax_template = _get_item_tax_template(args, item.taxes, out)

	if not item_tax_template:
		item_group = item.item_group
		while item_group and not item_tax_template:
			item_group_doc = frappe.get_cached_doc("Item Group", item_group)
			item_tax_template = _get_item_tax_template(args, item_group_doc.taxes, out)
			item_group = item_group_doc.parent_item_group

def _get_item_tax_template(args, taxes, out={}, for_validate=False):
	taxes_with_validity = []
	taxes_with_no_validity = []

	for tax in taxes:
		if tax.valid_from:
			# In purchase Invoice first preference will be given to supplier invoice date
			# if supplier date is not present then posting date
			validation_date = args.get('transaction_date') or args.get('bill_date') or args.get('posting_date')

			if getdate(tax.valid_from) <= getdate(validation_date):
				taxes_with_validity.append(tax)
		else:
			taxes_with_no_validity.append(tax)

	if taxes_with_validity:
		taxes = sorted(taxes_with_validity, key = lambda i: i.valid_from, reverse=True)
	else:
		taxes = taxes_with_no_validity

	if for_validate:
		return [tax.item_tax_template for tax in taxes if (cstr(tax.tax_category) == cstr(args.get('tax_category')) \
			and (tax.item_tax_template not in taxes))]

	# all templates have validity and no template is valid
	if not taxes_with_validity and (not taxes_with_no_validity):
		return None

	for tax in taxes:
		if cstr(tax.tax_category) == cstr(args.get("tax_category")):
			out["item_tax_template"] = tax.item_tax_template
			return tax.item_tax_template
	return None

@frappe.whitelist()
def get_item_tax_map(company, item_tax_template, as_json=True):
	item_tax_map = {}
	if item_tax_template:
		template = frappe.get_cached_doc("Item Tax Template", item_tax_template)
		for d in template.taxes:
			if frappe.get_cached_value("Account", d.tax_type, "company") == company:
				item_tax_map[d.tax_type] = d.tax_rate

	return json.dumps(item_tax_map) if as_json else item_tax_map

@frappe.whitelist()
def calculate_service_end_date(args, item=None):
	args = process_args(args)
	if not item:
		item = frappe.get_cached_doc("Item", args.item_code)

	doctype = args.get("parenttype") or args.get("doctype")
	if doctype == "Sales Invoice":
		enable_deferred = "enable_deferred_revenue"
		no_of_months = "no_of_months"
		account = "deferred_revenue_account"
	else:
		enable_deferred = "enable_deferred_expense"
		no_of_months = "no_of_months_exp"
		account = "deferred_expense_account"

	service_start_date = args.service_start_date if args.service_start_date else args.transaction_date
	service_end_date = add_months(service_start_date, item.get(no_of_months))
	deferred_detail = {
		"service_start_date": service_start_date,
		"service_end_date": service_end_date
	}
	deferred_detail[enable_deferred] = item.get(enable_deferred)
	deferred_detail[account] = get_default_deferred_account(args, item, fieldname=account)

	return deferred_detail

def get_default_income_account(args, item, item_group, brand):
	return (item.get("income_account")
		or item_group.get("income_account")
		or brand.get("income_account")
		or args.income_account)

def get_default_expense_account(args, item, item_group, brand):
	return (item.get("expense_account")
		or item_group.get("expense_account")
		or brand.get("expense_account")
		or args.expense_account)

def get_default_deferred_account(args, item, fieldname=None):
	if item.get("enable_deferred_revenue") or item.get("enable_deferred_expense"):
		return (item.get(fieldname)
			or args.get(fieldname)
			or frappe.get_cached_value('Company',  args.company,  "default_"+fieldname))
	else:
		return None

def get_default_cost_center(args, item, item_group, brand, company=None):
	cost_center = None
	if args.get('project'):
		cost_center = frappe.db.get_value("Project", args.get("project"), "cost_center", cache=True)

	if not cost_center:
		if args.get('customer'):
			cost_center = item.get('selling_cost_center') or item_group.get('selling_cost_center') or brand.get('selling_cost_center')
		else:
			cost_center = item.get('buying_cost_center') or item_group.get('buying_cost_center') or brand.get('buying_cost_center')

	cost_center = cost_center or args.get("cost_center")

	if (company and cost_center
		and frappe.get_cached_value("Cost Center", cost_center, "company") != company):
		return None

	return cost_center

def get_default_supplier(args, item, item_group, brand):
	return (item.get("default_supplier")
		or item_group.get("default_supplier")
		or brand.get("default_supplier"))

def get_price_list_rate(args, item_doc, out):
	meta = frappe.get_meta(args.parenttype or args.doctype)

	if meta.get_field("currency") or args.get('currency'):
		pl_details = get_price_list_currency_and_exchange_rate(args)
		args.update(pl_details)
		if meta.get_field("currency"):
			validate_conversion_rate(args, meta)

		price_list_rate = get_price_list_rate_for(args, item_doc.name) or 0

		# variant
		if not price_list_rate and item_doc.variant_of:
			price_list_rate = get_price_list_rate_for(args, item_doc.variant_of)

		'''
		# insert in database
		if not price_list_rate:
			if args.price_list and args.rate:
				insert_item_price(args)
			return {}
		'''

		out.price_list_rate = flt(price_list_rate) * flt(args.plc_conversion_rate) \
			/ flt(args.conversion_rate)

		if not args.ignore_pricing_rule:
			out.discount_percentage = 0

			uom_margin = item_doc.get("uom_additional_cost", {"uom": args.uom, "company": args.company})
			if uom_margin and not pl_details.get("prices_independent_of_additional_uom_cost"):
				uom_margin = uom_margin[0]
				out.margin_type = "Amount"
				out.margin_rate_or_amount = uom_margin.margin_rate
			else:
				out.margin_type = ""
				out.margin_rate_or_amount = 0

			out.rate = out.price_list_rate + (out.margin_rate_or_amount if out.margin_type == "Amount" else 0)

		if not out.price_list_rate and args.transaction_type=="buying":
			from erpnext.stock.doctype.item.item import get_last_purchase_details
			out.update(get_last_purchase_details(item_doc.name,
				args.name, args.conversion_rate))

def insert_item_price(args):
	"""Insert Item Price if Price List and Price List Rate are specified and currency is the same"""
	if cint(args.is_return):
		return

	if frappe.db.get_value("Price List", args.price_list, "currency", cache=True) == args.currency \
		and cint(frappe.db.get_single_value("Stock Settings", "auto_insert_price_list_rate_if_missing")):
		if frappe.has_permission("Item Price", "write"):
			price_list_rate = (args.rate / args.get('conversion_factor')
				if args.get("conversion_factor") else args.rate)

			item_price = frappe.db.get_value('Item Price',
				{'item_code': args.item_code, 'price_list': args.price_list, 'currency': args.currency},
				['name', 'price_list_rate'], as_dict=1)

			if not item_price:
				item_price = frappe.get_doc({
					"doctype": "Item Price",
					"price_list": args.price_list,
					"item_code": args.item_code,
					"currency": args.currency,
					"price_list_rate": price_list_rate
				})
				item_price.insert()
				frappe.msgprint(_("Item Price added for {0} in Price List {1}").format(args.item_code,
					args.price_list), alert=True)

def get_item_price(args, item_code, ignore_party=False):
	"""
		Get name, price_list_rate from Item Price based on conditions
			Check if the desired qty is within the increment of the packing list.
		:param args: dict (or frappe._dict) with mandatory fields price_list, uom
			optional fields transaction_date, customer, supplier
		:param item_code: str, Item Doctype field item_code
	"""

	args['item_code'] = item_code

	conditions = """where item_code=%(item_code)s and price_list=%(price_list)s """
	order_by = "order by ifnull(valid_from, '2000-01-01') desc, uom desc"

	if not ignore_party:
		if args.get("customer"):
			conditions += " and customer=%(customer)s"
		elif args.get("supplier"):
			conditions += " and supplier=%(supplier)s"
		else:
			conditions += " and (customer is null or customer = '') and (supplier is null or supplier = '')"

	if args.get('transaction_date'):
		if args.get('period') == 'future':
			args['uom'] = args.get('uom', '')
			conditions += """ and ifnull(valid_from, '2000-01-01') > %(transaction_date)s and ifnull(uom, '') = %(uom)s"""
			order_by = "order by valid_from asc "
		else:
			conditions += """ and %(transaction_date)s between
				ifnull(valid_from, '2000-01-01') and ifnull(valid_upto, '2500-12-31')"""

	out = frappe.db.sql("""
		select name, price_list_rate, uom,
			ifnull(valid_from, '2000-01-01') as valid_from, ifnull(valid_upto, '2500-12-31') as valid_upto
		from `tabItem Price`
		{conditions} {order_by}
	""".format(conditions=conditions, order_by=order_by), args, as_list=1)

	matches_uom = list(filter(lambda d: cstr(d[2]) == cstr(args.get('uom')), out))
	if matches_uom:
		return matches_uom

	has_uom = list(filter(lambda d: d[2], out))
	if has_uom:
		# there are item prices with uom other than the current uom

		item = frappe.get_cached_doc("Item", item_code)
		item_uoms = [d.uom for d in item.uoms]

		convertible_prices = [d for d in has_uom if d[2] in item_uoms]
		if convertible_prices:
			has_uom_other_than_stock_uom = list(filter(lambda d: cstr(d[2]) != cstr(item.stock_uom), convertible_prices))
			if has_uom_other_than_stock_uom:
				return has_uom_other_than_stock_uom

		return convertible_prices

	return out

def get_price_list_rate_for(args, item_code):
	"""
		:param customer: link to Customer DocType
		:param supplier: link to Supplier DocType
		:param price_list: str (Standard Buying or Standard Selling)
		:param item_code: str, Item Doctype field item_code
		:param uom: str
		:param qty: Derised Qty
		:param transaction_date: Date of the price
	"""

	if frappe.get_cached_value("Stock Settings", None, "get_prices_based_on_date") == "Delivery Date":
		price_date = args.get('delivery_date') or args.get('transaction_date')
	else:
		price_date = args.get('transaction_date')

	item_price_args = {
			"item_code": item_code,
			"price_list": args.get('price_list'),
			"customer": args.get('customer'),
			"supplier": args.get('supplier'),
			"uom": args.get('uom'),
			"transaction_date": price_date,
	}

	item_price_data = None
	price_list_rate = get_item_price(item_price_args, item_code)
	if price_list_rate:
		desired_qty = args.get("qty")
		if desired_qty and check_packing_list(price_list_rate[0][0], desired_qty, item_code):
			item_price_data = price_list_rate
	else:
		for field in ["customer", "supplier"]:
			del item_price_args[field]

		general_price_list_rate = get_item_price(item_price_args, item_code,
			ignore_party=args.get("ignore_party"))

		if not general_price_list_rate and args.get("uom") != args.get("stock_uom"):
			item_price_args["uom"] = args.get("stock_uom")
			general_price_list_rate = get_item_price(item_price_args, item_code, ignore_party=args.get("ignore_party"))

		if general_price_list_rate:
			item_price_data = general_price_list_rate

	if item_price_data:
		stale_price_days = frappe.get_cached_value("Stock Settings", None, "stale_price_days")
		if args.doctype == "Purchase Order" and stale_price_days and not args.skip_old_price_alert:
			if args.get('transaction_date') and frappe.utils.date_diff(frappe.utils.getdate(args.get('transaction_date')),
					frappe.utils.getdate(item_price_data[0][3])) > stale_price_days:
				frappe.msgprint(
					"Price for Item {0} has not been updated for more than {1} days. Please make sure the price is still valid."
						.format(item_code, stale_price_days))

		if item_price_data[0][2] == args.get("uom"):
			return item_price_data[0][1]
		elif args.get('price_list_uom_dependant'):
			return convert_item_uom_for(value=item_price_data[0][1], item_code=item_code,
				from_uom=item_price_data[0][2], to_uom=args.get("uom"), conversion_factor=args.get("conversion_factor"))
		else:
			return item_price_data[0][1]

def check_packing_list(price_list_rate_name, desired_qty, item_code):
	"""
		Check if the desired qty is within the increment of the packing list.
		:param price_list_rate_name: Name of Item Price
		:param desired_qty: Desired Qt
		:param item_code: str, Item Doctype field item_code
		:param qty: Desired Qt
	"""

	flag = True
	item_price = frappe.get_doc("Item Price", price_list_rate_name)
	if item_price.packing_unit:
		packing_increment = desired_qty % item_price.packing_unit

		if packing_increment != 0:
			flag = False

	return flag

def validate_conversion_rate(args, meta):
	from erpnext.controllers.accounts_controller import validate_conversion_rate

	if (not args.conversion_rate
		and args.currency==frappe.get_cached_value('Company',  args.company,  "default_currency")):
		args.conversion_rate = 1.0

	# validate currency conversion rate
	validate_conversion_rate(args.currency, args.conversion_rate,
		meta.get_label("conversion_rate"), args.company)

	args.conversion_rate = flt(args.conversion_rate,
		get_field_precision(meta.get_field("conversion_rate"),
			frappe._dict({"fields": args})))

	if args.price_list:
		if (not args.plc_conversion_rate
			and args.price_list_currency==frappe.db.get_value("Price List", args.price_list, "currency", cache=True)):
			args.plc_conversion_rate = 1.0

		# validate price list currency conversion rate
		if not args.get("price_list_currency"):
			throw(_("Price List Currency not selected"))
		else:
			validate_conversion_rate(args.price_list_currency, args.plc_conversion_rate,
				meta.get_label("plc_conversion_rate"), args.company)

			if meta.get_field("plc_conversion_rate"):
				args.plc_conversion_rate = flt(args.plc_conversion_rate,
					get_field_precision(meta.get_field("plc_conversion_rate"),
					frappe._dict({"fields": args})))

def get_party_item_code(args, item_doc, out):
	if args.transaction_type=="selling" and args.customer:
		out.customer_item_code = None

		if args.quotation_to and args.quotation_to != 'Customer':
			return

		customer_item_code = item_doc.get("customer_items", {"customer_name": args.customer})

		if customer_item_code:
			out.customer_item_code = customer_item_code[0].ref_code
			out.item_name = customer_item_code[0].item_name or out.item_name
		else:
			customer_group = frappe.get_cached_value("Customer", args.customer, "customer_group")
			customer_group_item_code = item_doc.get("customer_items", {"customer_group": customer_group})
			if customer_group_item_code and not customer_group_item_code[0].customer_name:
				out.customer_item_code = customer_group_item_code[0].ref_code
				out.item_name = customer_group_item_code[0].item_name or out.item_name

	if args.transaction_type=="buying" and args.supplier:
		item_supplier = item_doc.get("supplier_items", {"supplier": args.supplier})
		out.supplier_part_no = item_supplier[0].supplier_part_no if item_supplier else None

def get_pos_profile_item_details(company, args, pos_profile=None, update_data=False):
	res = frappe._dict()

	if not frappe.flags.pos_profile and not pos_profile:
		pos_profile = frappe.flags.pos_profile = get_pos_profile(company, args.get('pos_profile'))

	if pos_profile:
		for fieldname in ("income_account", "cost_center", "warehouse", "expense_account"):
			if (not args.get(fieldname) or update_data) and pos_profile.get(fieldname):
				res[fieldname] = pos_profile.get(fieldname)

		if res.get("warehouse"):
			res.actual_qty = get_bin_details(args.item_code,
				res.warehouse).get("actual_qty")

	return res

@frappe.whitelist()
def get_pos_profile(company, pos_profile=None, user=None):
	if pos_profile: return frappe.get_cached_doc('POS Profile', pos_profile)

	if not user:
		user = frappe.session['user']

	condition = "pfu.user = %(user)s AND pfu.default=1"
	if user and company:
		condition = "pfu.user = %(user)s AND pf.company = %(company)s AND pfu.default=1"

	pos_profile = frappe.db.sql("""SELECT pf.*
		FROM
			`tabPOS Profile` pf LEFT JOIN `tabPOS Profile User` pfu
		ON
				pf.name = pfu.parent
		WHERE
			{cond} AND pf.disabled = 0
	""".format(cond = condition), {
		'user': user,
		'company': company
	}, as_dict=1)

	if not pos_profile and company:
		pos_profile = frappe.db.sql("""SELECT pf.*
			FROM
				`tabPOS Profile` pf LEFT JOIN `tabPOS Profile User` pfu
			ON
					pf.name = pfu.parent
			WHERE
				pf.company = %(company)s AND pf.disabled = 0
		""", {
			'company': company
		}, as_dict=1)

	return pos_profile and pos_profile[0] or None

def get_serial_nos_by_fifo(args, sales_order=None):
	if frappe.db.get_single_value("Stock Settings", "automatically_set_serial_nos_based_on_fifo"):
		return "\n".join(frappe.db.sql_list("""select name from `tabSerial No`
			where item_code=%(item_code)s and warehouse=%(warehouse)s and
			sales_order=IF(%(sales_order)s IS NULL, sales_order, %(sales_order)s)
			order by timestamp(purchase_date, purchase_time)
			asc limit %(qty)s""",
			{
				"item_code": args.item_code,
				"warehouse": args.warehouse,
				"qty": abs(cint(args.stock_qty)),
				"sales_order": sales_order
			}))

def get_serial_no_batchwise(args, sales_order=None):
	if frappe.db.get_single_value("Stock Settings", "automatically_set_serial_nos_based_on_fifo"):
		return "\n".join(frappe.db.sql_list("""select name from `tabSerial No`
			where item_code=%(item_code)s and warehouse=%(warehouse)s and
			sales_order=IF(%(sales_order)s IS NULL, sales_order, %(sales_order)s)
			and batch_no=IF(%(batch_no)s IS NULL, batch_no, %(batch_no)s) order
			by timestamp(purchase_date, purchase_time) asc limit %(qty)s""", {
				"item_code": args.item_code,
				"warehouse": args.warehouse,
				"batch_no": args.batch_no,
				"qty": abs(cint(args.stock_qty)),
				"sales_order": sales_order
			}))

@frappe.whitelist()
def get_conversion_factor(item_code, uom):
	filters = {"parent": item_code, "uom": uom}
	'''variant_of = frappe.db.get_value("Item", item_code, "variant_of", cache=True)
	if variant_of:
		filters["parent"] = ("in", (item_code, variant_of))'''
	conversion_factor = frappe.db.get_value("UOM Conversion Detail",
		filters, "conversion_factor")
	if not conversion_factor:
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
		conversion_factor = get_uom_conv_factor(uom, stock_uom)
	return {"conversion_factor": conversion_factor or 1.0}

@frappe.whitelist()
def get_projected_qty(item_code, warehouse):
	return {"projected_qty": frappe.db.get_value("Bin",
		{"item_code": item_code, "warehouse": warehouse}, "projected_qty")}

@frappe.whitelist()
def get_bin_details(item_code, warehouse):
	return frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse},
		["projected_qty", "actual_qty", "reserved_qty"], as_dict=True, cache=True) \
			or {"projected_qty": 0, "actual_qty": 0, "reserved_qty": 0}

@frappe.whitelist()
def get_serial_no_details(item_code, warehouse, stock_qty, serial_no):
	args = frappe._dict({"item_code":item_code, "warehouse":warehouse, "stock_qty":stock_qty, "serial_no":serial_no})
	serial_no = get_serial_no(args)
	return {'serial_no': serial_no}

@frappe.whitelist()
def get_bin_details_and_serial_nos(item_code, warehouse, has_batch_no=None, stock_qty=None, serial_no=None):
	bin_details_and_serial_nos = {}
	bin_details_and_serial_nos.update(get_bin_details(item_code, warehouse))
	if flt(stock_qty) > 0:
		if has_batch_no:
			args = frappe._dict({"item_code":item_code, "warehouse":warehouse, "stock_qty":stock_qty})
			serial_no = get_serial_no(args)
			bin_details_and_serial_nos.update({'serial_no': serial_no})
			return bin_details_and_serial_nos

		bin_details_and_serial_nos.update(get_serial_no_details(item_code, warehouse, stock_qty, serial_no))
	return bin_details_and_serial_nos

@frappe.whitelist()
def get_batch_qty_and_serial_no(batch_no, stock_qty, warehouse, item_code, has_serial_no):
	batch_qty_and_serial_no = {}
	batch_qty_and_serial_no.update(get_batch_qty(batch_no, warehouse, item_code))

	if (flt(batch_qty_and_serial_no.get('actual_batch_qty')) >= flt(stock_qty)) and has_serial_no:
		args = frappe._dict({"item_code":item_code, "warehouse":warehouse, "stock_qty":stock_qty, "batch_no":batch_no})
		serial_no = get_serial_no(args)
		batch_qty_and_serial_no.update({'serial_no': serial_no})
	return batch_qty_and_serial_no

@frappe.whitelist()
def get_batch_qty(batch_no, warehouse, item_code):
	from erpnext.stock.doctype.batch import batch
	if batch_no:
		return {'actual_batch_qty': batch.get_batch_qty(batch_no, warehouse)}

@frappe.whitelist()
def apply_price_list(args, as_doc=False):
	"""Apply pricelist on a document-like dict object and return as
	{'parent': dict, 'children': list}

	:param args: See below
	:param as_doc: Updates value in the passed dict

		args = {
			"doctype": "",
			"name": "",
			"items": [{"doctype": "", "name": "", "item_code": "", "brand": "", "item_group": ""}, ...],
			"conversion_rate": 1.0,
			"selling_price_list": None,
			"price_list_currency": None,
			"price_list_uom_dependant": None,
			"plc_conversion_rate": 1.0,
			"doctype": "",
			"name": "",
			"supplier": None,
			"transaction_date": None,
			"conversion_rate": 1.0,
			"buying_price_list": None,
			"ignore_pricing_rule": 0/1
		}
	"""
	args = process_args(args)

	parent = get_price_list_currency_and_exchange_rate(args)
	children = []

	if "items" in args:
		item_list = args.get("items")
		args.update(parent)

		for item in item_list:
			args_copy = frappe._dict(args.copy())
			args_copy.update(item)
			item_details = apply_price_list_on_item(args_copy) if not args_copy.ignore_pricing_rule else frappe._dict({})
			children.append(item_details)

	if as_doc:
		args.price_list_currency = parent.price_list_currency,
		args.plc_conversion_rate = parent.plc_conversion_rate
		if args.get('items'):
			for i, item in enumerate(args.get('items')):
				for fieldname in children[i]:
					# if the field exists in the original doc
					# update the value
					if fieldname in item and fieldname not in ("name", "doctype"):
						item[fieldname] = children[i][fieldname]
		return args
	else:
		return {
			"parent": parent,
			"children": children
		}

def apply_price_list_on_item(args):
	item_details = frappe._dict()
	item_doc = frappe.get_cached_doc("Item", args.item_code)
	get_price_list_rate(args, item_doc, item_details)

	item_details.update(get_pricing_rule_for_item(args, item_details.price_list_rate))

	return item_details

def get_price_list_currency_and_exchange_rate(args):
	if not args.price_list:
		return {}

	if args.doctype in ['Quotation', 'Sales Order', 'Delivery Note', 'Sales Invoice']:
		args.update({"exchange_rate": "for_selling"})
	elif args.doctype in ['Purchase Order', 'Purchase Receipt', 'Purchase Invoice']:
		args.update({"exchange_rate": "for_buying"})

	price_list_details = get_price_list_details(args.price_list)

	price_list_currency = price_list_details.get("currency")
	price_list_uom_dependant = not price_list_details.get("price_not_uom_dependant")
	prices_independent_of_additional_uom_cost = price_list_details.get("prices_independent_of_additional_uom_cost")

	plc_conversion_rate = args.plc_conversion_rate
	company_currency = get_company_currency(args.company)

	if (not plc_conversion_rate) or (price_list_currency and args.price_list_currency \
		and price_list_currency != args.price_list_currency):
			# cksgb 19/09/2016: added args.transaction_date as posting_date argument for get_exchange_rate
			plc_conversion_rate = get_exchange_rate(price_list_currency, company_currency,
				args.transaction_date, args.exchange_rate) or plc_conversion_rate

	return frappe._dict({
		"price_list_currency": price_list_currency,
		"price_list_uom_dependant": price_list_uom_dependant,
		"plc_conversion_rate": plc_conversion_rate,
		"prices_independent_of_additional_uom_cost": prices_independent_of_additional_uom_cost
	})

@frappe.whitelist()
def get_default_bom(item_code=None):
	if item_code:
		bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_default": 1, "is_active": 1, "item": item_code})
		if bom:
			return bom

@frappe.whitelist()
def get_valuation_rate(item_code, company=None, warehouse=None, from_date=None, to_date=None, batch_no=None):
	empty = {"valuation_rate": 0.0}

	from erpnext.accounts.report.gross_profit.gross_profit import get_sales_item_batch_incoming_rate
	item = frappe.get_cached_doc("Item", item_code)

	if item.get("is_stock_item"):
		args = [{'item_code': item_code, 'batch_no': batch_no}]
		incoming_rate_data = get_sales_item_batch_incoming_rate(args, from_date=from_date, to_date=to_date)
		batch_or_item = 'batch_incoming_rate' if batch_no else 'item_incoming_rate'
		return {"valuation_rate": flt(incoming_rate_data[batch_or_item].get(batch_no or item_code))}

	elif not item.get("is_stock_item"):
		valuation_rate = frappe.db.sql("""select sum(base_net_amount) / sum(stock_qty)
			from `tabPurchase Invoice Item`
			where item_code = %s and docstatus=1""", item_code)

		if valuation_rate:
			return {"valuation_rate": valuation_rate[0][0] or 0.0}
	else:
		return empty

def get_gross_profit(out):
	if out.valuation_rate:
		out.update({
			"gross_profit": ((out.base_rate - out.valuation_rate) * out.stock_qty)
		})

	return out

@frappe.whitelist()
def get_serial_no(args, serial_nos=None, sales_order=None):
	serial_no = None
	if isinstance(args, string_types):
		args = json.loads(args)
		args = frappe._dict(args)
	if args.get('doctype') == 'Sales Invoice' and not args.get('update_stock'):
		return ""
	if args.get('warehouse') and args.get('stock_qty') and args.get('item_code'):
		has_serial_no = frappe.get_value('Item', {'item_code': args.item_code}, "has_serial_no")
		if args.get('batch_no') and has_serial_no == 1:
			return get_serial_no_batchwise(args, sales_order)
		elif has_serial_no == 1:
			args = json.dumps({"item_code": args.get('item_code'),"warehouse": args.get('warehouse'),"stock_qty": args.get('stock_qty')})
			args = process_args(args)
			serial_no = get_serial_nos_by_fifo(args, sales_order)

	if not serial_no and serial_nos:
		# For POS
		serial_no = serial_nos

	return serial_no


def update_party_blanket_order(args, out):
	blanket_order_details = get_blanket_order_details(args)
	if blanket_order_details:
		out.update(blanket_order_details)

@frappe.whitelist()
def get_blanket_order_details(args):
	if isinstance(args, string_types):
		args = frappe._dict(json.loads(args))

	blanket_order_details = None
	condition = ''
	if args.item_code:
		if args.customer and args.doctype == "Sales Order":
			condition = ' and bo.customer=%(customer)s'
		elif args.supplier and args.doctype == "Purchase Order":
			condition = ' and bo.supplier=%(supplier)s'
		if args.blanket_order:
			condition += ' and bo.name =%(blanket_order)s'
		if args.transaction_date:
			condition += ' and bo.to_date>=%(transaction_date)s'

		blanket_order_details = frappe.db.sql('''
				select boi.rate as blanket_order_rate, bo.name as blanket_order
				from `tabBlanket Order` bo, `tabBlanket Order Item` boi
				where bo.company=%(company)s and boi.item_code=%(item_code)s
					and bo.docstatus=1 and bo.name = boi.parent {0}
			'''.format(condition), args, as_dict=True)

		blanket_order_details = blanket_order_details[0] if blanket_order_details else ''
	return blanket_order_details

def get_so_reservation_for_item(args):
	reserved_so = None
	if args.get('against_sales_order'):
		if get_reserved_qty_for_so(args.get('against_sales_order'), args.get('item_code')):
			reserved_so = args.get('against_sales_order')
	elif args.get('against_sales_invoice'):
		sales_order = frappe.db.sql("""select sales_order from `tabSales Invoice Item` where
		parent=%s and item_code=%s""", (args.get('against_sales_invoice'), args.get('item_code')))
		if sales_order and sales_order[0]:
			if get_reserved_qty_for_so(sales_order[0][0], args.get('item_code')):
				reserved_so = sales_order[0]
	elif args.get("sales_order"):
		if get_reserved_qty_for_so(args.get('sales_order'), args.get('item_code')):
			reserved_so = args.get('sales_order')
	return reserved_so

def get_reserved_qty_for_so(sales_order, item_code):
	reserved_qty = frappe.db.sql("""select sum(qty) from `tabSales Order Item`
	where parent=%s and item_code=%s and ensure_delivery_based_on_produced_serial_no=1
	""", (sales_order, item_code))
	if reserved_qty and reserved_qty[0][0]:
		return reserved_qty[0][0]
	else:
		return 0

@frappe.whitelist()
def validate_price_change(item_code, price_list_rate, rate):
	price_list_rate = flt(price_list_rate)
	rate = flt(rate)

	if not price_list_rate:
		return 0

	change_rate = flt(frappe.get_cached_value("Item", item_code, 'change_rate'))

	allowed_change = abs(price_list_rate * change_rate / 100)

	if rate < price_list_rate:
		difference = price_list_rate - rate
		return cint(difference > allowed_change)
	else:
		return 0

@frappe.whitelist()
def get_item_custom_projected_qty(date, item_codes, exclude_so=None):
	from_date = frappe.utils.getdate(date)
	to_date = frappe.utils.add_days(from_date, 4)

	if isinstance(item_codes, string_types):
		item_codes = json.loads(item_codes)

	po_data = frappe.db.sql("""
		select
			i.item_code, po.schedule_date as date,
			sum((i.qty - ifnull(i.received_qty, 0)) * i.conversion_factor) as qty
		from `tabPurchase Order Item` i
		inner join `tabPurchase Order` po on po.name = i.parent
		where po.docstatus < 2 and po.status != 'Closed' and ifnull(i.received_qty, 0) < ifnull(i.qty, 0)
			and po.schedule_date between %s and %s and i.item_code in ({0})
		group by i.item_code, po.schedule_date
	""".format(", ".join(['%s']*len(item_codes))), [from_date, to_date] + item_codes, as_dict=1)

	exclude_so_cond = " and so.name != {0}".format(frappe.db.escape(exclude_so)) if exclude_so else ""

	so_data = frappe.db.sql("""
		select
			i.item_code, so.delivery_date as date,
			sum((i.qty - ifnull(i.delivered_qty, 0)) * i.conversion_factor) as qty
		from `tabSales Order Item` i
		inner join `tabSales Order` so on so.name = i.parent
		where so.docstatus < 2 and so.status != 'Closed' and ifnull(i.delivered_qty, 0) < ifnull(i.qty, 0)
			and so.delivery_date between %s and %s and i.item_code in ({0}) {1}
		group by i.item_code, so.delivery_date
	""".format(", ".join(['%s'] * len(item_codes)), exclude_so_cond), [from_date, to_date] + item_codes, as_dict=1)

	sinv_data = frappe.db.sql("""
		select
			i.item_code, sinv.delivery_date as date,
			sum(i.stock_qty) as qty
		from `tabSales Invoice Item` i
		inner join `tabSales Invoice` sinv on sinv.name = i.parent
		where sinv.docstatus = 0 and ifnull(i.sales_order, '') = ''
			and sinv.delivery_date between %s and %s and i.item_code in ({0})
		group by i.item_code, sinv.delivery_date
	""".format(", ".join(['%s'] * len(item_codes))), [from_date, to_date] + item_codes, as_dict=1)

	bin_data = frappe.db.sql("""
		select item_code, sum(actual_qty) as actual_qty, sum(projected_qty) as projected_qty
		from tabBin
		where item_code in ({0})
		group by item_code
	""".format(", ".join(['%s']*len(item_codes))), item_codes, as_dict=1)

	out = {}

	template = {
		"po_day_1": 0, "po_day_2": 0, "po_day_3": 0, "po_day_4": 0, "po_day_5": 0,
		"so_day_1": 0, "so_day_2": 0, "so_day_3": 0, "so_day_4": 0, "so_day_5": 0,
		"actual_qty": 0, "projected_qty": 0
	}

	for d in po_data:
		out.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, from_date)
		out[d.item_code]['po_day_' + str(i+1)] = d.qty

	for d in so_data:
		out.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, from_date)
		out[d.item_code].setdefault('so_day_' + str(i+1), 0)
		out[d.item_code]['so_day_' + str(i+1)] += d.qty

	for d in sinv_data:
		out.setdefault(d.item_code, template.copy())
		i = frappe.utils.date_diff(d.date, from_date)
		out[d.item_code].setdefault('so_day_' + str(i+1), 0)
		out[d.item_code]['so_day_' + str(i+1)] += d.qty

	for d in bin_data:
		out.setdefault(d.item_code, template.copy())
		out[d.item_code]['actual_qty'] = d.actual_qty

	for item_code, d in iteritems(out):
		d['projected_qty'] = d['actual_qty']
		for i in range(2):
			d['projected_qty'] += d['po_day_' + str(i+1)]
			d['projected_qty'] -= d['so_day_' + str(i+1)]

	return out