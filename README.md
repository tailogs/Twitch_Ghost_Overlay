# 🎬 Twitch Ghost Overlay

[![Version](https://img.shields.io/badge/version-1.1.3-blue)]()
[![Platform](https://img.shields.io/badge/platform-Windows-blue)]()
[![Python](https://img.shields.io/badge/python-3.8%2B-green)]()

> Transparent, click-through Twitch chat overlay for Windows.

## ✨ Features

- 👻 Click-through overlay (mouse passes through)
- 🔝 Always on top
- 🔌 Anonymous Twitch IRC connection
- 🎨 Colored usernames & role badges (STREAMER/MOD/VIP/SUB)
- 🎬 Twitch emote support (animated & static)
- 🔔 Keyword alerts with custom images/GIFs
- 🌍 English / Russian UI
- 📊 Session statistics
- 💾 Auto-save settings

## 📦 Requirements

- Windows 10/11
- Python 3.8+

## 🚀 Installation

```bash
git clone https://github.com/tailogs/Twitch_Ghost_Overlay.git
cd Twitch_Ghost_Overlay
pip install -r requirements.txt
```

## ▶️ Usage

```bash
python twitch_ghost_overlay.py          # Normal run
python twitch_ghost_overlay.py shroud   # Auto-connect to channel
python twitch_ghost_overlay.py --test   # Test mode (no logs)
```

## 🖥️ Controls

- **F8** — Full restart
- **Right-click tray** — Open/Quit
- **Settings tab** — Adjust position, size, opacity, language

## 📁 Config Files

| File | Description |
|------|-------------|
| `overlay_config.json` | Position, size, opacity, font |
| `app_state.json` | Last channel & language |
| `alerts_config.json` | Keyword alerts |

## 🔒 Privacy

- Anonymous connection — no login required
- No chat logging to disk
- Usernames hashed in stats

## 📄 License

MIT

## 👨‍💻 Developer

**Tailogs**