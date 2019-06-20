// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Purchase Order Items To Be Received"] = {
	"filters": [
		{
			"fieldname":"from_date",
			"label": __("From Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname":"to_date",
			"label": __("To Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname":"item_code",
			"label": __("Item Code"),
			"fieldtype": "Link",
			"options": "Item"
		}
	]
}
