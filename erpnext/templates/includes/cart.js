// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// js inside blog page

// shopping cart
frappe.provide("erpnext.shopping_cart");
var shopping_cart = erpnext.shopping_cart;

$.extend(shopping_cart, {
	show_error: function(title, text) {
		$("#cart-container").html('<div class="msg-box"><h4>' +
			title + '</h4><p class="text-muted">' + text + '</p></div>');
	},

	create_fields: function() {
		shopping_cart.field_group = new frappe.ui.FieldGroup({
			parent: $('#cart-fields'),
			fields: [
				{
					label: __('Delivery Date'),
					fieldname: 'delivery_date',
					fieldtype: 'Date',
					reqd: 1,
					onchange: shopping_cart.bind_change_delivery_date
				},
				{
					label: __('Customer Name'),
					fieldname: 'customer_name',
					fieldtype: 'Data',
					read_only: 1
				},
				{
					fieldtype: 'Column Break'
				},
				{
					label: __('Credit Limit'),
					fieldname: 'credit_limit',
					fieldtype: 'Currency',
					read_only: 1
				},
				{	
					label: __('Balance Amount'),
					fieldname: 'customer_balance',
					fieldtype: 'Currency',
					read_only: 1
				}
			]
		});
		shopping_cart.field_group.make();

		let values = {};
		$(`.cart-field-data`).each(function (i, e) {
			let $this = $(this);
			values[$this.data('fieldname')] = $this.text();
		});
		$.each(values, function (k, v) {
			frappe.run_serially([
				() => shopping_cart.ignore_update = true,
				() => shopping_cart.field_group.set_value(k, v),
				() => shopping_cart.ignore_update = false
			]);
		});
	},

	bind_events: function () {
		shopping_cart.bind_address_select();
		shopping_cart.bind_place_order();
		shopping_cart.bind_change_qty();
		shopping_cart.bind_change_uom();
		shopping_cart.bind_dropdown_cart_buttons();
		shopping_cart.bind_get_default_items();
		shopping_cart.bind_add_items();
	},

	bind_get_default_items: function () {
		$('.btn-get-default-items').click(function () {
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.get_default_items",
				freeze: true,
				args: {
					with_items: 1
				},
				callback: function (r) {
					shopping_cart.shopping_cart_update_callback(r);
				}
			});
		});

	},

	bind_add_items: function () {
		$('.btn-add-items').click(function () {
			var dialog = new frappe.ui.Dialog({
				data: [],
				title: __("Add Items"), fields: [
					{label: __("Search"), fieldname: "search", fieldtype: "Data"},
					{fieldname: "body", fieldtype: "HTML"}
				]
			});
			dialog.set_primary_action(__("Search"), () => shopping_cart.get_product_list.call(this, dialog));
			dialog.show();
		});
	},

	get_product_list: function(dialog) {
		return frappe.call({
			type: "POST",
			method: "erpnext.templates.pages.product_search.get_product_list",
			freeze: true,
			args: {
				search: dialog.get_value('search')
			},
			callback: function (r) {
				dialog.set_df_property('body', 'options', r.message);
				$('.product-link', dialog.$wrapper).click(function() {
					shopping_cart.add_item.call(this, dialog);
					return false;
				});
			}

		});
	},

	add_item: function(dialog) {
		var item_code = $(this).attr("data-item-code");
		if (item_code) {
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.add_item",
				freeze: true,
				args: {
					item_code: item_code,
					with_items: 1
				},
				callback: function (r){
					shopping_cart.shopping_cart_update_callback(r);
					dialog.hide();
				}
			})
		}
	},

	bind_change_delivery_date: function() {
		var delivery_date = shopping_cart.field_group.get_value('delivery_date');
		shopping_cart.shopping_cart_update_field('delivery_date', delivery_date);
	},

	bind_address_select: function() {
		$(".cart-addresses").find('input[data-address-name]').on("click", function() {
			if($(this).prop("checked")) {
				var me = this;

				// uncheck other shipping or billing addresses:
				if ( $(this).is('input[data-fieldname=customer_address]') ) {
					$('input[data-fieldname=customer_address]').not(this).prop('checked', false);
				} else {
					$('input[data-fieldname=shipping_address_name]').not(this).prop('checked', false);
				}

				return frappe.call({
					type: "POST",
					method: "erpnext.shopping_cart.cart.update_cart_address",
					freeze: true,
					args: {
						address_fieldname: $(this).attr("data-fieldname"),
						address_name: $(this).attr("data-address-name")
					},
					callback: function(r) {
						if(!r.exc) {
							$(".cart-tax-items").html(r.message.taxes);
						}
					}
				});
			} else {
				return false;
			}
		});

	},

	bind_place_order: function() {
		$(".btn-place-order").on("click", function() {
			shopping_cart.place_order(this);
		});
	},

	bind_change_qty: function() {
		// bind update button
		$(".cart-items").on("change", ".cart-qty", function() {
			var item_code = $(this).attr("data-item-code");
			var newVal = $(this).val();
			shopping_cart.shopping_cart_update_item(item_code, 'qty', newVal);
		});

		$(".cart-items").on('click', '.number-spinner button', function () {
			var btn = $(this),
				input = btn.closest('.number-spinner').find('input'),
				oldValue = input.val().trim(),
				newVal = 0;

			if (btn.attr('data-dir') == 'up') {
				newVal = parseInt(oldValue) + 1;
			} else {
				if (oldValue > 1) {
					newVal = parseInt(oldValue) - 1;
				}
			}
			input.val(newVal);
			var item_code = input.attr("data-item-code");
			shopping_cart.shopping_cart_update_item(item_code, 'qty', newVal);
		});
	},

	bind_change_uom: function() {
		$(".cart-items").on("change", ".cart-uom", function() {
			var item_code = $(this).attr("data-item-code");
			var newVal = $(this).val();
			shopping_cart.shopping_cart_update_item(item_code, 'uom', newVal);
		});
	},

	render_tax_row: function($cart_taxes, doc, shipping_rules) {
		var shipping_selector;
		if(shipping_rules) {
			shipping_selector = '<select class="form-control">' + $.map(shipping_rules, function(rule) {
				return '<option value="' + rule[0] + '">' + rule[1] + '</option>' }).join("\n") +
			'</select>';
		}

		var $tax_row = $(repl('<div class="row">\
			<div class="col-md-9 col-sm-9">\
				<div class="row">\
					<div class="col-md-9 col-md-offset-3">' +
					(shipping_selector || '<p>%(description)s</p>') +
					'</div>\
				</div>\
			</div>\
			<div class="col-md-3 col-sm-3 text-right">\
				<p' + (shipping_selector ? ' style="margin-top: 5px;"' : "") + '>%(formatted_tax_amount)s</p>\
			</div>\
		</div>', doc)).appendTo($cart_taxes);

		if(shipping_selector) {
			$tax_row.find('select option').each(function(i, opt) {
				if($(opt).html() == doc.description) {
					$(opt).attr("selected", "selected");
				}
			});
			$tax_row.find('select').on("change", function() {
				shopping_cart.apply_shipping_rule($(this).val(), this);
			});
		}
	},

	apply_shipping_rule: function(rule, btn) {
		return frappe.call({
			btn: btn,
			type: "POST",
			method: "erpnext.shopping_cart.cart.apply_shipping_rule",
			args: { shipping_rule: rule },
			callback: function(r) {
				if(!r.exc) {
					shopping_cart.render(r.message);
				}
			}
		});
	},

	place_order: function(btn) {
		return frappe.call({
			type: "POST",
			method: "erpnext.shopping_cart.cart.place_order",
			btn: btn,
			callback: function(r) {
				if(r.exc) {
					var msg = "";
					if(r._server_messages) {
						msg = JSON.parse(r._server_messages || []).join("<br>");
					}

					$("#cart-error")
						.empty()
						.html(msg || frappe._("Something went wrong!"))
						.toggle(true);
				} else {
					window.location.href = "/quotations/" + encodeURIComponent(r.message);
				}
			}
		});
	}
});

frappe.ready(function() {
	$(".cart-icon").hide();
	shopping_cart.create_fields();
	shopping_cart.bind_events();
});

function show_terms() {
	var html = $(".cart-terms").html();
	frappe.msgprint(html);
}
