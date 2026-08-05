// Copyright (c) 2026, Sakthi and contributors
// Frappe Huddle — Google Calendar-style calendar view

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

	get_events_method:
		"frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.get_events",

	options: {
		editable: false,
		eventStartEditable: false,
		eventDurationEditable: false,
		selectable: true,
		droppable: false,
		eventLimit: false,        // show ALL events — no "+N more" collapse
		slotDuration: "00:30:00",
		scrollTime: "08:00:00",
		nowIndicator: true,
		height: "auto",

		// ── Inject Google-Calendar-style CSS once ──────────────────────────
		viewRender: function () {
			if (document.getElementById("huddle-cal-style")) return;

			const style = document.createElement("style");
			style.id = "huddle-cal-style";
			style.textContent = `
				/* ── Toolbar ── */
				.fc-toolbar { padding: 12px 16px !important; gap: 10px; }
				.fc-toolbar h2 {
					font-size: 20px !important;
					font-weight: 700 !important;
					color: #1a1a2e !important;
					letter-spacing: -0.3px;
				}
				.fc-button {
					background: #fff !important;
					border: 1.5px solid #e2e8f0 !important;
					color: #475569 !important;
					border-radius: 8px !important;
					font-weight: 600 !important;
					font-size: 13px !important;
					padding: 6px 14px !important;
					box-shadow: 0 1px 3px rgba(0,0,0,.06) !important;
					transition: all .15s ease !important;
				}
				.fc-button:hover {
					background: #f8fafc !important;
					border-color: #cbd5e1 !important;
					color: #1e293b !important;
					transform: translateY(-1px);
					box-shadow: 0 3px 8px rgba(0,0,0,.09) !important;
				}
				.fc-button-primary.fc-button-active,
				.fc-button-primary:not(:disabled).fc-button-active {
					background: linear-gradient(135deg, #0ea5a0, #0891b2) !important;
					border-color: transparent !important;
					color: #fff !important;
					box-shadow: 0 4px 14px rgba(14,165,160,.35) !important;
				}
				.fc-today-button {
					background: linear-gradient(135deg, #0ea5a0, #0891b2) !important;
					border-color: transparent !important;
					color: #fff !important;
					border-radius: 8px !important;
					box-shadow: 0 4px 14px rgba(14,165,160,.3) !important;
				}

				/* ── Grid ── */
				.fc-bg td, .fc-bg th { border-color: #eef2f7 !important; }
				.fc-axis { color: #94a3b8 !important; font-size: 11px !important; font-weight: 600 !important; }
				.fc-day-header {
					padding: 10px 0 !important;
					font-size: 12px !important;
					font-weight: 700 !important;
					color: #64748b !important;
					text-transform: uppercase !important;
					letter-spacing: .8px !important;
					border-bottom: 2px solid #eef2f7 !important;
				}
				.fc-today {
					background: rgba(14,165,160,.04) !important;
				}
				.fc-day-number {
					font-size: 13px !important;
					font-weight: 700 !important;
					color: #475569 !important;
					padding: 6px 10px !important;
				}
				td.fc-today .fc-day-number {
					background: linear-gradient(135deg, #0ea5a0, #0891b2) !important;
					color: #fff !important;
					border-radius: 50% !important;
					width: 28px !important;
					height: 28px !important;
					display: flex !important;
					align-items: center !important;
					justify-content: center !important;
					margin: 4px 6px !important;
					font-size: 12px !important;
					box-shadow: 0 3px 10px rgba(14,165,160,.3) !important;
				}
				.fc-now-indicator-line {
					border-color: #f43f5e !important;
					border-width: 2px !important;
				}
				.fc-now-indicator-arrow {
					border-top-color: #f43f5e !important;
				}

				/* ── Base event chip ── */
				.fc-event {
					border: none !important;
					border-radius: 6px !important;
					padding: 3px 8px !important;
					font-size: 12px !important;
					font-weight: 600 !important;
					cursor: pointer !important;
					transition: transform .15s ease, box-shadow .15s ease !important;
					overflow: hidden !important;
				}
				.fc-event:hover {
					transform: translateY(-1px) scale(1.01) !important;
					box-shadow: 0 6px 20px rgba(0,0,0,.15) !important;
					z-index: 99 !important;
				}
				.fc-event .fc-title { font-weight: 600 !important; }
				.fc-event .fc-time  { font-size: 11px !important; opacity: .85; }

				/* ── Status colours ── */
				.huddle-ev-scheduled {
					background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
					color: #fff !important;
					box-shadow: 0 2px 8px rgba(59,130,246,.3) !important;
					border-left: 3px solid #1d4ed8 !important;
				}
				.huddle-ev-inprogress {
					background: linear-gradient(135deg, #f59e0b, #d97706) !important;
					color: #fff !important;
					box-shadow: 0 2px 8px rgba(245,158,11,.3) !important;
					border-left: 3px solid #b45309 !important;
					animation: huddle-live-pulse 2.5s ease-in-out infinite;
				}
				@keyframes huddle-live-pulse {
					0%, 100% { box-shadow: 0 2px 8px rgba(245,158,11,.3); }
					50%       { box-shadow: 0 2px 18px rgba(245,158,11,.55); }
				}
				.huddle-ev-completed {
					background: #f1f5f9 !important;
					color: #64748b !important;
					border-left: 3px solid #cbd5e1 !important;
					box-shadow: none !important;
				}
				.huddle-ev-cancelled {
					background: #fee2e2 !important;
					color: #ef4444 !important;
					border-left: 3px solid #fca5a5 !important;
					opacity: .75 !important;
					text-decoration: line-through !important;
				}

				/* ── Popup card ── */
				.huddle-popup-overlay {
					position: fixed;
					inset: 0;
					z-index: 8000;
					pointer-events: none;
				}
				.huddle-popup {
					position: fixed;
					z-index: 8001;
					width: 340px;
					background: #fff;
					border-radius: 16px;
					box-shadow:
						0 0 0 1px rgba(0,0,0,.06),
						0 20px 60px rgba(0,0,0,.18),
						0 8px 20px rgba(0,0,0,.1);
					overflow: hidden;
					animation: huddle-pop-in .22s cubic-bezier(.34,1.56,.64,1);
					pointer-events: all;
					font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
				}
				@keyframes huddle-pop-in {
					from { opacity: 0; transform: scale(.88) translateY(8px); }
					to   { opacity: 1; transform: scale(1) translateY(0); }
				}
				.huddle-popup-header {
					padding: 18px 20px 14px;
					position: relative;
				}
				.huddle-popup-close {
					position: absolute;
					top: 14px; right: 14px;
					width: 28px; height: 28px;
					border-radius: 50%;
					background: rgba(0,0,0,.06);
					border: none;
					cursor: pointer;
					display: flex; align-items: center; justify-content: center;
					font-size: 16px; color: #64748b;
					transition: background .15s;
				}
				.huddle-popup-close:hover { background: rgba(0,0,0,.12); color: #1e293b; }
				.huddle-popup-status-bar {
					height: 4px;
					width: 100%;
					position: absolute;
					top: 0; left: 0;
					border-radius: 16px 16px 0 0;
				}
				.huddle-popup-title {
					font-size: 16px;
					font-weight: 700;
					color: #1e293b;
					line-height: 1.3;
					margin: 0 0 10px;
					padding-right: 32px;
				}
				.huddle-popup-pill {
					display: inline-flex;
					align-items: center;
					gap: 5px;
					padding: 3px 10px;
					border-radius: 100px;
					font-size: 11px;
					font-weight: 700;
					letter-spacing: .3px;
					text-transform: uppercase;
				}
				.huddle-pill-scheduled  { background:#eff6ff; color:#2563eb; }
				.huddle-pill-inprogress { background:#fef3c7; color:#d97706; }
				.huddle-pill-completed  { background:#f1f5f9; color:#64748b; }
				.huddle-pill-cancelled  { background:#fee2e2; color:#ef4444; }
				.huddle-live-dot {
					width: 7px; height: 7px;
					background: currentColor;
					border-radius: 50%;
					animation: huddle-blink 1.4s ease-in-out infinite;
				}
				@keyframes huddle-blink {
					0%,100% { opacity:1; } 50% { opacity:.3; }
				}
				.huddle-popup-body {
					padding: 0 20px 18px;
				}
				.huddle-popup-row {
					display: flex;
					align-items: center;
					gap: 10px;
					padding: 8px 0;
					border-bottom: 1px solid #f1f5f9;
					font-size: 13px;
					color: #475569;
				}
				.huddle-popup-row:last-child { border-bottom: none; }
				.huddle-popup-row-icon {
					width: 32px; height: 32px;
					border-radius: 8px;
					background: #f8fafc;
					display: flex; align-items: center; justify-content: center;
					font-size: 15px;
					flex-shrink: 0;
				}
				.huddle-popup-row-label {
					font-size: 10px;
					font-weight: 700;
					text-transform: uppercase;
					letter-spacing: .7px;
					color: #94a3b8;
					margin-bottom: 1px;
				}
				.huddle-popup-row-value {
					font-size: 13px;
					font-weight: 600;
					color: #1e293b;
				}
				.huddle-popup-avatars {
					display: flex;
					align-items: center;
					flex-wrap: wrap;
					gap: 4px;
					margin-top: 2px;
				}
				.huddle-av {
					width: 26px; height: 26px;
					border-radius: 50%;
					display: flex; align-items: center; justify-content: center;
					font-size: 10px; font-weight: 700; color: #fff;
					border: 2px solid #fff;
					flex-shrink: 0;
				}
				.huddle-popup-footer {
					padding: 14px 20px;
					background: #f8fafc;
					border-top: 1px solid #eef2f7;
					display: flex;
					gap: 8px;
				}
				.huddle-btn {
					flex: 1;
					padding: 9px 14px;
					border-radius: 8px;
					font-size: 13px;
					font-weight: 600;
					border: none;
					cursor: pointer;
					transition: all .15s ease;
					display: flex; align-items: center; justify-content: center; gap: 6px;
				}
				.huddle-btn-primary {
					background: linear-gradient(135deg, #0ea5a0, #0891b2);
					color: #fff;
					box-shadow: 0 4px 14px rgba(14,165,160,.3);
				}
				.huddle-btn-primary:hover {
					transform: translateY(-1px);
					box-shadow: 0 6px 20px rgba(14,165,160,.4);
				}
				.huddle-btn-ghost {
					background: #fff;
					color: #475569;
					border: 1.5px solid #e2e8f0;
				}
				.huddle-btn-ghost:hover {
					border-color: #0ea5a0;
					color: #0ea5a0;
					background: rgba(14,165,160,.05);
				}
				.huddle-jitsi-dialog .modal-dialog {
					max-width: 96% !important;
					margin: 10px auto !important;
				}
				.huddle-jitsi-dialog .modal-content {
					height: 96vh !important;
					border-radius: 16px !important;
					overflow: hidden !important;
				}
				.huddle-jitsi-dialog .modal-header {
					background: #1a1a2e !important;
					color: #fff !important;
					border-bottom: none !important;
				}
				.huddle-jitsi-dialog .close { color: #fff !important; }
			`;
			document.head.appendChild(style);
		},

		// ── Paint each event chip ──────────────────────────────────────────
		eventRender: function (event, $el) {
			const status = event.status || "Scheduled";
			const classMap = {
				"Scheduled":   "huddle-ev-scheduled",
				"In Progress": "huddle-ev-inprogress",
				"Completed":   "huddle-ev-completed",
				"Cancelled":   "huddle-ev-cancelled",
			};

			$el.removeClass("fc-event")
				.addClass("fc-event " + (classMap[status] || "huddle-ev-scheduled"));

			// Time badge
			const start = event.start && event.start.format
				? event.start.format("h:mm A")
				: "";

			// Live pulse dot for In Progress
			const liveDot = status === "In Progress"
				? `<span style="
						display:inline-block;width:7px;height:7px;
						border-radius:50%;background:#fff;margin-right:5px;
						animation:huddle-blink 1.4s ease-in-out infinite;
						vertical-align:middle;
					"></span>`
				: "";

			$el.find(".fc-content").html(`
				<div style="display:flex;align-items:center;gap:4px;overflow:hidden;">
					${liveDot}
					<span class="fc-time" style="font-size:11px;opacity:.85;flex-shrink:0;">${start}</span>
					<span class="fc-title" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${event.title || ""}</span>
				</div>
			`);

			$el.attr("title", `${event.title} · ${status}`);
		},

		// ── Click → rich Google-Calendar popup ────────────────────────────
		eventClick: function (calEvent, jsEvent, view) {
			// Remove any existing popup
			$(".huddle-popup, .huddle-popup-overlay").remove();

			const name = calEvent.name || calEvent.id;
			if (!name) return false;

			frappe.call({
				method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.get_meeting_details",
				args: { meeting_name: name },
				callback: function (r) {
					if (!r.message) {
						frappe.show_alert({ message: __("Could not load meeting details."), indicator: "red" });
						return;
					}
					const doc = r.message;
					_showHuddlePopup(doc, jsEvent);
				},
			});

			return false;
		},

		// ── Click on empty day → open new meeting form ─────────────────────
		dayClick: function (date) {
			frappe.new_doc("Huddle Meeting", {
				meeting_date: date.format("YYYY-MM-DD HH:mm:ss"),
			});
		},
	},
};

