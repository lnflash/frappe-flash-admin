frappe.pages["alert-users"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Alert Users",
		single_column: true,
	});

	page.main.html(`
        <style>
            /* ═══ Ops-pulse design system — Alert Users (broadcast compose) ═══
               Fully scoped: the old block styled global .form-control and leaked
               into every desk form while this page was in the DOM. */
            .alert-users-page {
                --au-surface: var(--card-bg, #ffffff); --au-ink: var(--text-color, #1a2420);
                --au-ink2: var(--text-muted, #5c6b65); --au-ink3: var(--text-light, #8fa098);
                --au-line: var(--border-color, #e2e8e5); --au-line-soft: var(--subtle-fg, #ecf1ee);
                --au-accent: #007856; --au-accent-ink: #007856; --au-accent-soft: #e6f3ee;
                --au-good: #0ca30c; --au-warn: #b87d00; --au-warn-bg: #fff3d6;
                --au-serious: #c05a32; --au-serious-bg: #fdeae2;
                --au-info: #2563eb; --au-info-bg: #e8effd;
                --au-shadow: 0 1px 2px rgba(26,36,32,0.05), 0 4px 14px rgba(26,36,32,0.04);
                max-width: 1180px; margin: 0 auto; padding: 8px 12px 40px;
            }
            [data-theme="dark"] .alert-users-page, .dark .alert-users-page {
                --au-accent: #1e9e75; --au-accent-ink: #4cc29e; --au-accent-soft: #12352a;
                --au-good: #35c135; --au-warn: #fab219; --au-warn-bg: #33290d;
                --au-serious: #ec835a; --au-serious-bg: #38211a;
                --au-info: #6ea8fe; --au-info-bg: #172742;
                --au-shadow: 0 1px 2px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.25);
            }

            /* compose left, live preview + history right */
            .alert-users-page .au-grid { display: grid; grid-template-columns: 1fr 400px;
                gap: 16px; align-items: start; }
            @media (max-width: 980px) { .alert-users-page .au-grid { grid-template-columns: 1fr; } }

            .alert-users-page .au-card { background: var(--au-surface);
                border: 1px solid var(--au-line); border-radius: 14px;
                box-shadow: var(--au-shadow); overflow: hidden; }
            .alert-users-page .au-card + .au-card { margin-top: 16px; }
            .alert-users-page .au-card-header { padding: 14px 20px 12px;
                border-bottom: 1px solid var(--au-line); }
            .alert-users-page .au-card-header h3 { margin: 0; font-size: 15px;
                font-weight: 650; color: var(--au-ink); letter-spacing: -0.01em; }
            .alert-users-page .au-card-header p { margin: 3px 0 0; font-size: 12.5px;
                color: var(--au-ink3); }
            .alert-users-page .au-card-body { padding: 18px 20px 20px; }

            /* form */
            .alert-users-page .form-group { margin-bottom: 18px; }
            .alert-users-page .form-group label { display: block; font-size: 11px;
                letter-spacing: 0.05em; text-transform: uppercase; font-weight: 650;
                color: var(--au-ink2); margin-bottom: 7px; }
            .alert-users-page .form-group label .required { color: var(--au-serious);
                margin-left: 2px; }
            .alert-users-page .form-control { width: 100%; padding: 9px 13px;
                border: 1px solid var(--au-line); border-radius: 10px; font-size: 13.5px;
                background: var(--au-surface); color: var(--au-ink); box-sizing: border-box;
                transition: border-color 0.15s; }
            .alert-users-page .form-control:focus { outline: 2px solid var(--au-accent);
                outline-offset: 1px; border-color: var(--au-accent); box-shadow: none; }
            .alert-users-page .form-control::placeholder { color: var(--au-ink3); }
            .alert-users-page textarea.form-control { resize: vertical; min-height: 120px;
                font-family: inherit; }
            .alert-users-page select.form-control { cursor: pointer; appearance: auto;
                min-height: 38px; }
            .alert-users-page .char-count { font-size: 11.5px; color: var(--au-ink3);
                text-align: right; margin-top: 4px; font-variant-numeric: tabular-nums; }

            .alert-users-page .btn-send-alert { width: 100%; margin-top: 4px;
                background: var(--au-accent); border: 1px solid var(--au-accent);
                color: #fff; padding: 11px 24px; border-radius: 10px; font-size: 14px;
                font-weight: 650; cursor: pointer; transition: filter 0.13s; }
            .alert-users-page .btn-send-alert:hover { filter: brightness(1.07); }
            .alert-users-page .btn-send-alert:focus-visible { outline: 2px solid var(--au-accent);
                outline-offset: 2px; }
            .alert-users-page .btn-send-alert:disabled { opacity: 0.55; cursor: not-allowed; }

            /* live preview — styled like the notification the user receives */
            .alert-users-page .au-preview-empty { padding: 26px 20px; text-align: center;
                color: var(--au-ink3); font-size: 12.5px; }
            .alert-users-page .au-alert { border-left: 4px solid var(--au-accent);
                background: var(--au-line-soft); border-radius: 10px; padding: 13px 16px;
                margin: 0; }
            .alert-users-page .au-alert h4 { margin: 0 0 4px; font-size: 14px;
                font-weight: 650; color: var(--au-ink); overflow-wrap: anywhere; }
            .alert-users-page .au-alert p { margin: 0; font-size: 13px; color: var(--au-ink2);
                white-space: pre-wrap; overflow-wrap: anywhere; }
            .alert-users-page .au-alert-meta { display: flex; gap: 8px; align-items: center;
                margin-top: 9px; flex-wrap: wrap; }
            .alert-users-page .au-tag { display: inline-flex; border-radius: 999px;
                padding: 2px 9px; font-size: 11px; font-weight: 650;
                background: var(--au-accent-soft); color: var(--au-accent-ink); }
            .alert-users-page .au-alert-meta small { color: var(--au-ink3); font-size: 11.5px; }

            /* severity accents (shared by preview + history) */
            .alert-users-page .severity-emergency { border-left-color: var(--au-serious); }
            .alert-users-page .severity-emergency .au-tag { background: var(--au-serious-bg);
                color: var(--au-serious); }
            .alert-users-page .severity-attention { border-left-color: var(--au-warn); }
            .alert-users-page .severity-attention .au-tag { background: var(--au-warn-bg);
                color: var(--au-warn); }
            .alert-users-page .severity-info { border-left-color: var(--au-info); }
            .alert-users-page .severity-info .au-tag { background: var(--au-info-bg);
                color: var(--au-info); }
            .alert-users-page .severity-marketing { border-left-color: var(--au-good); }

            /* history */
            .alert-users-page .alert-item { border-left: 4px solid var(--au-accent);
                background: var(--au-line-soft); padding: 13px 16px; border-radius: 10px;
                margin-bottom: 12px; }
            .alert-users-page .alert-item:last-child { margin-bottom: 0; }
            .alert-users-page .alert-item h4 { margin: 0 0 4px; font-size: 13.5px;
                font-weight: 650; color: var(--au-ink); overflow-wrap: anywhere; }
            .alert-users-page .alert-item p { margin: 0; font-size: 12.5px;
                color: var(--au-ink2); overflow-wrap: anywhere; }
            .alert-users-page .au-history-empty { color: var(--au-ink3); font-size: 12.5px;
                margin: 0; }

            @media (prefers-reduced-motion: no-preference) {
                .alert-users-page .au-card { animation: au-rise 0.3s ease; }
                @keyframes au-rise { from { opacity: 0; transform: translateY(5px); } }
            }
        </style>

        <div class="alert-users-page">
            <div class="au-grid">
                <div class="au-card au-compose">
                    <div class="au-card-header">
                        <h3>Send Alert to All Users</h3>
                        <p>The alert is broadcast to every user in the system — you will be asked to confirm.</p>
                    </div>
                    <div class="au-card-body">
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
                            <select class="form-control" id="alert-tag" disabled>
                                <option value="">Loading alert types...</option>
                            </select>
                        </div>

                        <button class="btn-send-alert" id="send-alert-btn" disabled>
                            <span class="btn-text">Send Alert to All Users</span>
                        </button>
                    </div>
                </div>

                <div class="au-side">
                    <div class="au-card au-preview-card">
                        <div class="au-card-header">
                            <h3>Live Preview</h3>
                            <p>What users will see</p>
                        </div>
                        <div class="au-card-body">
                            <div class="au-preview-empty">Start typing to see the alert here.</div>
                            <div id="alert-preview" style="display: none;">
                                <div class="au-alert alert-preview-card">
                                    <h4 id="preview-title"></h4>
                                    <p id="preview-description"></p>
                                    <div class="au-alert-meta">
                                        <span class="au-tag" id="preview-tag"></span>
                                        <small>to all users</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="au-card au-history">
                        <div class="au-card-header">
                            <h3>Sent Alerts History</h3>
                            <p>The last 10 broadcasts</p>
                        </div>
                        <div class="au-card-body">
                            <div id="alert-history-list">
                                <p class="au-history-empty">Loading history...</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `);

	const $titleInput = page.main.find("#alert-title");
	const $descriptionInput = page.main.find("#alert-description");
	const $tagSelect = page.main.find("#alert-tag");
	const $sendButton = page.main.find("#send-alert-btn");
	const $titleCount = page.main.find("#title-count");
	const $descriptionCount = page.main.find("#description-count");
	const $previewContainer = page.main.find("#alert-preview");
	const $previewTitle = page.main.find("#preview-title");
	const $previewDescription = page.main.find("#preview-description");
	const $previewTag = page.main.find("#preview-tag");
	const $previewEmpty = page.main.find(".au-preview-empty");
	const $previewCard = page.main.find(".alert-preview-card");

	function updatePreview() {
		const title = $titleInput.val().trim();
		const description = $descriptionInput.val().trim();
		const tag = $tagSelect.val();

		if (title || description) {
			$previewTitle.text(title || "No title");
			$previewDescription.text(description || "No message");
			$previewTag.text(tag || "\u2014");
			$previewCard.attr("class", "au-alert alert-preview-card " + getSeverityClass(tag));
			$previewEmpty.hide();
			$previewContainer.fadeIn();
		} else {
			$previewContainer.hide();
			$previewEmpty.show();
		}
	}

	function loadAlertTypes() {
		frappe.call({
			method: "admin_panel.api.admin_api.get_alert_types",
			callback: function (r) {
				const topics = r.message && r.message.topics;
				$tagSelect.empty();

				if (!topics || topics.length === 0) {
					$tagSelect.append('<option value="">No alert types available</option>');
					return;
				}

				topics.forEach(function (topic) {
					$tagSelect.append(`<option value="${topic}">${topic}</option>`);
				});

				$tagSelect.prop("disabled", false);
				$sendButton.prop("disabled", false);
				updatePreview();
			},
			error: function () {
				$tagSelect.empty().append('<option value="">Failed to load types</option>');
				frappe.show_alert(
					{
						message: "Could not load alert types from API.",
						indicator: "red",
					},
					5
				);
			},
		});
	}

	function sendAlert(title, description, alertType) {
		$sendButton.prop("disabled", true);
		$sendButton.html('<span class="btn-text">Sending...</span>');

		frappe.call({
			method: "admin_panel.api.admin_api.send_alert",
			args: {
				title: title,
				message: description,
				alert_type: alertType,
			},
			callback: function (response) {
				if (response.message && response.message.success) {
					frappe.show_alert(
						{
							message: "Alert sent successfully to all users!",
							indicator: "green",
						},
						5
					);

					$titleInput.val("");
					$descriptionInput.val("");
					$titleCount.text("0");
					$descriptionCount.text("0");
					$previewContainer.fadeOut();

					loadAlertHistory();
				} else {
					const errorMsg =
						response.message?.error ||
						(response.message?.errors ? response.message.errors.join(", ") : "") ||
						"Unknown error";

					frappe.msgprint({
						title: "Error",
						message: `Failed to send alert: ${errorMsg}`,
						indicator: "red",
					});
				}
			},
			error: function () {
				frappe.msgprint({
					title: "Error",
					message: "Failed to send alert. Please try again.",
					indicator: "red",
				});
			},
			always: function () {
				$sendButton.prop("disabled", false);
				$sendButton.html('<span class="btn-text">Send Alert to All Users</span>');
			},
		});
	}

	function getSeverityClass(tag) {
		const t = (tag || "").toUpperCase();
		if (t.includes("EMERGENCY")) return "severity-emergency";
		if (t.includes("ATTENTION")) return "severity-attention";
		if (t.includes("INFO")) return "severity-info";
		if (t.includes("MARKETING")) return "severity-marketing";
		return "";
	}

	function loadAlertHistory() {
		frappe.call({
			method: "admin_panel.api.admin_api.get_user_alerts",
			args: { limit: 10 },
			callback: function (r) {
				const $historyList = page.main.find("#alert-history-list");
				$historyList.empty();

				if (!r.message || !r.message.logs || r.message.logs.length === 0) {
					$historyList.html(
						'<p class="au-history-empty">No alerts have been sent yet.</p>'
					);
					return;
				}

				const html = r.message.logs
					.map((log) => {
						const date = frappe.datetime.str_to_user(log.sent_on);
						return `
                        <div class="alert-item ${getSeverityClass(log.tag)}">
                            <h4>${frappe.utils.escape_html(log.title)}</h4>
                            <p>${frappe.utils.escape_html(log.message)}</p>
                            <div class="au-alert-meta">
                                <span class="au-tag">${frappe.utils.escape_html(
									log.tag || ""
								)}</span>
                                <small>${frappe.utils.escape_html(
									log.sent_by || ""
								)} \u00b7 ${date}</small>
                            </div>
                        </div>
                    `;
					})
					.join("");
				$historyList.html(html);
			},
		});
	}

	// Event handlers
	$titleInput.on("input", function () {
		$titleCount.text($(this).val().length);
		updatePreview();
	});

	$descriptionInput.on("input", function () {
		$descriptionCount.text($(this).val().length);
		updatePreview();
	});

	$tagSelect.on("change", updatePreview);

	$sendButton.on("click", function () {
		const title = $titleInput.val().trim();
		const description = $descriptionInput.val().trim();
		const alertType = $tagSelect.val();

		if (!title) {
			frappe.msgprint({
				title: "Missing Title",
				message: "Please enter an alert title",
				indicator: "red",
			});
			$titleInput.focus();
			return;
		}

		if (!description) {
			frappe.msgprint({
				title: "Missing Message",
				message: "Please enter an alert message",
				indicator: "red",
			});
			$descriptionInput.focus();
			return;
		}

		frappe.confirm(
			`Are you sure you want to send this ${alertType} alert to all users?<br><br>
            <strong>Title:</strong> ${title}<br>
            <strong>Message:</strong> ${description}<br>
            <strong>Type:</strong> ${alertType}`,
			function () {
				sendAlert(title, description, alertType);
			}
		);
	});

	loadAlertTypes();
	loadAlertHistory();
};
