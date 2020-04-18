frappe.provide('default_items');

default_items.add_default_item = function(item_code) {
    return frappe.call({
        type: "POST",
        method: "erpnext.www.default_items.add_default_item",
        freeze: true,
        args: {
            item_code: item_code
        },
        callback: function(r) {
            if (r.message) {
                $("#default-items").append(r.message);
            }
            default_items.empty_default_items();
        }
    })
};

default_items.remove_default_item = function(item_code) {
    if (item_code) {
        frappe.confirm(__('Are you sure you want to remove this item'),
            () => {
                    return frappe.call({
                        type: "POST",
                        method: "erpnext.www.default_items.remove_default_item",
                        freeze: true,
                        args: {
                            item_code: item_code
                        },
                        callback: function(r) {
                            if (r.message) {
                                $(`.default-item-row[data-item-code='${item_code}']`).remove();
                            }
                            default_items.empty_default_items();
                        }
                });
            }
        );
    }
};

default_items.magnify_default_items = function() {
    var modal = document.getElementById("myModal");
    var modalImg = document.getElementById("img01");

    $('#default-items').on('click', '.default-product-image', function() {
        var pro_img = $(this).attr("data-item-image");
        if (pro_img) {
            modal.style.display = "block";
            modalImg.src = pro_img;
        }
    });
    var span = document.getElementsByClassName("close")[0];
    span.onclick = function() {
        modal.style.display = "none";
    }
    $(document).on('keydown', function(e) {
        if (e.keyCode === 27) {
            modal.style.display = "none";
        }
    });
};

default_items.empty_default_items = function() {
    var tbody = document.getElementById("default-items");
    if (tbody.childElementCount === 0) {
        $("#default-items").html('<tr class="empty-items"><td colspan="10" class="text-center">No Default Items</td></tr>');
    } else {
        $(".empty-items").remove();
    }
};

frappe.ready(function() {
    $('.btn-add-items').click(function() {
        window.add_item_dialog(default_items.add_default_item);
    });

    $("#default-items").on("click", ".btn-remove-item", function() {
        var item_code = $(this).attr('data-item-code');
        default_items.remove_default_item(item_code);
    });

    default_items.magnify_default_items();
    default_items.empty_default_items();
});
