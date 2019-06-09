// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["LC Based Prices"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Price Effective Date"),
			fieldtype: "Date",
			reqd: 1
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options:"Item",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options:"Item Group",
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options:"Brand",
		},
	],
	onChange: function(new_value, column, data) {
		return frappe.call({
			method: "erpnext.stock.report.lc_based_prices.lc_based_prices.set_item_pl_rate",
			args: {
				effective_date: frappe.query_report.get_filter_value("date"),
				item_code: data['item_code'],
				price_list: column.price_list,
				price_list_rate: new_value,
				is_diff: Boolean(column.is_diff)
			},
			callback: function(r) {
				frappe.query_report.refresh();
			}
		});
	}
};
