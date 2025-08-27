frappe.pages['account-management'].on_page_load = function(wrapper) {
    if (!frappe.user_roles.includes('Accounts Manager')) {
        var page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Flash Account Manager',
            single_column: true
        });
        
        page.main.html(`
            <div class="text-center mt-5">
                <div class="alert alert-warning">
                    <h4>Access Denied</h4>
                    <p>You do not have permission to access this page. Please contact your administrator to get the "Account Manager" role.</p>
                </div>
            </div>
        `);
        return;
    }

    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Flash Account Manager',
        single_column: true
    });

    new FlashAccountManager(page);
};

const accountLevels = [
    {label: 'Trial', value: 'ZERO'},
    {label: 'Personal', value: 'ONE'},
    {label: 'Pro', value: 'TWO'},
    {label: 'Business', value: 'THREE'}
]

function getAccountLevelLabel(level) {
    const levelObj = accountLevels.find(item => item.value === level);
    return levelObj ? levelObj.label : level;
}

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
            <div class="flash-account-manager m-3">
                <div class="card mb-4">
                    <div class="card-body">
                        <h5>Search Account</h5>
                        <div class="d-flex gap-3">
                            <input 
                                type="tel" 
                                id="basic-phone" 
                                class="form-control phone-input" 
                                placeholder="Enter user phone number"
                                pattern="[0-9\s\-\+\(\)]+"
                                style="width: 250px;"
                            >
                            <button class="btn btn-primary btn-search">Search</button>
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
                            <p><strong>Account ID:</strong> <span class="account-id"></span></p>
                            <p><strong>Phone: </strong> <span class="phone"></span></p>
                            <p class="d-flex align-items-center">
                                <strong class="me-2">Level: </strong> 
                                <span class="level me-2"></span>
                                <button class="btn btn-sm btn-outline-primary btn-edit-level" title="Edit level">
                                    <i class="fa fa-edit"></i> 
                                </button>
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        `);
    }

    bind_events() {
        this.page.main.find('.btn-search').on('click', () => this.search());
        this.page.main.find('.btn-edit-level').on('click', () => this.edit_level());
        this.page.main.find('.phone-input').on('focus', (e) => {
            $(e.target).removeClass('border-danger');
        });
        this.page.main.find('.phone-input').on('keypress', (e) => {
            if (e.which === 13) {
                this.search();
            }
        });
    }

    search() {
        const phone = this.read_phone_input();
        if (!phone) {
            return;
        }
        
        this.show_loading();
        
        frappe.call({
            method: 'admin_panel.api.admin_api.get_account_by_phone',
            args: { phone: phone },
            callback: (response) => {
                this.hide_loading();
                this.current_account_data = response.message;
                this.show_results();
            },
            error: (e) => {
                this.hide_loading();
                this.show_error(e.message || 'Network error');
            }
        });
    }

    read_phone_input() {
        const phoneInput = this.page.main.find('.phone-input');
        const phone = phoneInput.val().trim();
        
        if (!phone) {
            phoneInput.addClass('border-danger');
            return null;
        }
        
        const cleaned = phone.replace(/[\s\-\(\)\.]/g, '');
        if (!/^\+?\d{10,15}$/.test(cleaned)) {
            phoneInput.addClass('border-danger');
            return null;
        }
        
        phoneInput.removeClass('border-danger');
        return cleaned;
    }

    show_results() {
        const data = this.current_account_data;

        this.page.main.find('.error').hide();
        this.page.main.find('.account-id').text(data.id);
        const formattedPhone = this.formatPhone(data.owner.phone);
        this.page.main.find('.phone').text(formattedPhone);
        this.page.main.find('.level').text(getAccountLevelLabel(data.level));
        this.page.main.find('.results').show();
    }

    edit_level() {
        if (!this.current_account_data) {
            return;
        }

        const current_level = this.current_account_data.level || '';
        
        frappe.prompt({
            label: 'Account Level',
            fieldname: 'new_level',
            fieldtype: 'Select',
            options: accountLevels,
            default: current_level,
            reqd: 1
        }, (values) => {
          this.show_loading();
          frappe.call({
              method: 'admin_panel.api.admin_api.update_account_level',
              args: { uid: this.current_account_data.id, level: values.new_level },
              // args: { email: email },
              callback: (response) => {
                this.current_account_data["level"] = values.new_level;
                this.show_results(this.current_account_data);
                this.hide_loading();
                frappe.show_alert({
                    message:__('Account level updated successfully'),
                    indicator:'green'
                }, 5);
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

    formatPhone(phone) {
        if (!phone) return '';
        
        const digits = phone.replace(/\D/g, '');
        if (digits.length === 10) {
            return `(${digits.slice(0,3)}) ${digits.slice(3,6)}-${digits.slice(6)}`;
        } else if (digits.length === 11 && digits[0] === '1') {
            return `+1 (${digits.slice(1,4)}) ${digits.slice(4,7)}-${digits.slice(7)}`;
        }
        return phone; // Return original if can't format
    }
}