/* ─────────────────────────────────────────────────────────────────────────────
   Popup renderer — completely outside FullCalendar options so it can be
   called from eventClick without `this` scope issues.
   ───────────────────────────────────────────────────────────────────────────── */
function _showHuddlePopup(doc, jsEvent) {
	const status = doc.status || "Scheduled";

	// Status styling
	const barColor = {
		"Scheduled":   "linear-gradient(90deg,#3b82f6,#2563eb)",
		"In Progress": "linear-gradient(90deg,#f59e0b,#d97706)",
		"Completed":   "linear-gradient(90deg,#10b981,#059669)",
		"Cancelled":   "linear-gradient(90deg,#ef4444,#dc2626)",
	}[status] || "linear-gradient(90deg,#94a3b8,#64748b)";

	const pillClass = {
		"Scheduled":   "huddle-pill-scheduled",
		"In Progress": "huddle-pill-inprogress",
		"Completed":   "huddle-pill-completed",
		"Cancelled":   "huddle-pill-cancelled",
	}[status] || "huddle-pill-scheduled";

	const liveDot = status === "In Progress"
		? `<span class="huddle-live-dot"></span>` : "";

	// Dates / times (Convert to user local timezone to show the correct local date/time)
	const localMeetingDate = doc.meeting_date ? frappe.datetime.convert_to_user_tz(doc.meeting_date) : null;
	const localEndDate = doc.end_date ? frappe.datetime.convert_to_user_tz(doc.end_date) : null;

	const startDt  = localMeetingDate
		? frappe.datetime.global_date_format(localMeetingDate) : "—";
	const startTm  = localMeetingDate
		? frappe.datetime.get_time(localMeetingDate).slice(0,5) : "";
	const endTm    = localEndDate
		? frappe.datetime.get_time(localEndDate).slice(0,5) : "";
	const timeStr  = startTm ? (endTm ? `${startTm} – ${endTm}` : startTm) : "—";

	// Participants
	const participants = (doc.participants || []).filter(p => p.full_name);
	const AVATAR_COLORS = [
		"#0ea5a0","#6366f1","#f43f5e","#f59e0b","#8b5cf6","#10b981",
	];
	const avatarHTML = participants.slice(0, 6).map((p, i) => {
		const initial = (p.full_name || "?")[0].toUpperCase();
		const bg = AVATAR_COLORS[i % AVATAR_COLORS.length];
		return `<div class="huddle-av" style="background:${bg};" title="${p.full_name}">${initial}</div>`;
	}).join("");
	const extraCount = participants.length > 6 ? participants.length - 6 : 0;
	const extraHTML  = extraCount
		? `<div class="huddle-av" style="background:#94a3b8;">+${extraCount}</div>` : "";

	const participantBlock = participants.length
		? `<div class="huddle-popup-avatars">${avatarHTML}${extraHTML}
			   <span style="font-size:12px;color:#64748b;margin-left:4px;">${participants.length} participant${participants.length > 1 ? "s" : ""}</span>
		   </div>`
		: `<span style="font-size:12px;color:#94a3b8;">No participants</span>`;

	// Action buttons
	const canJoin = status === "Scheduled" || status === "In Progress";
	const joinLabel = status === "In Progress" ? "🔴 Join Live" : "▶ Join Meeting";

	const html = `
		<div class="huddle-popup-overlay" id="huddle-overlay"></div>
		<div class="huddle-popup" id="huddle-popup">
			<div class="huddle-popup-status-bar" style="background:${barColor};"></div>

			<div class="huddle-popup-header">
				<button class="huddle-popup-close" id="huddle-popup-close">✕</button>
				<h3 class="huddle-popup-title">${frappe.utils.escape_html(doc.title || "Meeting")}</h3>
				<span class="huddle-popup-pill ${pillClass}">
					${liveDot}${status}
				</span>
			</div>

			<div class="huddle-popup-body">
				<div class="huddle-popup-row">
					<div class="huddle-popup-row-icon">📅</div>
					<div>
						<div class="huddle-popup-row-label">Date</div>
						<div class="huddle-popup-row-value">${startDt}</div>
					</div>
				</div>
				<div class="huddle-popup-row">
					<div class="huddle-popup-row-icon">🕐</div>
					<div>
						<div class="huddle-popup-row-label">Time · ${doc.duration || 60} min</div>
						<div class="huddle-popup-row-value">${timeStr}</div>
					</div>
				</div>
				<div class="huddle-popup-row">
					<div class="huddle-popup-row-icon">👥</div>
					<div style="flex:1;">
						<div class="huddle-popup-row-label">Participants</div>
						${participantBlock}
					</div>
				</div>
				${doc.jitsi_url ? `
				<div class="huddle-popup-row">
					<div class="huddle-popup-row-icon">🔗</div>
					<div style="flex:1; min-width:0;">
						<div class="huddle-popup-row-label">Meeting ID</div>
						<div class="huddle-popup-row-value" style="font-size:11px;font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${doc.name}</div>
					</div>
				</div>` : ""}
			</div>

			<div class="huddle-popup-footer">
				<button class="huddle-btn huddle-btn-ghost" id="huddle-popup-view">
					📋 Open Record
				</button>
				${canJoin ? `
				<button class="huddle-btn huddle-btn-primary" id="huddle-popup-join">
					${joinLabel}
				</button>` : ""}
			</div>
		</div>
	`;

	$("body").append(html);

	// ── Position the popup near the click, staying inside viewport ──────
	const PW = 340, PH = 420;
	const vw = $(window).width(), vh = $(window).height();
	let left = jsEvent.pageX + 12;
	let top  = jsEvent.pageY - 60;

	if (left + PW + 20 > vw) left = jsEvent.pageX - PW - 12;
	if (top + PH + 20 > vh) top  = vh - PH - 20;
	if (top < 10) top = 10;
	if (left < 10) left = 10;

	$("#huddle-popup").css({ top, left });

	// ── Wire up buttons ────────────────────────────────────────────────
	const closePopup = () => {
		$(".huddle-popup, .huddle-popup-overlay").remove();
		$(document).off("page-change.huddlepopup");
		$(document).off("keydown.huddlepopup");
	};

	$("#huddle-popup-close, #huddle-overlay").on("click", closePopup);

	$("#huddle-popup-view").on("click", function () {
		closePopup();
		frappe.set_route("Form", "Huddle Meeting", doc.name);
	});

	$("#huddle-popup-join").on("click", function () {
		closePopup();
		frappe.set_route("Form", "Huddle Meeting", doc.name);
	});

	// Close on Escape
	$(document).on("keydown.huddlepopup", function (e) {
		if (e.key === "Escape") closePopup();
	});

	// Close automatically if user navigates away (page changes in Frappe Desk)
	$(document).on("page-change.huddlepopup", function () {
		closePopup();
	});
}