// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Sundine Price List"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Price Effective Date"),
			fieldtype: "Date",
			default: frappe.datetime.nowdate(),
			reqd: 1
		},
		{
			fieldname: "valid_days",
			label: __("Valid For Days"),
			fieldtype: "Int",
			on_change: function () {
				return false;
			}
		},
		{
			fieldname: "previous_price_date",
			label: __("Price Ref Date for Increase/Decrease"),
			fieldtype: "Date"
		},
		{
			fieldname: "po_from_date",
			label: __("PO From Date"),
			default: frappe.datetime.nowdate(),
			fieldtype: "Date",
			hidden: !cint(frappe.defaults.get_default("restrict_amounts_in_report_to_role") && frappe.user.has_role(frappe.defaults.get_default("restrict_amounts_in_report_to_role")))
		},
		{
			fieldname: "po_to_date",
			label: __("PO To Date"),
			fieldtype: "Date",
			hidden: !cint(frappe.defaults.get_default("restrict_amounts_in_report_to_role") && frappe.user.has_role(frappe.defaults.get_default("restrict_amounts_in_report_to_role")))
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
			default:"Vegetables"
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options:"Brand",
			hidden: !cint(frappe.defaults.get_default("restrict_amounts_in_report_to_role") && frappe.user.has_role(frappe.defaults.get_default("restrict_amounts_in_report_to_role")))
		},
		{
			fieldname: "customer",
			label: __("For Customer"),
			fieldtype: "Link",
			options:"Customer",
			on_change: function () {
				var customer = frappe.query_report.get_filter_value('customer');
				if(customer) {
					frappe.db.get_value("Customer", customer, "default_price_list", function(value) {
						frappe.query_report.set_filter_value('selected_price_list', value["default_price_list"]);
					});
				} else {
					frappe.query_report.set_filter_value('selected_price_list', '');
				}
			}
		},
		{
			fieldname: "selected_price_list",
			label: __("Selected Price List"),
			fieldtype: "Link",
			options:"Price List"
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
			fieldname: "buying_selling",
			label: __("Buying Or Selling Prices"),
			fieldtype: "Select",
			options:"Selling\nBuying\nBoth",
			default:"Selling",
			hidden: !cint(frappe.defaults.get_default("restrict_amounts_in_report_to_role") && frappe.user.has_role(frappe.defaults.get_default("restrict_amounts_in_report_to_role")))
		},
		{
			fieldname: "price_list_1",
			label: __("Additional Price List 1"),
			fieldtype: "Link",
			options:"Price List"
		},
		{
			fieldname: "price_list_2",
			label: __("Additional Price List 2"),
			fieldtype: "Link",
			options:"Price List"
		},
		{
			fieldname: "price_list_3",
			label: __("Additional Price List 3"),
			fieldtype: "Link",
			options:"Price List"
		},
		{
			fieldname: "uom",
			label: __("UOM"),
			fieldtype: "Link",
			options:"UOM"
		},
		{
			fieldname: "default_uom",
			label: __("Default UOM"),
			fieldtype: "Select",
			options: "Default UOM\nStock UOM\nContents UOM",
			default: "Default UOM"
		},
	],
	formatter: function(value, row, column, data, default_formatter) {
		var options = {
			link_target: "_blank",
			css: {}
		};

		if (column.price_list && !column.is_diff) {
			var old_rate_field = "rate_old_" + frappe.scrub(column.price_list);
			if (data.hasOwnProperty(old_rate_field)) {
				if (flt(value) < flt(data[old_rate_field])) {
					options.css['color'] = 'green';
				} else if (flt(value) > flt(data[old_rate_field])) {
					options.css['color'] = 'red';
				}
			}

			var item_price_field = "item_price_" + frappe.scrub(column.price_list);
			if (data.hasOwnProperty(item_price_field) && data[item_price_field]) {
				options.link_href = "desk#Form/Item Price/" + data[item_price_field];
			}
		}

		if (column.fieldname == "po_qty") {
			var po_from_date = frappe.query_report.get_filter_value("po_from_date");
			var po_to_date = frappe.query_report.get_filter_value("po_to_date");
			options.link_href = "desk#query-report/Purchase Order Items To Be Received?item_code=" + data.item_code;
			if(po_from_date) {
				options.link_href += "&from_date=" + po_from_date
			}
			if(po_to_date) {
				options.link_href += "&to_date=" + po_to_date
			}
		}

		if (['po_qty', 'actual_qty', 'standard_rate', 'avg_lc_rate'].includes(column.fieldname)) {
			options.css['font-weight'] = 'bold';
		}

		if (column.fieldname == "alt_uom_size") {
			options.always_show_decimals = 0;
		}

		return default_formatter(value, row, column, data, options);
	},
	onChange: function(new_value, column, data, rowIndex) {
		var method;
		var args;

		if (column.fieldname === "print_in_price_list") {
			method = "frappe.client.set_value";
			args = {
				doctype: "Item",
				name: data.item_code,
				fieldname: 'print_in_price_list',
				value: new_value
			};
		} else {
			method = "erpnext.stock.report.sundine_price_list.sundine_price_list.set_item_pl_rate";
			args = {
				effective_date: frappe.query_report.get_filter_value("date"),
				item_code: data['item_code'],
				price_list: column.price_list,
				price_list_rate: new_value,
				is_diff: cint(column.is_diff),
				uom: data['uom'],
				filters: frappe.query_report.get_filter_values()
			};
		}

		return frappe.call({
			method: method,
			args: args,
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
	onload: function(listview) {
		listview.page.add_menu_item(__("Setup Auto Email"), function() {
			var customer = frappe.query_report.get_filter_value("customer");
			var title = "Price List";
			if (customer) {
				title = title + " - " + customer;
			}

			frappe.model.with_doctype('Auto Email Report', function() {
				var doc = frappe.model.get_new_doc('Auto Email Report');
				doc = Object.assign(doc,{
					'report': frappe.query_report.report_name,
					'title': title,
					'from_date_field': 'date',
					'to_date_field': 'date',
					'dynamic_date_period': 'Daily',
					'day_of_week': 'Tuesday',
					'frequency': 'Weekly',
					'format': 'PDF',
					'filters': JSON.stringify(frappe.query_report.get_filter_values()),
				});

				frappe.run_serially([
					() => frappe.set_route('Form', 'Auto Email Report', doc.name),
					() => cur_frm.set_value('filters', JSON.stringify(frappe.query_report.get_filter_values()))
				]);
			});
		});
	}
};
