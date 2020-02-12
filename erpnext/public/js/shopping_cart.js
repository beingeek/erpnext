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
							$('.shopping-cart-menu').html(r.message);
						}
					}
				});
			}
		});
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
				freeze: opts.freeze,
				callback: function(r) {
					shopping_cart.set_cart_count();
					if (r.message.shopping_cart_menu) {
						$('.shopping-cart-menu').html(r.message.shopping_cart_menu);
					}
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
					item_code:opts.item_code,
					fieldname: opts.fieldname,
					value: opts.value,
					with_items: opts.with_items || 0
				},
				btn: opts.btn,
				freeze: opts.freeze,
				callback: function(r) {
					shopping_cart.set_cart_count();
					if (r.message.shopping_cart_menu) {
						$('.shopping-cart-menu').html(r.message.shopping_cart_menu);
					}
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
			$(".cart-items").html('Cart is Empty');
			$(".cart-tax-items").hide();
			$(".btn-place-order").hide();
			$(".cart-addresses").hide();
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

	shopping_cart_update_callback: function(r, cart_dropdown) {
		if(!r.exc) {
			$(".cart-items").html(r.message.items);
			$(".cart-tax-items").html(r.message.taxes);
			if (cart_dropdown != true) {
				$(".cart-icon").hide();
			}

			$.each(r.message.fields || {}, function (k, v) {
				frappe.run_serially([
					() => shopping_cart.ignore_update = true,
					() => shopping_cart.field_group.set_value(k, v),
					() => shopping_cart.ignore_update = false,
				]);
			});
		}
	},

	shopping_cart_update_item: function(item_code, fieldname, value, cart_dropdown) {
		shopping_cart.update_cart_item({
			item_code: item_code,
			fieldname: fieldname,
			value: value,
			with_items: 1,
			btn: this,
			callback: function (r) {
				shopping_cart.shopping_cart_update_callback(r, cart_dropdown);
			},
			freeze: 1
		});
	},

	shopping_cart_update_field: function(fieldname, value, cart_dropdown) {
		shopping_cart.update_cart_field({
			item_code: item_code,
			fieldname: fieldname,
			value: value,
			with_items: 1,
			btn: this,
			callback: function (r) {
				shopping_cart.shopping_cart_update_callback(r, cart_dropdown);
			},
			freeze: 1
		});
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
				if (oldValue > 1) {
					newVal = parseInt(oldValue) - 1;
				}
			}
			input.val(newVal);
			var item_code = input.attr("data-item-code");
			shopping_cart.shopping_cart_update_item(item_code, newVal, true);
			return false;
		});

	},

});
