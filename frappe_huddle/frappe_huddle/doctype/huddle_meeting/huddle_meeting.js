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

								let sid_val = frappe.utils.get_random(20);
								let heartbeat_interval;

								let jd = new frappe.ui.Dialog({
									title: frm.doc.title,
									size: "extra-large",
									fields: [
										{
											fieldname: "jitsi_iframe",
											fieldtype: "HTML",
											options: `
												<iframe src="${r.message.join_url}" id="jitsi_iframe"
													style="border:0; width:100%; height:calc(94vh - 80px); border-radius: 12px; background: #000; box-shadow: 0 4px 12px rgba(0,0,0,0.1);"
													allow="camera;microphone;fullscreen;display-capture;autoplay;clipboard-write"
													allowfullscreen>
												</iframe>
											`
										}
									],
									on_page_show: () => {
										// Start heartbeat for attendance tracking (DO NOT REMOVE)
										heartbeat_interval = setInterval(() => {
											frappe.call({
												method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.update_presence",
												args: { meeting_name: frm.doc.name, session_id: sid_val }
											});
										}, 20000);
										// Initial heartbeat ping
										frappe.call({
											method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.update_presence",
											args: { meeting_name: frm.doc.name, session_id: sid_val }
										});
									},
									onhide: () => {
										if (heartbeat_interval) clearInterval(heartbeat_interval);
									}
								});

								jd.$wrapper.find(".modal-dialog").css({
									"max-width": "98%",
									"margin": "10px auto"
								});

								jd.$wrapper.find(".modal-content").css("height", "96vh");

								jd.show();

								setTimeout(() => {
									if (frm.doc.status === "Scheduled") {
										frm.reload_doc();
									}
								}, 800);

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

			// Add "Copy Link" button — Issue #6: Copy Frappe join URL, not raw Jitsi link
			frm.add_custom_button(__("Copy Meeting Link"), function () {
				let frappe_join_url = window.location.origin + "/huddle/join?meeting=" + frm.doc.name;
				frappe.utils.copy_to_clipboard(frappe_join_url);
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

	// ──── Issue #5: Client-side duration warning ────
	duration(frm) {
		if (!frm.doc.duration) return;

		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Huddle Settings",
				fieldname: ["enforce_duration_limit", "max_duration_minutes", "duration_enforcement_mode"]
			},
			async: false,
			callback: function (r) {
				if (!r || !r.message) return;
				let settings = r.message;

				if (!settings.enforce_duration_limit) return;

				let max_dur = settings.max_duration_minutes || 120;
				if (frm.doc.duration > max_dur) {
					let msg = `Duration (${frm.doc.duration} mins) exceeds the maximum of ${max_dur} mins.`;
					if (settings.duration_enforcement_mode === "Hard") {
						frappe.msgprint({
							title: __("Duration Limit Exceeded"),
							message: __(msg + " Please reduce the duration before saving."),
							indicator: "red"
						});
						frm.set_value("duration", max_dur);
					} else {
						frappe.show_alert({
							message: __(msg + " Consider shortening the meeting."),
							indicator: "orange"
						}, 7);
					}
				}
			}
		});
	},

	status(frm) {
		// If user manually selects "Cancelled", prompt for Reschedule vs Cancel
		if (frm.doc.status === "Cancelled" && !frm.__is_cancelling) {
			// Revert temporarily to prevent accidental save without decision
			const prev_status = frm.doc.__original_status || "Scheduled";

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
