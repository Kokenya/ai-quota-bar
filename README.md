# ⚡ AI Quota Bar

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Linux](https://img.shields.io/badge/platform-Linux%20(GNOME%20%7C%20AppIndicator)-orange.svg)](https://ubuntu.com/)

A lightweight, real-time Linux top bar indicator and CLI tool to monitor remaining usage, **5-hour rolling limits**, and **weekly quotas** for your favorite AI coding assistants:
- 🟣 **Claude Code** (Anthropic)
- 🔵 **Google Antigravity** (Gemini & 3P Claude/GPT models)
- 🟢 **OpenAI Codex CLI** (ChatGPT / Codex)
- 🐙 **GitHub Copilot** (CLI / API)

Always know exactly how much quota you have left before hitting the rate limit wall!

---

## 🖥️ Preview

### Top Bar Indicator
```text
C: 5h 100% W 1%   •   AG: 5h 90% W 96%   •   CX: 0%   •   GH: 100%
```

### Dropdown Menu (on click)
```text
── AI Quota & Usage Monitor ──
───────────────────────────────
🟣 Claude Code (Anthropic):
   ⏱️ 5-Hour Limit: 100% left
   📅 Weekly Limit: 1% left (in 4h 05m)
───────────────────────────────
🔵 Google Antigravity:
   ⏱️ Five Hour Limit Remaining: 90% left (in 3h 14m)
   📅 Weekly Limit Remaining: 96% left (in 6d 22h)
   [Claude and GPT models]
     • ⏱️ Five Hour Limit Remaining: 100% left (in 4h 59m)
     • 📅 Weekly Limit Remaining: 100% left (in 6d 23h)
   [Gemini 4 Argon]
     • 📅 Gemini 4 Argon Weekly Limit: 89% left (in 6d 21h)
───────────────────────────────
🟢 OpenAI Codex CLI (Free):
   ⏱️ Plan Quota: 0% left (in 11d 2h)
───────────────────────────────
🐙 GitHub Copilot:
   ⏱️ API Hourly Limit: 100% left
───────────────────────────────
🕒 Updated: 13:54:17
🔄 Refresh Now
❌ Quit
```

### Terminal CLI (`ai-usage`)
```text
========================================================================
                     AI QUOTA & USAGE MONITOR                           
========================================================================
PROVIDER / MODEL GROUP            LIMIT TYPE      REMAINING    RESETS IN
------------------------------------------------------------------------
🟣 Claude Code (Anthropic)        5-Hour Limit    100%        -           
                                 Weekly Limit      1%        in 4h 05m   
------------------------------------------------------------------------
🐙 GitHub Copilot                 API Hourly Limit 100%        -           
------------------------------------------------------------------------
🟢 OpenAI Codex CLI (Free)        Plan Quota        0%        in 11d 2h   
------------------------------------------------------------------------
🔵 Google Antigravity             Weekly Limit Remaining  96%        in 6d 22h   
                                 Five Hour Limit Remaining  90%        in 3h 14m   
  └ Claude and GPT models        Weekly Limit Remaining 100%        in 6d 23h   
                                 Five Hour Limit Remaining 100%        in 4h 59m   
  └ Gemini 4 Argon               Gemini 4 Argon Weekly Limit  89%        in 6d 21h   
------------------------------------------------------------------------
Updated: 2026-11-07 13:54:17 CET
========================================================================
```

---

## 🚀 Features

- **Multi-Assistant Tracking**: Supports Claude Code, Google Antigravity, OpenAI Codex CLI, and GitHub Copilot simultaneously.
- **Auto-Detection**: Only monitors the tools actually installed and authenticated on your machine.
- **Dual Limit Monitoring**: Tracks both short-term 5-hour burst limits and long-term weekly/monthly billing caps.
- **Smart Asynchronous Polling**: Non-blocking background worker thread with configurable refresh intervals (default: 2 minutes).
- **Systemd & Autostart Integration**: Starts automatically on login with zero user intervention required.
- **Single-Instance Protection**: Built-in file locking prevents duplicate icons.
- **CLI Included**: Run `ai-usage` anytime in your terminal for an instant colorized report.

---

## 📦 Installation

### Quick Install (Recommended)

Clone the repository and run the installer:

```bash
git clone https://github.com/Kokenya/ai-quota-bar.git ~/gh/ai-quota-bar
cd ~/gh/ai-quota-bar
./install.sh
```

The installer will:
1. Link `ai-usage` and `ai-quota-bar` to `~/.local/bin/`.
2. Configure and start the systemd user service (`ai-quota-bar.service`).
3. Set up the desktop autostart entry (`~/.config/autostart/ai-quota-bar.desktop`).
4. Install the native GNOME Shell Extension.

---

## ⌨️ CLI Usage

```bash
# Display formatted quota table
ai-usage

# Force an immediate refresh from APIs
ai-usage --refresh # or -r

# Watch mode: live updates every 5 seconds
ai-usage --watch   # or -w

# Output machine-readable JSON
ai-usage --json    # or -j

# Disable ANSI colors
ai-usage --no-color
```

---

## ⚙️ Configuration

Configuration is located at `~/.config/ai-quota-bar/config.json`:

```json
{
  "update_interval_seconds": 120,
  "topbar_format": "standard",
  "show_resets_in_menu": true,
  "enabled_providers": [
    "claude",
    "antigravity",
    "codex",
    "copilot"
  ],
  "colors_enabled": true
}
```

- `topbar_format`:
  - `"standard"`: `C: 5h 100% W 1%   •   AG: 5h 90% W 96%   •   CX: 0%   •   GH: 100%`
  - `"compact"`: `C 100%·1%   •   AG 90%·96%   •   CX 0%   •   GH 100%`

---

## 🔧 Managing the Service

```bash
# Check service status
systemctl --user status ai-quota-bar.service

# Restart service
systemctl --user restart ai-quota-bar.service

# View live service logs
journalctl --user -u ai-quota-bar.service -f
```

---

## 🗑️ Uninstallation

```bash
cd ~/gh/ai-quota-bar
./uninstall.sh
```

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
