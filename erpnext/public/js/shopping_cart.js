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

	update_cart_callback: function(r) {
		shopping_cart.set_cart_count();
		if (r.message.shopping_cart_menu) {
			shopping_cart.set_shopping_cart_menu(r.message.shopping_cart_menu);
		}
	},

	update_cart_item: function(opts) {
		if(!shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.update_cart_item",
				args: {
					item_code: opts.item_code,
					fieldname: opts.fieldname,
					value: opts.value,
					with_items: opts.with_items || 0
				},
				btn: opts.btn,
				freeze: opts.freeze || 1,
				callback: function(r) {
					shopping_cart.update_cart_callback(r);
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
					with_items: opts.with_items || 0
				},
				btn: opts.btn,
				freeze: opts.freeze || 1,
				callback: function(r) {
					shopping_cart.update_cart_callback(r);
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

	add_item: function(item_code, opts) {
		if (!opts) {
			opts = {};
		}

		if (item_code && !shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.add_item",
				freeze: opts.freeze || 1,
				args: {
					item_code: item_code,
					with_items: opts.with_items || 0
				},
				callback: function (r){
					shopping_cart.update_cart_callback(r);
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

	add_default_items: function(item_group, opts) {
		if (!opts) {
			opts = {};
		}

		if (item_group && !shopping_cart.in_update && !shopping_cart.ignore_update && shopping_cart.check_if_logged_in()) {
			shopping_cart.in_update = true;
			return frappe.call({
				type: "POST",
				method: "erpnext.shopping_cart.cart.get_default_items",
				freeze: opts.freeze || 1,
				args: {
					item_group: item_group,
					with_items: opts.with_items || 0
				},
				callback: function (r) {
					shopping_cart.update_cart_callback(r);
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
		var cart_count = frappe.get_cookie("cart_count");
		if(frappe.session.user==="Guest") {
			cart_count = 0;
		}

		if(cart_count) {
			$(".shopping-cart").toggleClass('hidden', false);
		}

		var $cart = $('.cart-icon');
		var $badge = $cart.find("#cart-count");
		if(parseInt(cart_count) === 0 || cart_count === undefined) {
			$cart.css("display", "none");
		}
		else {
			$cart.css("display", "inline");
		}

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
