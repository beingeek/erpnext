from __future__ import unicode_literals
import frappe

from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import getdate, validate_email_add, today, add_years,add_days,format_datetime
from datetime import datetime
from frappe.model.naming import make_autoname
from frappe import throw, _, scrub
import frappe.permissions
from frappe.model.document import Document
import json
import collections
from erpnext.controllers.sales_and_purchase_return import make_return_doc
# import urllib
# import urllib2

@frappe.whitelist()
def test():
	return "test"

@frappe.whitelist()
def submitLcv(doc):
	doc = frappe.get_doc(json.loads(doc))
	set_local_name(doc)
	doc.docstatus=1
	dt=doc.submit();
	if dt:
		return "In"
	else:
		return "out"

def set_local_name(doc):
	def _set_local_name(d):
		if doc.get('__islocal') or d.get('__islocal'):
			d.localname = d.name
			d.name = None

	_set_local_name(doc)
	for child in doc.get_all_children():
		_set_local_name(child)

	if doc.get("__newname"):
		doc.name = doc.get("__newname")

@frappe.whitelist()
def makeReturnReceipt(doc,method):
	make_return_doc("Purchase Receipt",doc)


@frappe.whitelist()
def getItemtaxes(item_code):
	item=frappe.get_doc("Item",item_code)
	return dict(([d.tax_type, d.tax_rate] for d in item.get("taxes")))

@frappe.whitelist()
def validateReference(ref_no,party):
	data=frappe.db.sql("""select mjea.idx,mje.name from `tabMaster Journal Entry` as mje inner join `tabMaster Journal Entry Account` as mjea on mje.name=mjea.parent where mjea.reference_name=%s and mjea.party=%s and mje.docstatus=1""",(ref_no,party),as_dict=1)
	#return len(data)
	if len(data)>=1:
		return data[0]
	else:
		return "False"
		
def get_items_from_purchase_receipts(doc):
		doc.set("items", [])
		for pr in doc.get("purchase_receipts"):
			if pr.receipt_document_type and pr.receipt_document:
				pr_items = frappe.db.sql("""select pr_item.item_code, pr_item.item_name, pr_item.description,
					pr_item.qty, pr_item.base_rate, pr_item.base_amount, pr_item.name, 						pr_item.cost_center,pr_item.gross_weight_lbs
					from `tab{doctype} Item` pr_item where parent = %s
					and exists(select name from tabItem where name = pr_item.item_code and is_stock_item = 1)
					""".format(doctype=pr.receipt_document_type), pr.receipt_document, as_dict=True)

				for d in pr_items:
					item = doc.append("items")
					item.item_code = d.item_code
					item.description = d.item_name
					item.qty = d.qty
					item.rate = d.base_rate
					item.cost_center = d.cost_center or \
						erpnext.get_default_cost_center(doc.company)
					item.amount = d.base_amount
					item.receipt_document_type = pr.receipt_document_type
					item.receipt_document = pr.receipt_document
					item.purchase_receipt_item = d.name
					sitem = frappe.get_doc("Item", d.item_code)
					if not d.gross_weight_lbs:
						item.gross_weight=float(d.qty)*float(sitem.gross_weight)
					else:
						item.gross_weight=float(d.qty)*float(d.gross_weight_lbs)

@frappe.whitelist()
def paymentReferenceDate(row,reference_doctype,reference_name):
	result_list2=[]
	d={}
	d["row"]=row
	doc = frappe.get_doc(reference_doctype, reference_name)
	d["cheque_no"] = ""
	d["due_date"] = doc.get("due_date") or doc.get("posting_date")
	if reference_doctype == "Journal Entry":
		d["cheque_no"] = doc.cheque_no
		d["due_date"] = doc.posting_date
	elif reference_doctype == "Purchase Invoice":
		d["cheque_no"] = doc.bill_no
		d["due_date"] = doc.received_date
	elif reference_doctype == "Sales Invoice":
		d["due_date"] = doc.posting_date
	elif reference_doctype == "Landed Cost Voucher":
		d["cheque_no"] = ", ".join([tax.remarks for tax in doc.taxes if tax.remarks])
	
	result_list2.append(d)
	return result_list2
