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
                onchange: product.bind_change_delivery_date
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

product.bind_change_delivery_date = function() {
    var delivery_date = product.field_group.get_value('delivery_date') || "";
    shopping_cart.update_cart_field({
        fieldname: 'delivery_date',
        value: delivery_date
    });
    return frappe.call({
        type: "POST",
        method: "erpnext.www.product_list.get_delivery_date_prices",
        freeze: true,
        args: {
            delivery_date: delivery_date
        },
        callback: function(r) {
            $(".product-items-table").replaceWith(r.message.items);
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
        method: "erpnext.www.product_list.change_product_uom",
        freeze: true,
        args: {
            item_code: item_code,
            uom: uom
        },
        callback: function(r) {
            $(`.product-items-row[data-item-code="${item_code}"]`).replaceWith(r.message.item);
        }
    });
}

frappe.ready(function() {
    product.create_fields();
    product.bind_change_qty();
    product.bind_change_uom();
    window.zoom_item_image(".product-items",".product-page-image", "data-item-image");
});
