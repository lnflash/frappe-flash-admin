frappe.ui.form.on('Cashout', {

	onload: function(frm) {
		if (frm.doc.customer) {
			frm.set_query('bank_account', () => ({
				filters: [
					['Bank Account', 'party_type', '=', 'Customer'],
					['Bank Account', 'party', '=', frm.doc.customer]
				]
			}));
		}
	},

	customer: function(frm) {
		frm.set_value('bank_account', null);
		frm.set_query('bank_account', () => ({
			filters: [
				['Bank Account', 'party_type', '=', 'Customer'],
				['Bank Account', 'party', '=', frm.doc.customer]
			]
		}));
	},

	refresh: function(frm) {
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.status === 'In Progress' &&
			!frm.doc.payment_journal_entry
		) {
			frm.add_custom_button('Mark as Completed', () => {
				frappe.confirm(
					'Are you sure you want to mark this cashout as Completed and create a Payment Journal Entry?',
					() => {
						frappe.call({
							method: 'create_payment_journal_entry',
							doc: frm.doc,
							callback: function(r) {
								frm.reload_doc();
							}
						});
					}
				);
			}, 'Actions');
		}
	}
});
