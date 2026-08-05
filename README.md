# 📞 Frappe Huddle

> Open source meeting tracking system inside Frappe

[![Frappe](https://img.shields.io/badge/Built%20on-Frappe-blue)](https://frappeframework.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 What Is Frappe Huddle?

**Frappe Huddle** is a meeting management and participant tracking system built on the [Frappe Framework](https://frappeframework.com). It provides a clean, structured way to schedule meetings, track who joined, who left, and whether meetings are active — all from within your Frappe workspace.

## ✨ Features

- 📅 **Meeting scheduling** — create and schedule meetings with a title, host, and date
- 👥 **Participant tracking** — track who joined, who left, and who disconnected
- 🔄 **Status lifecycle** — meetings flow through `Scheduled → Live → Ended` or `Cancelled`
- 🔒 **Unique room IDs** — every meeting gets a unique auto-generated room identifier
- ⚙️ **Huddle Settings** — configure default duration, reminders, and email notifications
- 👤 **Role-based access** — Huddle Admin, Huddle User, and Huddle Guest roles

## 📦 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Frappe Framework (Python) |
| Frontend | Frappe Desk + Custom Portal |
| Database | MariaDB |

## 🚀 Installation

```bash
bench get-app https://github.com/Sakthi10122004/frappe-huddle.git
bench --site your-site install-app frappe_huddle
```

## 📋 DocTypes

### Huddle Meeting

The core meeting record.

| Field | Type | Description |
|-------|------|-------------|
| Title | Data | Meeting name |
| Room ID | Data | Auto-generated unique identifier |
| Host | Link → User | Meeting creator |
| Status | Select | Scheduled / Live / Ended / Cancelled |
| Scheduled At | Datetime | When the meeting is planned |
| Started At | Datetime | When the meeting actually started |
| Ended At | Datetime | When the meeting ended |
| Is Active | Check | Whether the meeting is currently active |

### Huddle Participant

Tracks individual participation in meetings.

| Field | Type | Description |
|-------|------|-------------|
| Meeting | Link → Huddle Meeting | Which meeting |
| User | Link → User | Which user |
| State | Select | Joined / Left / Disconnected |
| Joined At | Datetime | When the user joined |
| Left At | Datetime | When the user left |
| Is Active | Check | Whether the user is currently in the meeting |

## 📄 License

MIT

---

<p align="center">Built with ❤️ on Frappe</p>
