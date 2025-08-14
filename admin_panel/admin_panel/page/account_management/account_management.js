// File: customer_account_lookup/customer_account_lookup.js

frappe.pages['account-management'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Flash Account Manager',
        single_column: true
    });

    new FlashAccountManager(page);
};

class FlashAccountManager {
    constructor(page) {
        this.page = page;
        this.current_account_data = null;
        this.setup_page();
    }

    setup_page() {
        this.create_layout();
        this.bind_events();
    }

    create_layout() {
        this.page.main.html(`
            <div class="flash-account-manager">
                <!-- Search Section -->
                <div class="card mb-4">
                    <div class="card-body">
                        <h5>Search Flash Account</h5>
                        <div class="row">
                            <div class="col-md-8">
                                <input type="text" 
                                       class="form-control account-id-input" 
                                       placeholder="Enter Account ID">
                            </div>
                            <div class="col-md-4">
                                <button class="btn btn-primary btn-search w-100">Search</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Loading -->
                <div class="loading text-center py-4" style="display: none;">
                    <div class="spinner-border"></div>
                    <p class="mt-2">Loading...</p>
                </div>

                <!-- Error -->
                <div class="error alert alert-danger" style="display: none;"></div>

                <!-- Results -->
                <div class="results" style="display: none;">
                    <div class="card mb-3">
                        <div class="card-body">
                            <p><strong>ID:</strong> <span class="account-id"></span></p>
                            <p><strong>Level:</strong> 
                                <span class="level"></span>
                                <button class="btn btn-sm btn-outline-primary ms-2 btn-edit-level">
                                    <i class="fa fa-edit"></i> Edit
                                </button>
                            </p>
                            <p><strong>Username:</strong> <span class="username"></span></p>
                            <p><strong>Status:</strong> <span class="status"></span></p>
                            <p><strong>Email:</strong> <span class="email"></span></p>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-body">
                            <h6>Wallets</h6>
                            <div class="wallets-list"></div>
                        </div>
                    </div>
                </div>
            </div>
        `);
    }

    bind_events() {
        this.page.main.find('.btn-search').on('click', () => this.search());
        // this.page.main.find('.email-input').on('keypress', (e) => {
        //     if (e.which === 13) this.search();
        // });
        this.page.main.find('.btn-edit-level').on('click', () => this.edit_level());
    }

    search() {
        const id = this.page.main.find('.account-id-input').val().trim();
        if (!id) {
            frappe.msgprint('Please enter id');
            return;
        }

        this.show_loading();
        
        frappe.call({
            method: 'admin_panel.api.admin_api.get_account_by_id',
            args: { id: id },
            // args: { email: email },
            callback: (response) => {
                this.hide_loading();
                if (response.message?.success) {
                    this.current_account_data = response.message.data;
                    this.show_results(response.message.data);
                } else {
                    this.show_error(response.message?.error || 'Failed to load account');
                }
            },
            error: () => {
                this.hide_loading();
                this.show_error('Network error');
            }
        });
    }

    show_results(data) {
        this.page.main.find('.error').hide();
        
        // Basic info
        this.page.main.find('.account-id').text(data.account_id);
        this.page.main.find('.level').text(data.level);
        this.page.main.find('.username').text(data.username || 'None');
        this.page.main.find('.status').text(data.status);
        this.page.main.find('.email').text(data.owner?.email_address || 'None');
        
        // Wallets
        const wallets = data.wallets || [];
        let walletsHtml = '';
        if (wallets.length === 0) {
            walletsHtml = '<p class="text-muted">No wallets found</p>';
        } else {
            walletsHtml = '<ul class="list-group">';
            wallets.forEach(wallet => {
                walletsHtml += `
                    <li class="list-group-item d-flex justify-content-between">
                        <span>Ibex Account: ${wallet.id}</span>
                        <span>${wallet.currency}</span>
                        <span>Balance: ${wallet.balance}</span>
                    </li>
                `;
            });
            walletsHtml += '</ul>';
        }
        this.page.main.find('.wallets-list').html(walletsHtml);
        
        this.page.main.find('.results').show();
    }

    edit_level() {
        if (!this.current_account_data) {
            frappe.msgprint('No account data loaded');
            return;
        }

        const current_level = this.current_account_data.level || '';
        
        frappe.prompt({
            label: 'Account Level',
            fieldname: 'new_level',
            fieldtype: 'Data',
            default: current_level,
            reqd: 1
        }, (values) => {
          console.log(this.current_account_data)
          this.show_loading();
          frappe.call({
              method: 'admin_panel.api.admin_api.update_account_level',
              args: { uid: this.current_account_data.id, level: values.new_level },
              // args: { email: email },
              callback: (response) => {
                  this.hide_loading();
                  if (response.message?.success) {

                  } else {
                      this.show_error(response.message?.error || 'Failed to load account');
                  }
              },
              error: () => {
                  this.hide_loading();
                  this.show_error('Network error');
              }
          });
        }, 'Update Account Level', 'Update');
    }

    show_loading() {
        this.page.main.find('.error, .results').hide();
        this.page.main.find('.loading').show();
    }

    hide_loading() {
        this.page.main.find('.loading').hide();
    }

    show_error(message) {
        this.page.main.find('.loading, .results').hide();
        this.page.main.find('.error').text(message).show();
    }
}