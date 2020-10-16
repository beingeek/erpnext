// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt


frappe.require("assets/erpnext/js/financial_statements.js", function() {
	frappe.query_reports["Profit and Loss Statement"] = $.extend({},
		erpnext.financial_statements);

	erpnext.utils.add_dimensions('Profit and Loss Statement', 10);

	frappe.query_reports["Profit and Loss Statement"]["filters"].push(
		{
			"fieldname": "project",
			"label": __("Project"),
			"fieldtype": "MultiSelectList",
			get_data: function(txt) {
				return frappe.db.get_link_options('Project', txt);
			}
		},
		{
			"fieldname": "sales_person",
			"label": __("Sales Person"),
			"fieldtype": "Link",
			"options": "Sales Person"
		},
		{
			"fieldname": "group_by",
			"label": __("Group By"),
			"fieldtype": "Select",
			"default": "Ungrouped",
			"options": ['Ungrouped', 'Sales Person']
		},
		{
			"fieldname": "start_month",
			"label": __("Start Month"),
			"fieldtype": "Select",
			"default": "January",
			"options": ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
		},
		{
			"fieldname": "end_month",
			"label": __("End Month"),
			"fieldtype": "Select",
			"default": "December",
			"options": ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
		},
		{
			"fieldname": "accumulated_values",
			"label": __("Accumulated Values"),
			"fieldtype": "Check"
		},
		{
			"fieldname": "include_default_book_entries",
			"label": __("Include Default Book Entries"),
			"fieldtype": "Check",
			"default": 1
		}
	);
});
