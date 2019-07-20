// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Bank Reconciliation Statement"] = {
	"filters": [
		{
			"fieldname":"account",
			"label": __("Bank Account"),
			"fieldtype": "Link",
			"options": "Account",
			"default": frappe.defaults.get_user_default("Company")? 
				locals[":Company"][frappe.defaults.get_user_default("Company")]["default_bank_account"]: "",
			"reqd": 1,
			"get_query": function() {
				return {
					"query": "erpnext.controllers.queries.get_account_list",
					"filters": [
						['Account', 'account_type', 'in', 'Bank, Cash'],
						['Account', 'is_group', '=', 0],
					]
				}
			}
		},
		{
			"fieldname":"report_date",
			"label": __("Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname":"include_pos_transactions",
			"label": __("Include POS Transactions"),
			"fieldtype": "Check"
		},
	],
	formatter: function(value, row, column, data, default_formatter) {
		var style = {};
		var link;

		if (column.fieldname == 'payment_entry' && value == __("'Outstanding Cheques and Deposits to clear'")) {
			var date = frappe.query_report.get_filter_value("report_date");
			var account = frappe.query_report.get_filter_value("account");
			link = "desk#Form/Bank Reconciliation/Bank Reconciliation?date=" + date + "&account=" + account;
		}

		return default_formatter(value, row, column, data, {css: style, link_href: link, link_target: "_blank"});
	},
}