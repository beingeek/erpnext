// Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.provide("erpnext.selling");

erpnext.selling.QtyAdjustController = frappe.ui.form.Controller.extend({
	setup: function() {
		this.frm.doc.from_date = get_url_arg("from_date");
		this.frm.doc.to_date = get_url_arg("to_date");
		this.frm.doc.item_code = get_url_arg("item_code");
		this.frm.trigger("item_code");
	},

	refresh: function() {
		this.frm.disable_save();
		this.frm.add_custom_button(__('Qty Adjust Report'), function() {
			frappe.set_route('query-report', 'Qty Adjust');
		});
	},

	onload: function() {
		this.set_po_qty_labels();
	},

	onload_post_render: function() {
		var me = this;

		me.frm.fields_dict.qty_adjust_sales_orders.$input.addClass("btn-primary");
		$(".grid-footer", me.frm.fields_dict.sales_orders.$wrapper).hide().addClass("hidden");

		me.frm.fields_dict.sales_orders.grid.wrapper.on('click', '.grid-row-check', function(e) {
			var unchecked = me.frm.fields_dict.sales_orders.grid.grid_rows.filter(row => !row.doc.__checked);
			$.each(unchecked || [], function(i, row) {
				row.doc.new_item_code = "";
				row.refresh_field("new_item_code");
			});
		});
	},

	from_date: function() {
		this.set_po_qty_labels();
		this.get_item_custom_projected_qty();
		this.get_sales_orders_for_qty_adjust();
	},

	to_date: function() {
		this.get_sales_orders_for_qty_adjust();
	},

	item_code: function() {
		this.get_item_name();
		this.get_item_custom_projected_qty();
		this.get_sales_orders_for_qty_adjust();
	},

	allocated_qty: function() {
		this.calculate_totals();
	},

	back_order_qty: function() {
		this.calculate_totals();
	},

	sales_orders_remove: function() {
		this.calculate_totals();
	},

	new_item_code: function(frm, cdt, cdn) {
		var grid_row = this.frm.fields_dict['sales_orders'].grid.grid_rows_by_docname[cdn];
		if (grid_row && grid_row.doc.__checked) {
			var checked_rows = this.frm.fields_dict['sales_orders'].grid.grid_rows
				.filter(row => row.doc.__checked && row.doc.name != cdn);

			$.each(checked_rows || [], function(i, d) {
				d.doc.new_item_code = grid_row.doc.new_item_code;
			});

			this.frm.refresh_field("sales_orders");
		}
	},

	get_item_name: function() {
		var me = this;

		if (me.frm.doc.item_code) {
			return frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Item",
					filters: {name: me.frm.doc.item_code},
					fieldname: "item_name"
				},
				callback: function(r) {
					if(r.message) {
						me.frm.set_value("item_name", r.message.item_name);
					}
				}
			});
		} else {
			me.frm.set_value("item_name", "");
		}
	},

	set_po_qty_labels: function() {
		var from_date = this.frm.doc.from_date || frappe.datetime.now_date();
		for (var i = 0; i < 5; ++i) {
			var from_date = new frappe.datetime.datetime(frappe.datetime.add_days(from_date, i));
			var day = from_date.format("ddd");
			this.frm.fields_dict["po_day_"+(i+1)].set_label("PO " + day);
			// this.frm.fields_dict["so_day_"+(i+1)].set_label("SO " + day);
		}
	},

	get_item_custom_projected_qty: function() {
		var me = this;

		if (me.frm.doc.from_date && me.frm.doc.item_code) {
			return this.frm.call({
				method: "erpnext.api.get_item_custom_projected_qty",
				freeze: true,
				args: {
					date: me.frm.doc.from_date,
					item_codes: [me.frm.doc.item_code]
				},
				callback: function(r) {
					if(!r.exc) {
						if(r.message.hasOwnProperty(me.frm.doc.item_code)) {
							var res = r.message[me.frm.doc.item_code];
							me.frm.doc['actual_qty'] = res['actual_qty'];
							me.frm.doc['projected_qty'] = res['projected_qty'];
							for(var i = 0; i < 5; ++i) {
								me.frm.doc['po_day_' + (i + 1)] = res['po_day_' + (i + 1)];
								me.frm.doc['so_day_' + (i + 1)] = res['so_day_' + (i + 1)];
							}
						} else {
							me.frm.doc['actual_qty'] = 0;
							me.frm.doc['projected_qty'] = 0;
							for(var i = 0; i < 5; ++i) {
								me.frm.doc['po_day_' + (i + 1)] = 0;
								me.frm.doc['so_day_' + (i + 1)] = 0;
							}
						}

						me.frm.refresh_fields();
					}
				}
			});
		}
	},

	get_sales_orders_for_qty_adjust: function() {
		var me = this;

		if (me.frm.doc.from_date && me.frm.doc.item_code) {
			return this.frm.call({
				method: "erpnext.api.get_sales_orders_for_qty_adjust",
				freeze: true,
				args: {
					from_date: me.frm.doc.from_date,
					to_date: me.frm.doc.to_date,
					item_code: me.frm.doc.item_code
				},
				callback: function(r) {
					if(!r.exc) {
						me.frm.doc.sales_orders = [];
						$.each(r.message || [], function(i, d) {
							var row = me.frm.add_child("sales_orders");
							Object.assign(row, d);
							row.allocated_qty = row.ordered_qty;
						});

						me.calculate_totals();
					}
				}
			});
		}
	},

	calculate_totals: function() {
		var me = this;

		var totals = {
			total_ordered_qty: 0, total_allocated_qty: 0, total_back_order_qty: 0, total_difference: 0,
		};

		$.each(me.frm.doc.sales_orders || [], function(i, d) {
			d.difference = flt(d.allocated_qty) - flt(d.ordered_qty);
			$.each(['ordered_qty', 'allocated_qty', 'back_order_qty', 'difference'], function(j, f) {
				d[f] = flt(d[f], precision(f, d));
				totals['total_' + f] += flt(d[f]);
			});
		});

		Object.assign(me.frm.doc, totals);

		this.frm.refresh_fields();
	},

	qty_adjust_sales_orders: function() {
		var me = this;

		if (me.frm.doc.sales_orders.length) {
			return me.frm.call({
				method: "qty_adjust_sales_orders",
				doc: me.frm.doc,
				freeze: true,
				callback: function(r) {
					if(!r.exc) {
						me.get_sales_orders_for_qty_adjust();
					}
				}
			});
		}
	}
});

$.extend(cur_frm.cscript, new erpnext.selling.QtyAdjustController({frm: cur_frm}));
