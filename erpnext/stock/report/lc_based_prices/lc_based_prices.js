// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["LC Based Prices"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Price Effective Date"),
			fieldtype: "Date",
			default: frappe.datetime.nowdate(),
			reqd: 1
		},
		{
			fieldname: "po_from_date",
			label: __("PO From Date"),
			default: frappe.datetime.nowdate(),
			fieldtype: "Date"
		},
		{
			fieldname: "po_to_date",
			label: __("PO To Date"),
			fieldtype: "Date"
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
		{
			fieldname: "customer",
			label: __("For Customer"),
			fieldtype: "Link",
			options:"Customer"
		},
		{
			fieldname: "filter_items_without_price",
			label: __("Filter Items Without Price"),
			fieldtype: "Check"
		},
		{
			fieldname: "filter_price_list_by",
			label: __("Filter Price List By"),
			fieldtype: "Select",
			options:"Enabled\nDisabled\nAll",
			default:"Enabled"
		},
		{
			fieldname: "price_list_1",
			label: __("Show Price List Column 1"),
			fieldtype: "Link",
			options:"Price List"
		},
		{
			fieldname: "price_list_2",
			label: __("Show Price List Column 2"),
			fieldtype: "Link",
			options:"Price List"
		},
		{
			fieldname: "price_list_3",
			label: __("Show Price List Column 3"),
			fieldtype: "Link",
			options:"Price List"
		},
	],
	formatter: function(value, row, column, data, default_formatter) {
		var original_value = value;
		value = default_formatter(value, row, column, data);
		if (column.price_list && !column.is_diff) {
			var old_rate_field = "rate_old_" + frappe.scrub(column.price_list);
			if (data.hasOwnProperty(old_rate_field)) {
				if (flt(original_value) < flt(data[old_rate_field])) {
					value = $(`<span>${value}</span>`);
					var $value = $(value).css("color", "green");
					value = $value.wrap("<p></p>").parent().html();
				} else if (flt(original_value) > flt(data[old_rate_field])) {
					value = $(`<span>${value}</span>`);
					var $value = $(value).css("color", "red");
					value = $value.wrap("<p></p>").parent().html();
				}
			}
		}

		if (column.fieldname == "po_qty") {
			var po_from_date = frappe.query_report.get_filter_value("po_from_date");
			var po_to_date = frappe.query_report.get_filter_value("po_to_date");
			var link = "desk#query-report/Purchase Order Items To Be Received?item_code=" + data.item_code;
			if(po_from_date) {
				link += "&from_date=" + po_from_date
			}
			if(po_to_date) {
				link += "&to_date=" + po_to_date
			}
			value = $(`<span>${value}</span>`);
			var $value = $(value).wrap("<a href='" + link + "' target='_blank'></a>").parent();
			value = $value.wrap("<p></p>").parent().html();
		}
		return value;
	},
	onChange: function(new_value, column, data, rowIndex) {
		return frappe.call({
			method: "erpnext.stock.report.lc_based_prices.lc_based_prices.set_item_pl_rate",
			args: {
				effective_date: frappe.query_report.get_filter_value("date"),
				item_code: data['item_code'],
				price_list: column.price_list,
				price_list_rate: new_value,
				is_diff: cint(column.is_diff),
				filters: frappe.query_report.get_filter_values()
			},
			callback: function(r) {
				if (r.message) {
					frappe.query_report.datatable.datamanager.data[rowIndex] = r.message[1][0];

					frappe.query_report.datatable.datamanager.rowCount = 0;
					frappe.query_report.datatable.datamanager.columns = [];
					frappe.query_report.datatable.datamanager.rows = [];

					frappe.query_report.datatable.datamanager.prepareColumns();
					frappe.query_report.datatable.datamanager.prepareRows();
					frappe.query_report.datatable.datamanager.prepareTreeRows();
					frappe.query_report.datatable.datamanager.prepareRowView();
					frappe.query_report.datatable.datamanager.prepareNumericColumns();

					frappe.query_report.datatable.bodyRenderer.render();
				}
			}
		});
	},
	open_po_list: function(item_code) {
		frappe.route_options = {
			"item_code": item_code
		};
		frappe.set_route("query-report", "Purchase Order Items To Be Received");
	}
};
