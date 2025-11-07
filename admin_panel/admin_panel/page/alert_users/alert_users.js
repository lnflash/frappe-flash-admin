frappe.pages['alert-users'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Alert Users',
        single_column: true
    });

    page.main.html(`
        <style>
            .alert-form-container {
                max-width: 800px;
                margin: 40px auto;
                padding: 30px;
                background: #FFFFFF;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            
            .alert-form-header {
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 2px solid #DDE3E1;
            }
            
            .alert-form-header h3 {
                color: #212121;
                font-weight: 600;
                margin: 0;
            }
            
            .alert-form-header p {
                color: #939998;
                margin: 8px 0 0 0;
                font-size: 14px;
            }
            
            .form-group {
                margin-bottom: 24px;
            }
            
            .form-group label {
                display: block;
                font-weight: 600;
                color: #212121;
                margin-bottom: 8px;
                font-size: 14px;
            }
            
            .form-group label .required {
                color: #DC2626;
                margin-left: 2px;
            }
            
            .form-control {
                width: 100%;
                padding: 12px 16px;
                border: 1px solid #DDE3E1;
                border-radius: 6px;
                font-size: 14px;
                transition: all 0.3s ease;
                box-sizing: border-box;
                background: #FFFFFF;
                color: #212121;
            }
            
            .form-control:focus {
                outline: none;
                border-color: #007856;
                box-shadow: 0 0 0 3px rgba(0, 120, 86, 0.1);
            }
            
            .form-control::placeholder {
                color: #939998;
            }
            
            textarea.form-control {
                resize: vertical;
                min-height: 120px;
                font-family: inherit;
            }

            .form-group select {
                width: 100%;
                padding: 12px 16px;
                border: 1px solid #DDE3E1;
                border-radius: 6px;
                font-size: 14px;
                line-height: 1.5;           /* Add this */
                background: #FFFFFF;
                color: #212121;
                cursor: pointer;
                height: auto;               /* Add this */
                min-height: 42px;           /* Add this */
                appearance: none;           /* Add this for custom styling */
                background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23212121' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
                background-repeat: no-repeat;
                background-position: right 12px center;
                background-size: 16px;
                padding-right: 40px;        /* Add space for the arrow */
            }
            
            .btn-send-alert {
                background: linear-gradient(135deg, #E8D315 0%, #007856 100%);
                color: #002118;
                border: none;
                padding: 14px 32px;
                border-radius: 6px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0 4px 12px rgba(232, 211, 21, 0.3);
                width: 100%;
                margin-top: 10px;
            }
            
            .btn-send-alert:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 16px rgba(232, 211, 21, 0.4);
                background: linear-gradient(135deg, #E8D315 20%, #007856 100%);
            }
            
            .btn-send-alert:active {
                transform: translateY(0);
            }
            
            .btn-send-alert:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            
            .alert-preview {
                margin-top: 30px;
                padding: 20px;
                background: #F1F1F1;
                border-radius: 6px;
                border-left: 4px solid #007856;
            }
            
            .alert-preview h4 {
                color: #212121;
                margin: 0 0 10px 0;
                font-size: 16px;
            }
            
            .alert-preview p {
                color: #939998;
                margin: 0;
                font-size: 14px;
            }
            
            .char-count {
                font-size: 12px;
                color: #939998;
                text-align: right;
                margin-top: 4px;
            }
        </style>
        
        <div class="alert-form-container">
            <div class="alert-form-header">
                <h3>📢 Send Alert to All Users</h3>
                <p>Create and send an alert message that will be displayed to all users in the system</p>
            </div>
            
            <div class="form-group">
                <label for="alert-title">
                    Alert Title
                    <span class="required">*</span>
                </label>
                <input 
                    type="text" 
                    class="form-control" 
                    id="alert-title" 
                    placeholder="Enter a short, attention-grabbing title"
                    maxlength="100"
                >
                <div class="char-count">
                    <span id="title-count">0</span>/100 characters
                </div>
            </div>
            
            <div class="form-group">
                <label for="alert-description">
                    Alert Message
                    <span class="required">*</span>
                </label>
                <textarea 
                    class="form-control" 
                    id="alert-description" 
                    placeholder="Provide detailed information about the alert..."
                    maxlength="500"
                ></textarea>
                <div class="char-count">
                    <span id="description-count">0</span>/500 characters
                </div>
            </div>

            <div class="form-group">
                <label for="alert-tag">
                    Alert Type
                    <span class="required">*</span>
                </label>
                <select class="form-control" id="alert-tag">
                    <option value="EMERGENCY">Emergency</option>
                    <option value="WARNING">Warning</option>
                    <option value="INFO">Information</option>
                </select>
            </div>
            
            <button class="btn-send-alert" id="send-alert-btn">
                <span class="btn-text">Send Alert to All Users</span>
            </button>
            
            <div id="alert-preview" style="display: none;">
                <div class="alert-preview">
                    <h4>Preview:</h4>
                    <p><strong id="preview-title"></strong></p>
                    <p id="preview-description"></p>
                    <p><small id="preview-tag"></small></p>
                </div>
            </div>
        </div>
    `);

    const $titleInput = page.main.find('#alert-title');
    const $descriptionInput = page.main.find('#alert-description');
    const $tagSelect = page.main.find('#alert-tag');
    const $sendButton = page.main.find('#send-alert-btn');
    const $titleCount = page.main.find('#title-count');
    const $descriptionCount = page.main.find('#description-count');
    const $previewContainer = page.main.find('#alert-preview');
    const $previewTitle = page.main.find('#preview-title');
    const $previewDescription = page.main.find('#preview-description');
    const $previewTag = page.main.find('#preview-tag');

    function updatePreview() {
        const title = $titleInput.val().trim();
        const description = $descriptionInput.val().trim();
        const tag = $tagSelect.val();

        if (title || description) {
            $previewTitle.text(title || 'No title');
            $previewDescription.text(description || 'No message');
            $previewTag.text(`Type: ${tag}`);
            $previewContainer.fadeIn();
        } else {
            $previewContainer.fadeOut();
        }
    }

    function sendAlert(title, description, tag) {
        $sendButton.prop('disabled', true);
        $sendButton.html('<span class="btn-text">Sending...</span>');

        frappe.call({
            method: 'admin_panel.api.admin_api.send_alert',
            args: {
                title: title,
                message: description,
                tag: tag
            },
            callback: function(response) {
                if (response.message && response.message.success) {
                    frappe.show_alert({
                        message: 'Alert sent successfully to all users!',
                        indicator: 'green'
                    }, 5);

                    // Clear form
                    $titleInput.val('');
                    $descriptionInput.val('');
                    $tagSelect.val('EMERGENCY');
                    $titleCount.text('0');
                    $descriptionCount.text('0');
                    $previewContainer.fadeOut();
                } else {
                    const errorMsg = response.message?.error || 
                                   (response.message?.errors ? response.message.errors.join(', ') : '') || 
                                   'Unknown error';

                    frappe.msgprint({
                        title: 'Error',
                        message: `Failed to send alert: ${errorMsg}`,
                        indicator: 'red'
                    });
                }
            },
            error: function(error) {
                frappe.msgprint({
                    title: 'Error',
                    message: 'Failed to send alert. Please try again.',
                    indicator: 'red'
                });
            },
            always: function() {
                $sendButton.prop('disabled', false);
                $sendButton.html('<span class="btn-text">Send Alert to All Users</span>');
            }
        });
    }

    // Event handlers
    $titleInput.on('input', function() {
        $titleCount.text($(this).val().length);
        updatePreview();
    });

    $descriptionInput.on('input', function() {
        $descriptionCount.text($(this).val().length);
        updatePreview();
    });

    $tagSelect.on('change', updatePreview);

    $sendButton.on('click', function() {
        const title = $titleInput.val().trim();
        const description = $descriptionInput.val().trim();
        const tag = $tagSelect.val();

        if (!title) {
            frappe.msgprint({
                title: 'Missing Title',
                message: 'Please enter an alert title',
                indicator: 'red'
            });
            $titleInput.focus();
            return;
        }

        if (!description) {
            frappe.msgprint({
                title: 'Missing Message',
                message: 'Please enter an alert message',
                indicator: 'red'
            });
            $descriptionInput.focus();
            return;
        }

        frappe.confirm(
            `Are you sure you want to send this ${tag.toLowerCase()} alert to all users?<br><br>
            <strong>Title:</strong> ${title}<br>
            <strong>Message:</strong> ${description}<br>
            <strong>Type:</strong> ${tag}`,
            function() {
                sendAlert(title, description, tag);
            }
        );
    });
}