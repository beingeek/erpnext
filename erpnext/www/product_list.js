frappe.provide('product');
var shopping_cart = erpnext.shopping_cart;

product.create_fields = function() {
    product.field_group = new frappe.ui.FieldGroup({
        parent: $('#product-field'),
        fields: [
            {
                label: __('Delivery Date'),
                fieldname: 'delivery_date',
                fieldtype: 'Date',
                reqd: 1,
                onchange: product.handle_delivery_date_changed
            },
        ]
    });
    product.field_group.make();

    let values = {};
    $(`.product-field-data`).each(function (i, e) {
        let $this = $(this);
        values[$this.data('fieldname')] = $this.text();
    });
    $.each(values, function (k, v) {
        frappe.run_serially([
            () => product.ignore_update = true,
            () => product.field_group.set_value(k, v),
            () => product.ignore_update = false
        ]);
    });
}

product.bind_change_qty = function() {
    $(".product-items").on("change", ".product-qty", function() {
        var item_code = $(this).attr("data-item-code");
        var newVal = $(this).val();

        shopping_cart.update_cart_item({
            item_code: item_code,
            fieldname: 'qty',
            value: newVal
        });
    });
}

product.bind_change_uom = function() {
    $(".product-items").on("change", ".product-uom", function() {
        var item_code = $(this).attr("data-item-code");
        var newVal = $(this).val();

        shopping_cart.update_cart_item({
            item_code: item_code,
            fieldname: 'uom',
            value: newVal
        });
    });
}

product.handle_delivery_date_changed = function() {
    if (product.ignore_update) {
        return;
    }

    var delivery_date = product.field_group.get_value('delivery_date') || "";
    shopping_cart.update_cart_field({
        fieldname: 'delivery_date',
        value: delivery_date,
    });
}

product.handle_item_changed = function(r, opts) {
    var uom;
    if (opts.fieldname == 'uom' && opts.value) {
        uom = opts.value;
    }
    product.get_item_row(opts.item_code, uom);
}

product.handle_qoutation_changed = function() {
    product.get_items_table();
}

product.get_item_row = function(item_code, uom) {
    return frappe.call({
        type: "POST",
        method: "erpnext.www.product_list.get_item_row",
        freeze: true,
        args: {
            item_code: item_code,
            uom: uom
        },
        callback: function(r) {
            if (r && r.message) {
                $(`.product-items-row[data-item-code="${item_code}"]`).replaceWith(r.message);
            }
        }
    });
};

product.get_items_table = function() {
    return frappe.call({
        method: "erpnext.www.product_list.get_items_table",
        freeze: true,
        args: {
            item_group: product.item_group
        },
        callback: function(r) {
            if (r && r.message) {
                $(".product-items-table").replaceWith(r.message);
            }
        }
    });
}

frappe.ready(function() {
    product.item_group = frappe.utils.get_url_arg("item_group");

    shopping_cart.cart_update_item_callbacks.push(product.handle_item_changed);
    shopping_cart.cart_update_doc_callbacks.push(product.handle_qoutation_changed);

    product.create_fields();
    product.bind_change_qty();
    product.bind_change_uom();
    window.zoom_item_image(".product-items",".product-page-image", "data-item-image");
});
