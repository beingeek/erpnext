frappe.provide('product');
var shopping_cart = erpnext.shopping_cart;

product.change_qty = function() {
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

product.change_uom = function() {
    $(".product-items").on("change", ".product-uom", function() {
        var item_code = $(this).attr("data-item-code");
        var newVal = $(this).val();

        shopping_cart.update_cart_item({
            item_code: item_code,
            fieldname: 'uom',
            value: newVal,
            callback: function(r) {
                product.change_uom_item_row(item_code, newVal);
            }
        });
    });
}

product.change_uom_item_row = function(item_code, uom) {
    return frappe.call({
        type: "POST",
        method: "erpnext.www.product_list.change_product_uom",
        freeze: true,
        args: {
            item_code: item_code,
            uom: uom
        },
        callback: function(r) {
            debugger;
            $(`.product-items-row[data-item-code="${item_code}"]`).replaceWith(r.message.item);
        }
    });
}

frappe.ready(function() {
    product.change_qty();
    product.change_uom();
    window.zoom_item_image(".product-items",".product-page-image");
});