frappe.listview_settings['Quotation'] = {
	add_fields: ["customer_name", "base_grand_total", "status",
		"company", "currency", 'valid_till', 'confirmed_by_customer'],
	get_indicator: function(doc) {
		if(doc.status==="Submitted") {
			if (doc.valid_till && doc.valid_till < frappe.datetime.nowdate()) {
				return [__("Expired"), "darkgrey", "valid_till,<," + frappe.datetime.nowdate()];
			} else {
				return [__("To Create SO"), "red", "status,=,Submitted"];
			}
		} else if(doc.status==="Ordered") {
			return [__("Ordered"), "green", "status,=,Ordered"];
		} else if(doc.status==="Lost") {
			return [__("Lost"), "darkgrey", "status,=,Lost"];
		} else if(doc.docstatus == 0) {
			if (doc.confirmed_by_customer) {
				return [__("To Receive"), "orange", "confirmed_by_customer,=,1|docstatus,=,0"];
			} else {
				return [__("Draft"), "darkgrey", "confirmed_by_customer,=,0|docstatus,=,0"];
			}
		}
	},
	has_indicator_for_draft: 1,
	filters: [["confirmed_by_customer", "=", "1"]]
};
