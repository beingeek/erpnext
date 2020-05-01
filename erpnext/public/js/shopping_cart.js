// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// shopping cart
frappe.provide("erpnext.shopping_cart");
var shopping_cart = erpnext.shopping_cart;

frappe.ready(function() {
	var full_name = frappe.session && frappe.session.user_fullname;
	// update user
	if(full_name) {
		$('.navbar li[data-label="User"] a')
			.html('<i class="fa fa-fixed-width fa fa-user"></i> ' + full_name);
	}

	// update login
	shopping_cart.show_shoppingcart_dropdown();
	shopping_cart.set_cart_count();
	shopping_cart.bind_dropdown_cart_buttons();
});

$.extend(shopping_cart, {
	cart_update_callbacks: [],
	cart_update_doc_callbacks: [],
	cart_update_item_callbacks: [],

	show_shoppingcart_dropdown: function() {
		$(".shopping-cart").on('shown.bs.dropdown', function() {
			if (!$('.shopping-cart-menu .cart-container').length) {
				return frappe.call({
					method: 'erpnext.shopping_cart.cart.get_shopping_cart_menu',
					callback: function(r) {
						if (r.message) {
							shopping_cart.set_shopping_cart_menu(r.message);
						}
					}
				});
			}
		});
	},

	set_shopping_cart_menu: function(html) {
		$('.shopping-cart-menu').html(html);
	},

	check_if_logged_in: function() {
		if(frappe.session.user==="Guest") {
			if(localStorage) {
				localStorage.setItem("last_visited", window.location.pathname);
			}
			window.location.href = "/login";
			return false;
		}
		return true;
	},

	update_cart_callback: function(r, opts) {
		shopping_cart.set_cart_count();
		if (r.message.shopping_cart_menu) {
			shopping_cart.set_shopping_cart_menu(r.message.shopping_cart_menu);
		}

		$.each(shopping_cart.cart_update_callbacks || [], callback => callback(r, opts));
		if (opts.item_code) {
			$.each(shopping_cart.cart_update_item_callbacks || [], (i, callback) => callback(r, opts));
		} else {
			$.each(shopping_cart.cart_update_doc_callbacks || [], (i, callback) => callback(r, opts));
		}
	},

	update_cart_item: function(opts) {
		if (!opts || !opts.item_code || !opts.fieldname || opts.value == null) {
			return;
		}

		if(!shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.update_cart_item",
				args: {
					item_code: opts.item_code,
					fieldname: opts.fieldname,
					value: opts.value,
					with_items: opts.with_items || 0,
					name: opts.name
				},
				btn: opts.btn,
				freeze: opts.freeze || 1,
				callback: function(r) {
					shopping_cart.update_cart_callback(r, opts);
					if(opts.callback)
						opts.callback(r);
				},
				always: function() {
					shopping_cart.in_update = false;
					if (opts.always)
						opts.always();
				}
			});
		}
	},

	update_cart_field: function(opts) {
		if(!shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.update_cart_field",
				args: {
					fieldname: opts.fieldname,
					value: opts.value,
					with_items: opts.with_items || 0,
					name: opts.name
				},
				btn: opts.btn,
				freeze: opts.freeze || 1,
				callback: function(r) {
					shopping_cart.update_cart_callback(r, opts);
					if(opts.callback)
						opts.callback(r);
				},
				always: function() {
					shopping_cart.in_update = false;
					if (opts.always)
						opts.always();
				}
			});
		}
	},

	add_item: function(opts) {
		if (!opts || !opts.item_code) {
			return;
		}

		if (!shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.add_item",
				freeze: opts.freeze || 1,
				args: {
					item_code: opts.item_code,
					with_items: opts.with_items || 0,
					name: opts.name
				},
				callback: function (r){
					shopping_cart.update_cart_callback(r, opts);
					if (opts.callback) {
						opts.callback(r);
					}
				},
				always: function() {
					shopping_cart.in_update = false;
					if (opts.always)
						opts.always();
				}
			});
		}
	},

	add_default_items: function(opts) {
		if (!opts) {
			opts = {};
		}

		if (!shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.get_default_items",
				freeze: opts.freeze || 1,
				args: {
					item_group: opts.item_group || "",
					with_items: opts.with_items || 0,
					name: opts.name
				},
				callback: function (r) {
					shopping_cart.update_cart_callback(r, opts);
					if (opts.callback) {
						opts.callback(r);
					}
				},
				always: function() {
					shopping_cart.in_update = false;
					if (opts.always)
						opts.always();
				}
			});
		}
	},

	copy_items_from_transaction: function(opts) {
		if (!opts || !opts.dt || !opts.dn) {
			return;
		}

		if (!shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.copy_items_from_transaction",
				freeze: opts.freeze || 1,
				args: {
					dt: opts.dt,
					dn: opts.dn,
					with_items: opts.with_items || 0,
				},
				callback: function (r) {
					shopping_cart.update_cart_callback(r, opts);
					if (opts.callback) {
						opts.callback(r);
					}
				},
				always: function() {
					shopping_cart.in_update = false;
					if (opts.always)
						opts.always();
				}
			});
		}
	},

	set_cart_count: function() {
		var $cart = $('.cart-icon');
		var $badge = $cart.find("#cart-count");
		var cart_count = frappe.get_cookie("cart_count");
		var to_show = true;

		if(frappe.session.user==="Guest") {
			cart_count = 0;
			to_show = false;
		}

		$(".shopping-cart").toggleClass('hidden', !to_show);
		$cart.css("display", to_show ? "inline" : "none");

		if(cart_count) {
			$badge.html(cart_count);
		} else {
			$badge.remove();
		}
	},

	bind_dropdown_cart_buttons: function () {
		$(".cart-icon").on('click', '.number-spinner button', function () {
			var btn = $(this),
				input = btn.closest('.number-spinner').find('input'),
				oldValue = input.val().trim(),
				newVal = 0;

			if (btn.attr('data-dir') == 'up') {
				newVal = parseInt(oldValue) + 1;
			} else {
				if (parseInt(oldValue) >= 1) {
					newVal = parseInt(oldValue) - 1;
				}
			}

			input.val(newVal);
			var item_code = input.attr("data-item-code");

			shopping_cart.update_cart_item({
				item_code: item_code,
				fieldname: 'qty',
				value: newVal,
				btn: btn,
				freeze: 1
			});

			return false;
		});

	},

});
