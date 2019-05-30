// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Qty Adjust"] = {
	"filters": [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
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
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (['total_so_qty', 'total_po_qty', 'actual_qty'].includes(column.fieldname)) {
			value = $(`<span>${value}</span>`);
			var $value = $(value).css("font-weight", "bold");
			value = $value.wrap("<p></p>").parent().html();
		}

		if (column.is_so_qty) {
			var link = encodeURI("desk#Form/Qty Adjust/Qty Adjust" +
				"?item_code=" + data.item_code + "&from_date=" + column.from_date + "&to_date=" + column.to_date);

			value = $(`<span>${value}</span>`);
			var $value = $(value).css("color", "#0a0157");
			$value = $value.wrap("<a href='" + link + "' target='_blank'></a>").parent();
			value = $value.wrap("<p></p>").parent().html();
		}
		return value;
	}
};
