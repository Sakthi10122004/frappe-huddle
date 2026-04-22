// Copyright (c) 2026, Sakthi and contributors
// For license information, please see license.txt

frappe.ui.form.on("Huddle Meeting", {
	refresh(frm) {
		// Auto-set created_by_user on new documents
		if (frm.is_new() && !frm.doc.created_by_user) {
			frm.set_value("created_by_user", frappe.session.user);
		}

		// Show Join Meeting button if applicable
		const is_completed = frm.doc.status === "Completed";
		const is_cancelled = frm.doc.status === "Cancelled";
		const is_past = frm.doc.end_date && frappe.datetime.get_diff(frm.doc.end_date, frappe.datetime.now_datetime()) < 0;

		if (!frm.is_new() && frm.doc.jitsi_url && !is_completed && !is_cancelled && !is_past) {
			frm.add_custom_button(
			__("Join Huddle"),
			function () {

				console.log("Joining:", frm.doc.name);

				frappe.call({
					method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.join_meeting",
					args: { meeting_name: frm.doc.name },
					freeze: true,
					callback: function (r) {
						if (r && r.message && r.message.join_url) {

							let jd = new frappe.ui.Dialog({
								title: frm.doc.title,
								size: "extra-large",
								fields: [
									{
										fieldname: "jitsi_iframe",
										fieldtype: "HTML",
										options: `
											<iframe src="${r.message.join_url}"
												style="border:0; width:100%; height:calc(94vh - 80px); border-radius: 12px; background: #000;"
												allow="camera;microphone;fullscreen;display-capture;autoplay;clipboard-write"
												allowfullscreen>
											</iframe>
										`
									}
								]
							});

							jd.$wrapper.find(".modal-dialog").css({
								"max-width": "96%",
								"margin": "10px auto"
							});

							jd.$wrapper.find(".modal-content").css("height", "94vh");

							jd.show();
							
							// Wait slightly then reload doc behind the dialog
							setTimeout(() => {
								if (frm.doc.status === "Scheduled") {
									frm.reload_doc();
								}
							}, 500);

						} else {
							frappe.msgprint(__("Join URL not returned from server."));
						}
					},
					error: function (err) {
						console.error("API failed:", err);
						frappe.msgprint(__("Server error while joining meeting."));
					}
				});
			},
			null,
			"primary"
		);

			// Add "Copy Link" button
			frm.add_custom_button(__("Copy Meeting Link"), function () {
				frappe.utils.copy_to_clipboard(frm.doc.jitsi_url);
			});

			// Add "Resend Invites" button
			frm.add_custom_button(
				__("Resend Invites"),
				function () {
					frappe.confirm(
						__("Are you sure you want to resend email invites to all participants?"),
						() => {
							frappe.call({
								method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.resend_invites",
								args: { meeting_name: frm.doc.name },
								callback: function (r) {
									if (r.message) {
										frappe.show_alert({
											message: __("Invites have been queued successfully!"),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Actions")
			);
		}

		// Show meeting status indicator
		if (!frm.is_new()) {
			let indicator_color = {
				Scheduled: "blue",
				"In Progress": "orange",
				Completed: "green",
				Cancelled: "red",
			};
			frm.page.set_indicator(
				frm.doc.status,
				indicator_color[frm.doc.status] || "gray"
			);
		}
	},

	status(frm) {
		// If user manually selects "Cancelled", prompt for Reschedule vs Cancel
		if (frm.doc.status === "Cancelled" && !frm.__is_cancelling) {
			// Revert temporarily to prevent accidental save without decision
			const prev_status = frm.doc.__original_status || "Scheduled";
			
			frappe.warn(
				__("Cancel Huddle?"),
				__("Would you like to <b>Reschedule</b> this huddle for a later time or <b>Cancel</b> it entirely?"),
				() => {
					// Main Action: Reschedule
					frm.set_value("status", "Scheduled");
					frappe.msgprint(__("Please select a new <b>Meeting Date</b> and <b>Save</b> to reschedule."));
					// Focus on date field
					frm.scroll_to_field("meeting_date");
				},
				__("Reschedule"),
				true // secondary action will be "Cancel"
			);
			
			// Override the secondary action (Cancel) to actually set status to Cancelled
			// Frappe's frappe.warn doesn't easily allow 3 buttons, so we use it for Reschedule vs Cancel
			// If they click the Close (X) or "Cancel" (default secondary), we assume they want to Cancel
			// Let's use a custom Dialog for better control
			
			let d = new frappe.ui.Dialog({
				title: __("Cancel or Reschedule?"),
				fields: [
					{
						fieldtype: "HTML",
						options: `
							<p>${__("You are about to cancel this huddle. Do you want to reschedule it for another time instead?")}</p>
							<div style="margin-top: 20px; display: flex; justify-content: flex-end; gap: 10px;">
								<button class="btn btn-default btn-cancel-huddle" style="color: var(--red-600);">${__("Cancel Entirely")}</button>
								<button class="btn btn-primary btn-reschedule-huddle">${__("Reschedule")}</button>
							</div>
						`
					}
				],
			});

			d.$wrapper.find(".btn-cancel-huddle").click(() => {
				frm.__is_cancelling = true;
				frm.set_value("status", "Cancelled");
				frm.save();
				d.hide();
			});

			d.$wrapper.find(".btn-reschedule-huddle").click(() => {
				frm.set_value("status", "Scheduled");
				frappe.msgprint(__("Please update the <b>Meeting Date</b> and save to notify participants."));
				frm.scroll_to_field("meeting_date");
				d.hide();
			});

			// Revert field until decision is made
			frm.set_value("status", prev_status);
			d.show();
		}
	},
});

frappe.ui.form.on("Huddle Participant", {
	user(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.user) {
			frappe.db.get_value("User", row.user, ["full_name", "email"], (r) => {
				if (r) {
					frappe.model.set_value(cdt, cdn, "full_name", r.full_name);
					frappe.model.set_value(cdt, cdn, "email", r.email);
				}
			});
		} else {
			frappe.model.set_value(cdt, cdn, "full_name", "");
			frappe.model.set_value(cdt, cdn, "email", "");
		}
	},
});
