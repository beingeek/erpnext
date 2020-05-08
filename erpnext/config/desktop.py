# coding=utf-8

from __future__ import unicode_literals
from frappe import _

def get_data():
	colors = {
		"Stock": "#f39c12",
		"Selling": "#1abc9c",
		"Buying": "#c0392b",
		"HR": "#2ecc71",
		"Projects": "#8e44ad",
		"Support": "#2c3e50",
		"Accounts": "#3498db",
		"Tools": "#FFF5A7"
	}

	return [
		{"module_name": "Sales Order", "_doctype": "Sales Order", "type": "list",
			"color": colors["Selling"], "icon": "fa fa-file-text"},
		{"module_name": "Sales Invoice", "_doctype": "Sales Invoice", "type": "list",
			"color": colors["Accounts"], "icon": "fa fa-file-text"},
		{"module_name": "Qty Adjust", "_report": "Qty Adjust", "color": "grey", "type": "query-report",
			"link": "query-report/Qty Adjust", "label": _("Qty Adjust")},
		{"module_name": "Qty Adjust Log Summary", "_report": "Qty Adjust Log Summary", "color": "grey", "type": "query-report",
			"link": "query-report/Qty Adjust Log Summary", "label": _("Qty Adjust Log Summary")},

		{"module_name": "Price List", "_report": "Price List", "color": colors["Stock"], "type": "list",
			"link": "query-report/Price List", "label": _("Price List")},

		{"module_name": "Sales Order Route Map", "type": "link", "link": "/sales_order",
			"force_show": 1, "label": _("Sales Order Route Map")},
		{"module_name": "Customer", "_doctype": "Customer", "color": colors["Selling"], "icon": "octicon octicon-tag",
			"type": "list", "link": "List/Customer"},

		{"module_name": "Purchase Order", "_doctype": "Purchase Order", "type": "list",
			"color": colors["Buying"], "icon": "fa fa-file-text"},
		{"module_name": "Purchase Receipt", "_doctype": "Purchase Receipt", "type": "list",
			"color": colors["Stock"], "icon": "fa fa-truck"},
		{"module_name": "Landed Cost Voucher", "_doctype": "Landed Cost Voucher", "type": "list",
			"color": colors["Stock"], "icon": "fa fa-plane"},
		{"module_name": "Purchase Invoice", "_doctype": "Purchase Invoice", "type": "list",
			"color": colors["Accounts"], "icon": "fa fa-file-text"},
		{"module_name": "Supplier", "_doctype": "Supplier", "color": colors["Buying"], "icon": "octicon octicon-briefcase",
			"type": "list", "link": "List/Supplier"},

		{"module_name": "Item", "_doctype": "Item", "color": colors["Stock"], "icon": "octicon octicon-package",
			"type": "list", "link": "List/Item"},
		{"module_name": "Stock Ledger", "_report": "Stock Ledger", "type": "query-report", "link": "query-report/Stock Ledger",
			"color": colors["Stock"], "icon": "fa fa-exchange"},
		{"module_name": "Stock Reconciliation", "_doctype": "Stock Reconciliation", "type": "list",
			"color": colors["Stock"], "icon": "fa fa-files-o"},
		{"module_name": "BOM", "_doctype": "BOM", "color": colors["Stock"], "icon": "octicon octicon-package",
			"type": "list", "link": "List/BOM"},

		{"module_name": "Leaderboard", "color": "#589494", "icon": "octicon octicon-graph", "type": "page",
			"link": "leaderboard", "label": _("Leaderboard")},

		{"module_name": "Account", "_doctype": "Account", "type": "link", "link": "Tree/Account", "label": _("Chart of Accounts"),
			"color": colors["Accounts"], "icon": "fa fa-sitemap"},
		{"module_name": "Profit and Loss Statement", "_doctype": "Account", "color": colors["Accounts"], "icon": "octicon octicon-repo",
			"type": "query-report", "link": "query-report/Profit and Loss Statement"},
		{"module_name": "Master Journal Entry", "_doctype": "Master Journal Entry", "type": "list",
			"color": colors["Accounts"], "icon": "fa fa-book"},
		{"module_name": "Payment Entry", "_doctype": "Payment Entry", "type": "list",
			"color": colors["Accounts"], "icon": "fa fa-money"},
		{"module_name": "Accounts Payable Summary", "_report": "Accounts Payable Summary", "type": "query-report",
			"link": "query-report/Accounts Payable Summary", "color": colors["Buying"], "icon": "fa fa-tasks"},
		{"module_name": "Accounts Receivable Summary", "_report": "Accounts Receivable Summary", "type": "query-report",
			"link": "query-report/Accounts Receivable Summary", "color": colors["Selling"], "icon": "fa fa-tasks"},
		{"module_name": "Trial Balance", "_report": "Trial Balance", "type": "query-report", "link": "query-report/Trial Balance",
			"color": colors["Accounts"], "icon": "fa fa-balance-scale"},

		{"module_name": "Purchase Analytics", "_report": "Purchase Analytics", "type": "query-report", "link": "query-report/Purchase Analytics",
			"color": colors["Buying"], "icon": "fa fa-line-chart"},
		{"module_name": "Sales Analytics", "_report": "Sales Analytics", "type": "query-report", "link": "query-report/Sales Analytics",
			"color": colors["Selling"], "icon": "fa fa-line-chart"},
		{"module_name": "Master Sales Order", "_doctype": "Master Sales Order", "type": "list",
			"color": colors["Selling"], "icon": "octicon octicon-briefcase"},

		# old
		{
			"module_name": "Accounts",
			"color": colors["Accounts"],
			"icon": "octicon octicon-repo",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Stock",
			"color": colors["Stock"],
			"icon": "octicon octicon-package",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "CRM",
			"color": "#EF4DB6",
			"icon": "octicon octicon-broadcast",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Selling",
			"color": colors["Selling"],
			"icon": "octicon octicon-tag",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Buying",
			"color": colors["Buying"],
			"icon": "octicon octicon-briefcase",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "HR",
			"color": colors["HR"],
			"icon": "octicon octicon-organization",
			"label": _("Human Resources"),
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Manufacturing",
			"color": "#7f8c8d",
			"icon": "octicon octicon-tools",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Projects",
			"color": colors["Projects"],
			"icon": "octicon octicon-rocket",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Support",
			"color": colors["Support"],
			"icon": "octicon octicon-issue-opened",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Learn",
			"color": "#FF888B",
			"icon": "octicon octicon-device-camera-video",
			"type": "module",
			"is_help": True,
			"label": _("Learn"),
			"hidden": 1
		},
		{
			"module_name": "Maintenance",
			"color": "#FF888B",
			"icon": "octicon octicon-tools",
			"type": "module",
			"label": _("Maintenance"),
			"hidden": 1
		},
		{
			"module_name": "Education",
			"color": "#428B46",
			"icon": "octicon octicon-mortar-board",
			"type": "module",
			"label": _("Education"),
			"hidden": 1
		},
		{
			"module_name": "Healthcare",
			"color": "#FF888B",
			"icon": "fa fa-heartbeat",
			"type": "module",
			"label": _("Healthcare"),
			"hidden": 1
		},
		{
			"module_name": "Restaurant",
			"color": "#EA81E8",
			"icon": "🍔",
			"_doctype": "Restaurant",
			"type": "module",
			"link": "List/Restaurant",
			"label": _("Restaurant"),
			"hidden": 1
		},
		{
			"module_name": "Hotels",
			"color": "#EA81E8",
			"icon": "fa fa-bed",
			"type": "module",
			"label": _("Hotels"),
			"hidden": 1
		},
		{
			"module_name": "Agriculture",
			"color": "#8BC34A",
			"icon": "octicon octicon-globe",
			"type": "module",
			"label": _("Agriculture"),
			"hidden": 1
		},
		{
			"module_name": "Assets",
			"color": "#4286f4",
			"icon": "octicon octicon-database",
			"hidden": 1,
			"label": _("Assets"),
			"type": "module"
		},
		{
			"module_name": "Non Profit",
			"color": "#DE2B37",
			"icon": "octicon octicon-heart",
			"type": "module",
			"label": _("Non Profit"),
			"hidden": 1
		}
	]
