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
                onchange: product.delivery_date_changed
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

product.delivery_date_changed = function() {
    if (product.ignore_update) {
        return;
    }

    var delivery_date = product.field_group.get_value('delivery_date') || "";
    shopping_cart.update_cart_field({
        fieldname: 'delivery_date',
        value: delivery_date,
        callback: function() {
            product.get_items_table();
        }
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
            value: newVal,
            callback: function(r) {
                product.get_item_row(item_code, newVal);
            }
        });
    });
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
            $(`.product-items-row[data-item-code="${item_code}"]`).replaceWith(r.message);
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
            $(".product-items-table").replaceWith(r.message);
        }
    });
}

frappe.ready(function() {
    product.item_group = frappe.utils.get_url_arg("item_group");

    product.create_fields();
    product.bind_change_qty();
    product.bind_change_uom();
    window.zoom_item_image(".product-items",".product-page-image", "data-item-image");
});
