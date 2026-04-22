# 🤝 Frappe Huddle

> Open source video meetings inside Frappe — powered by Jitsi Meet

[![Frappe](https://img.shields.io/badge/Built%20on-Frappe%20v15-blue)](https://frappeframework.com)
[![Jitsi](https://img.shields.io/badge/Powered%20by-Jitsi%20Meet-green)](https://jitsi.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Sakthi10122004/frappe-huddle/pulls)

---

## 🎯 What is Frappe Huddle?

**Frappe Huddle** is a free and open source video meeting app built on the [Frappe Framework](https://frappeframework.com). It brings the power of [Jitsi Meet](https://jitsi.org) directly inside your Frappe or ERPNext workspace — schedule meetings, invite participants, and join video calls without ever leaving your Frappe desk.

Think of it as **Google Calendar + Google Meet**, but fully open source and embedded inside Frappe.

---

## ✨ Features

- 📅 **Schedule meetings** — create meetings with title, date, duration and agenda
- 🎥 **Jitsi embedded** — video room opens inside Frappe, no new tab or app needed
- 🔐 **JWT authentication** — secure rooms, only invited users can join
- 📧 **Email invites** — beautiful HTML invite emails sent automatically to participants
- 👥 **Participant management** — track who is invited, accepted, declined and joined
- 📆 **Calendar view** — see all meetings in Frappe's built-in calendar
- ⚙️ **Huddle Settings** — configure your Jitsi domain, App ID, JWT secret from one place
- 🏢 **Self-hosted or JaaS** — works with `meet.jit.si`, JaaS (8x8) or your own Jitsi server
- 🔔 **Frappe notifications** — in-app alerts before meetings start
- 📱 **Mobile friendly** — works on Frappe mobile interface

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | Frappe v15 |
| Video | Jitsi Meet (self-hosted or JaaS) |
| Auth | JWT (JSON Web Tokens) |
| Frontend | Frappe UI + FullCalendar.js |
| Email | Frappe Email + Jinja templates |
| Language | Python 3 + JavaScript |

---

## 🚀 Installation

**Requirements**
- Frappe Bench v15+
- Python 3.10+
- Node.js 18+

**Steps**

```bash
# Go to your bench directory
cd /home/frappe/frappe-bench

# Get the app
bench get-app https://github.com/yourusername/frappe-huddle

# Install on your site
bench --site yoursite.local install-app frappe_huddle

# Run migrations
bench --site yoursite.local migrate

# Restart bench
bench restart
```

---

## ⚙️ Configuration

After installation go to:

```
yoursite.local/app/huddle-settings
```

Fill in the following:

| Setting | Description |
|---|---|
| Jitsi Domain | `meet.jit.si` or your self-hosted domain |
| App ID | From JaaS dashboard or your Jitsi server config |
| App Secret | JWT signing secret |
| Default Duration | Default meeting length in minutes |
| Enable Waiting Room | Approve participants before they join |
| Enable Recording | Available on self-hosted Jitsi with Jibri |
| Send Email Invite | Auto-send invite emails on meeting save |

---

## 🧩 DocTypes

### Huddle Meeting
The main document for scheduling and managing meetings.

| Field | Type | Description |
|---|---|---|
| Title | Data | Meeting title |
| Meeting Date | Datetime | Scheduled date and time |
| Duration | Int | Duration in minutes |
| Agenda | Text Editor | Meeting agenda |
| Jitsi Room | Data | Auto-generated room name |
| Jitsi URL | Data | Full meeting URL |
| Status | Select | Scheduled / In Progress / Completed |
| Participants | Table | Linked to Huddle Participant |

### Huddle Participant (Child Table)
Tracks all invitees for a meeting.

| Field | Type | Description |
|---|---|---|
| User | Link | Frappe User |
| Full Name | Data | Auto-fetched |
| Email | Data | Auto-fetched |
| Role | Select | Host / Participant |
| Invite Status | Select | Pending / Accepted / Declined |
| Joined | Check | Set when user joins |

### Huddle Settings (Single)
Global configuration for the app.

---

## 🔄 How it works

```
User schedules meeting
        ↓
Jitsi room name auto-generated
        ↓
JWT token signed with App Secret
        ↓
Email invites sent to participants
        ↓
Meeting appears on Frappe calendar
        ↓
User clicks "Join Meeting" on the form
        ↓
Jitsi room opens inside Frappe Desk (iframe)
        ↓
Meeting status updates to "In Progress"
```

---

## 🗺️ Roadmap

- [ ] Google Calendar sync
- [ ] Outlook Calendar sync
- [ ] WhatsApp invite notifications
- [ ] Meeting recordings saved to Frappe Files
- [ ] AI meeting summary (post-call notes)
- [ ] ERPNext CRM integration (link meetings to leads/customers)
- [ ] Guest join link (no Frappe account required)
- [ ] Recurring meetings
- [ ] Meeting analytics dashboard

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

```bash
# Fork the repo and clone
git clone https://github.com/yourusername/frappe-huddle
cd frappe-huddle

# Create a feature branch
git checkout -b feature/your-feature-name

# Make your changes and commit
git commit -m "feat: add your feature"

# Push and open a Pull Request
git push origin feature/your-feature-name
```

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a PR.

---

## 🐛 Reporting Issues

Found a bug or have a feature request?
Open an issue at [github.com/yourusername/frappe-huddle/issues](https://github.com/yourusername/frappe-huddle/issues)

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

- [Frappe Framework](https://frappeframework.com) — the backbone of this app
- [Jitsi Meet](https://jitsi.org) — the open source video engine
- [8x8 JaaS](https://jaas.8x8.vc) — Jitsi as a Service platform
- [ERPNext](https://erpnext.com) — inspiration for open source enterprise tools

---

<p align="center">Built with ❤️ on Frappe · Powered by Jitsi</p>
