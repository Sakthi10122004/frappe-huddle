frappe.views.calendar["Huddle Meeting"] = {
	field_map: {
		start: "meeting_date",
		end: "end_date",
		id: "name",
		allDay: "all_day",
		title: "title",
		status: "status",
	},
	style_map: {
		Scheduled: "blue",
		"In Progress": "orange",
		Completed: "green",
		Cancelled: "red",
	},
	get_events_method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.get_events",

	options: {
		editable: false,
		eventStartEditable: false,
		eventDurationEditable: false,
		selectable: false,
		selectHelper: false,
		droppable: false,
		eventLimit: 3,

		eventRender: function (event, element) {
			const start = event.start && event.start.format
				? event.start.format("YYYY-MM-DD HH:mm:ss")
				: event.start;

			if (start) {
				const date = frappe.datetime.global_date_format(start);
				element.attr("title", `${event.title} (${date})`);
			}

			const color_map = {
				Scheduled: "#0351b6ff",
				"In Progress": "#eead45ff",
				Completed: "#1ee470ff",
				Cancelled: "#e74c3c",
			};
			const color = color_map[event.status] || "#95a5a6";
			element.css({
				"background-color": color,
				"border-color": color,
				"color": "white",
				"border-radius": "4px",
				"padding": "4px 8px",
				"font-weight": "500",
				"cursor": "pointer",
				"box-shadow": "0 2px 4px rgba(0,0,0,0.1)"
			});

			element.removeClass("fc-draggable");
		},

		eventClick: function (calEvent, jsEvent, view) {
			const name = calEvent.name || calEvent.id;
			if (!name) return false;

			// Use our own whitelisted method — frappe.client.get is not available
			// in this Frappe version. This also updates status on the fly.
			frappe.call({
				method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.get_meeting_details",
				args: { meeting_name: name },
				callback: function (r) {
					if (!r.message) {
						frappe.msgprint(__("Could not load meeting details. Please try again."));
						return;
					}

					const doc = r.message;

					const is_upcoming = doc.status === "Scheduled";
					const is_live = doc.status === "In Progress";
					const is_completed = doc.status === "Completed";

					const status_colors = {
						Scheduled: "blue",
						"In Progress": "orange",
						Completed: "green",
						Cancelled: "red",
					};

					const indicator = `<span class="indicator-pill ${status_colors[doc.status] || "gray"}">${doc.status}</span>`;
					const date_display = doc.meeting_date
						? frappe.datetime.global_date_format(doc.meeting_date)
						: "";
					const start_time = doc.meeting_date
						? frappe.datetime.get_time(doc.meeting_date)
						: "";
					const end_time = doc.end_date
						? frappe.datetime.get_time(doc.end_date)
						: "";

					const participants = (doc.participants || [])
						.map(function(p) { return p.full_name; })
						.filter(Boolean)
						.join(", ");

					// Build action buttons HTML directly — avoids d.add_custom_button
					// which is not available in this Frappe version
					const join_btn_html = (is_upcoming || is_live) ? `
						<button class="btn btn-primary huddle-join-btn" style="margin-right:12px; font-weight:700; padding:8px 20px;">
							${is_live ? __("Join Now (Live)") : __("Join When Starts")}
						</button>
					` : "";

					const d = new frappe.ui.Dialog({
						title: __("Huddle Details"),
						fields: [
							{
								fieldname: "info_html",
								fieldtype: "HTML",
								options: `
									<div class="huddle-popup-card">
										<h3 style="margin-top:0; color: var(--text-color); font-weight: 700; font-size: 1.5em; line-height: 1.2;">${doc.title}</h3>
										<div class="huddle-meta-row" style="margin-bottom: 15px; display: flex; align-items: center;">
											${indicator}
											<span style="margin-left: 12px; color: var(--text-muted); font-size: 0.9em; font-family: var(--font-stack-monospace);">${doc.name}</span>
										</div>

										<div style="background: var(--bg-light-gray); padding: 18px; border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 10px; box-shadow: inset 0 2px 6px rgba(0,0,0,0.03);">
											<div style="margin-bottom: 10px; display: flex; align-items: center;">
												<i class="fa fa-calendar" style="width: 28px; color: var(--primary-color); font-size: 1.2em;"></i>
												<span style="font-weight: 600; font-size: 1.1em;">${date_display}</span>
											</div>
											<div style="margin-bottom: 10px; display: flex; align-items: center;">
												<i class="fa fa-clock-o" style="width: 28px; color: var(--primary-color); font-size: 1.2em;"></i>
												<span style="font-size: 1.1em; font-weight: 500;">${start_time}${end_time ? " – " + end_time : ""}</span>
											</div>
											<div style="display: flex; align-items: flex-start;">
												<i class="fa fa-users" style="width: 28px; color: var(--primary-color); font-size: 1.2em; margin-top: 4px;"></i>
												<div style="flex: 1;">
													<div style="font-size: 0.85em; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px;">Participants</div>
													<div style="color: var(--text-color); line-height: 1.4; font-size: 0.95em;">${participants || "None"}</div>
												</div>
											</div>
										</div>

										${is_completed ? `
											<div style="padding: 5px 0; color:var(--text-color); font-weight:600; display: flex; align-items: center;">
												<i class="fa fa-check-circle" style="color:#1ee470ff; margin-right: 8px; font-size: 1.2em;"></i>
												This huddle is completed.
											</div>
										` : ""}

										${is_upcoming ? `
											<div style="padding: 5px 0; color:var(--text-color); font-weight:600; display: flex; align-items: center;">
												<i class="fa fa-clock-o" style="color:#0351b6ff; margin-right: 8px; font-size: 1.2em;"></i>
												This is an upcoming huddle.
											</div>
										` : ""}

										${is_live ? `
											<div style="padding: 5px 0; color:var(--text-color); font-weight:600; display: flex; align-items: center;">
												<i class="fa fa-video-camera" style="color:#eead45ff; margin-right: 8px; font-size: 1.2em;"></i>
												This huddle is live now.
											</div>
										` : ""}

										<div style="margin-top: 16px; display: flex; align-items: center;">
											${join_btn_html}
											<button class="btn btn-default huddle-view-btn" style="font-weight:600; padding:8px 16px;">
												${__("View Full Record")}
											</button>
										</div>
									</div>
								`,
							},
						],
					});

					d.show();

					// Wire up buttons after dialog renders
					d.$wrapper.find(".huddle-view-btn").on("click", function () {
						frappe.set_route("Form", "Huddle Meeting", doc.name);
						d.hide();
					});

					d.$wrapper.find(".huddle-join-btn").on("click", function () {
						d.hide();
						frappe.call({
							method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.join_meeting",
							args: { meeting_name: doc.name },
							freeze: true,
							callback: function (r) {
								if (r.message && r.message.join_url) {
									let jd = new frappe.ui.Dialog({
										title: doc.title,
										size: "extra-large",
										fields: [
											{
												fieldname: "jitsi_iframe",
												fieldtype: "HTML",
												options: `
													<iframe src="${r.message.join_url}"
														style="border:0; width:100%; height:calc(96vh - 70px); border-radius: 12px; background: #000;"
														allow="camera;microphone;fullscreen;display-capture;autoplay;clipboard-write"
														allowfullscreen>
													</iframe>
												`,
											},
										],
									});
									jd.$wrapper.find(".modal-dialog").css({
										"max-width": "96%",
										"margin": "10px auto",
									});
									jd.$wrapper.find(".modal-content").css("height", "96vh");
									jd.show();
								} else {
									frappe.msgprint(__("Error: Join URL not available"));
								}
							},
						});
					});
				},
			});

			return false;
		},
	},
};