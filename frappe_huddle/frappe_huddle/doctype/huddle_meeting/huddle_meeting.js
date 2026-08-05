frappe.ui.form.on("Huddle Meeting", {
    setup: function(frm) {
        // any initial setup
    },

    refresh: function(frm) {
        if (frm.is_new() && !frm.doc.created_by_user) {
            frm.set_value("created_by_user", frappe.session.user);
        }

        // Show status indicator with correct color
        if (!frm.is_new()) {
            let indicator_color = "blue";
            if (frm.doc.status === "Live") indicator_color = "green";
            if (frm.doc.status === "Ended") indicator_color = "darkgrey";
            if (frm.doc.status === "Cancelled") indicator_color = "red";
            if (frm.doc.status === "Expired") indicator_color = "orange";
            frm.page.set_indicator(frm.doc.status, indicator_color);
            
            // Add "Cancel Meeting" button if status is Scheduled or Live
            if (["Scheduled", "Live"].includes(frm.doc.status)) {
                frm.add_custom_button(__("Cancel Meeting"), function() {
                    frappe.confirm(__("Are you sure you want to cancel this meeting?"), function() {
                        frappe.call({
                            method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.cancel_meeting",
                            args: { meeting_name: frm.doc.name },
                            callback: function(r) {
                                if (r.message) {
                                    frm.reload_doc();
                                }
                            }
                        });
                    });
                }).removeClass("btn-default").addClass("btn-danger");
            }

            // Start / End Meeting Buttons for the Host
            if (frm.doc.host === frappe.session.user || frappe.session.user === "Administrator") {
                if (frm.doc.status === "Scheduled") {
                    frm.add_custom_button(__("Start Meeting"), function() {
                        frappe.call({
                            method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.start_meeting_api",
                            args: { meeting_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Preparing LiveKit room..."),
                            callback: function(r) {
                                if (r.message) {
                                    frm.reload_doc();
                                    frappe.show_alert({message: __("Meeting Started!"), indicator: "green"});

                                    // Auto-join the host after starting
                                    if (r.message.room_url) {
                                        frappe.confirm(
                                            __("Meeting room is ready. Join now?"),
                                            function() {
                                                frm.events.open_livekit_room(frm);
                                            }
                                        );
                                    }
                                }
                            }
                        });
                    }).removeClass("btn-default").addClass("btn-primary");
                }
                if (frm.doc.status === "Live") {
                    frm.add_custom_button(__("End Meeting"), function() {
                        frappe.confirm(__("Are you sure you want to end this meeting for everyone?"), function() {
                            frappe.call({
                                method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.end_meeting_api",
                                args: { meeting_name: frm.doc.name },
                                freeze: true,
                                freeze_message: __("Ending meeting..."),
                                callback: function(r) {
                                    if (r.message) {
                                        frm.reload_doc();
                                        frappe.show_alert({message: __("Meeting Ended."), indicator: "orange"});
                                    }
                                }
                            });
                        });
                    }).removeClass("btn-default").addClass("btn-danger");
                }
            }

            // Join Meeting Button — only when Live and room is ready
            if (frm.doc.status === "Live" && frm.doc.room_url) {
                frm.add_custom_button(__("Join Meeting"), function() {
                    frm.events.open_livekit_room(frm);
                }).removeClass("btn-default").addClass("btn-success");
            } else if (frm.doc.status === "Scheduled") {
                frm.add_custom_button(__("Join Meeting"), function() {
                    frappe.msgprint(__("Meeting hasn't started yet. Please wait for the host to start it."));
                }).removeClass("btn-default").addClass("btn-default-dark");
            }

            // Add "Resend Invites" button under Actions
            frm.page.add_action_item(__("Resend Invites"), function() {
                frappe.call({
                    method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.resend_invites",
                    args: { meeting_name: frm.doc.name },
                    callback: function(r) {
                        if (r.message) {
                            frappe.show_alert({message: r.message, indicator: "green"});
                        }
                    }
                });
            });

            // Add "Copy Meeting Link" button
            frm.add_custom_button(__("Copy Meeting Link"), function() {
                let url = frappe.urllib.get_base_url() + "/app/huddle-meeting/" + frm.doc.name;
                frappe.utils.copy_to_clipboard(url);
            });
            
            // Room info display
            if (frm.doc.room_url && frm.doc.status === "Live") {
                frm.set_df_property("room_id", "hidden", 0);
                frm.set_df_property("room_url", "hidden", 0);
                frm.dashboard.add_indicator(__("LiveKit Room Active"), "green");
            } else if (frm.doc.status === "Scheduled") {
                frm.set_df_property("room_id", "hidden", 1);
                frm.set_df_property("room_url", "hidden", 1);
                frm.dashboard.add_indicator(__("Room will be active when host starts the meeting"), "blue");
            } else {
                // Ended / Cancelled — show room_id if it existed
                frm.set_df_property("room_url", "hidden", !frm.doc.room_url);
            }
        }
    },

    /**
     * Open the LiveKit meeting room in a full-screen overlay.
     * Calls join_meeting to get a token, then loads LiveKit Meet.
     */
    open_livekit_room: function(frm) {
        frappe.call({
            method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.join_meeting",
            args: { meeting_name: frm.doc.name },
            freeze: true,
            freeze_message: __("Joining meeting..."),
            callback: function(r) {
                if (!r.message || !r.message.success) return;

                let data = r.message;
                if (!data.room_url) {
                    frappe.msgprint(__("Room URL not available. Please ask the host to start the meeting."));
                    return;
                }

                // Build the join URL with token
                let join_url = data.room_url;
                if (data.token) {
                    join_url += "&token=" + data.token;
                }

                // Lock scroll
                $("html, body").css({
                    overflow: "hidden",
                    height: "100%",
                    margin: 0,
                    padding: 0
                });

                // ── Full-screen overlay with LiveKit iframe ──
                let overlay = $(`
    <div id="huddle-livekit-overlay" style="
        position: fixed;
        inset: 0;
        width: 100vw;
        height: 100dvh;
        max-height: 100dvh;
        z-index: 99999;
        background: #0f172a;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        font-family: 'Inter', 'DM Sans', sans-serif;
    ">
        <!-- Top Header -->
        <div style="
            height: 64px;
            min-height: 64px;
            background: rgba(15, 23, 42, 0.96);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid rgba(255,255,255,0.06);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 22px;
            color: white;
        ">
            <!-- Left -->
            <div style="display:flex; align-items:center; gap:14px;">
                <!-- Logo -->
                <div style="
                    width: 38px;
                    height: 38px;
                    border-radius: 12px;
                    background: linear-gradient(135deg,#14b8a6,#0ea5e9);
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    font-size:16px;
                    font-weight:700;
                    box-shadow: 0 4px 18px rgba(14,165,233,.35);
                ">
                    H
                </div>

                <!-- Meeting Info -->
                <div style="display:flex; flex-direction:column;">
                    <span style="font-size:15px; font-weight:600; color:#fff; line-height:1.2;">
                        ${frm.doc.title}
                    </span>
                    <span style="font-size:12px; color:#94a3b8;">
                        Meeting ID: ${frm.doc.name}
                    </span>
                </div>
            </div>

            <!-- Center -->
            <div style="
                display:flex;
                align-items:center;
                gap:10px;
                background: rgba(255,255,255,0.05);
                padding: 8px 14px;
                border-radius: 999px;
                border:1px solid rgba(255,255,255,0.06);
            ">
                <span style="
                    width:10px;
                    height:10px;
                    border-radius:50%;
                    background:#22c55e;
                    display:inline-block;
                    box-shadow:0 0 10px #22c55e;
                "></span>
                <span style="font-size:13px; color:#e2e8f0; font-weight:500;">
                    Live Meeting
                </span>
            </div>

            <!-- Right -->
            <div style="display:flex; align-items:center; gap:12px;">
                <button id="huddle-custom-close-btn" style="
                    padding:10px 18px;
                    border:none;
                    border-radius:12px;
                    background:rgba(255,255,255,0.1);
                    color:white;
                    font-size:13px;
                    font-weight:600;
                    cursor:pointer;
                    transition: background 0.2s;
                " onmouseover="this.style.background='rgba(255,255,255,0.2)'" onmouseout="this.style.background='rgba(255,255,255,0.1)'">
                    Close
                </button>

                <!-- Fullscreen -->
                <button id="huddle-fullscreen-btn" style="
                    width:40px;
                    height:40px;
                    border:none;
                    border-radius:12px;
                    background:rgba(255,255,255,0.06);
                    color:white;
                    cursor:pointer;
                    transition:.2s;
                ">
                    ⛶
                </button>
            </div>
        </div>

        <!-- Main Meeting Area -->
        <div style="
            flex:1;
            position:relative;
            background:#020617;
            overflow:hidden;
        ">
            <!-- Decorative Glow -->
            <div style="
                position:absolute;
                width:500px;
                height:500px;
                background: radial-gradient(circle, rgba(14,165,233,.18), transparent 70%);
                top:-200px;
                right:-120px;
                pointer-events:none;
            "></div>

            <!-- Iframe -->
            <iframe 
                id="huddle-livekit-iframe"
                src="${join_url}"
                allow="camera; microphone; display-capture; autoplay; clipboard-write"
                style="
                    width:100%;
                    height:100%;
                    border:none;
                    background:#000;
                    display:block;
                    overflow:hidden;
                "
            ></iframe>
        </div>
    </div>
`);

                // Remove existing if any, then append new overlay
                $("#huddle-livekit-overlay").remove();
                $("body").append(overlay);

                let overlay_closed = false;

                // Helper to close overlay cleanly without disconnecting
                function close_overlay() {
                    if (overlay_closed) return;
                    overlay_closed = true;

                    // Cleanup event listeners
                    $(window).off("message.huddle");

                    // Remove overlay
                    $("#huddle-livekit-overlay").remove();

                    // Restore scroll
                    $("html, body").css({
                        overflow: "",
                        height: "",
                        margin: "",
                        padding: ""
                    });
                }

                // Helper to handle meeting disconnect
                function handle_disconnect() {
                    close_overlay();

                    frappe.call({
                        method: "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.leave_meeting",
                        args: { meeting_name: frm.doc.name },
                        callback: function() {
                            frm.reload_doc();
                            frappe.show_alert({message: __("You left the meeting."), indicator: "blue"});
                        }
                    });
                }

                // Fullscreen binding
                $("#huddle-fullscreen-btn").on("click", function () {
                    let elem = document.getElementById("huddle-livekit-overlay");
                    if (!document.fullscreenElement) {
                        elem.requestFullscreen?.();
                    } else {
                        document.exitFullscreen?.();
                    }
                });

                // Close button binding (just closes overlay, does not disconnect)
                $("#huddle-custom-close-btn").on("click", function () {
                    close_overlay();
                });

                // Listen for LiveKit iframe disconnect events
                $(window).on("message.huddle", function(event) {
                    let data = event.originalEvent.data;
                    
                    if (typeof data === "string") {
                        try {
                            data = JSON.parse(data);
                        } catch (e) {
                            // Not JSON, keep as string
                        }
                    }

                    const is_disconnect =
                        data === "leave" ||
                        data === "disconnect" ||
                        data === "disconnected" ||
                        (
                            data &&
                            typeof data === "object" &&
                            (
                                data.event === "leave" ||
                                data.event === "disconnect" ||
                                data.type === "disconnect" ||
                                data.source === "lk-meet-component"
                            )
                        );

                    if (is_disconnect) {
                        handle_disconnect();
                    }
                });

                frappe.show_alert({message: __("Connected to LiveKit Room"), indicator: "green"});
            }
        });
    },

    duration: function(frm) {
        // Warn if duration exceeds settings max
        if (frm.doc.duration > 480) {
            frappe.msgprint(__("Duration seems unusually long. Please check."));
        }
        frm.trigger("meeting_date");
    },

    meeting_date: function(frm) {
        // Auto calculate end_date client side
        if (frm.doc.meeting_date && frm.doc.duration) {
            let end_date = frappe.datetime.add_time(frm.doc.meeting_date, frm.doc.duration, "minutes");
            frm.set_value("end_date", end_date);
        }
    },

    is_recurring: function(frm) {
        // Show/hide recurrence fields happens automatically via depends_on in JSON, but we can clear them here if unchecked
        if (!frm.doc.is_recurring) {
            frm.set_value("recurrence_rule", "");
            frm.set_value("recurrence_end_date", "");
        }
    },

    linked_doctype: function(frm) {
        // When linked_doctype is set, show linked_docname as dynamic link
        if (!frm.doc.linked_doctype) {
            frm.set_value("linked_docname", "");
        }
    }
});

frappe.ui.form.on("Huddle Participant", {
    user: function(frm, cdt, cdn) {
        // Auto fetch full_name and email from User
        let row = locals[cdt][cdn];
        if (row.user) {
            frappe.db.get_value("User", row.user, ["full_name", "email"], function(r) {
                if (r) {
                    frappe.model.set_value(cdt, cdn, "full_name", r.full_name);
                    frappe.model.set_value(cdt, cdn, "email", r.email);
                }
            });
        }
    }
});
