frappe.provide('product');
var shopping_cart = erpnext.shopping_cart;

product.change_qty = function() {
    $(".product-items").on("change", ".product-qty", function() {
        var item_code = $(this).attr("data-item-code");
        var newVal = $(this).val();
        shopping_cart.shopping_cart_update_item(item_code, 'qty', newVal);
    });
}

frappe.ready(function() {
    product.change_qty();
    window.zoom_item_image(".product-items",".product-page-image");
});