# 🎬 Twitch Chat

Transparent, click-through Twitch chat overlay for Windows.  
Shows chat on top of games and apps without blocking mouse input.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## ✨ Features

- 👻 Click-through overlay
- 🔝 Always on top
- 🔌 Anonymous Twitch IRC connection
- 🎨 Colored usernames and role badges
- ⚙ Live overlay settings
- 🌍 English / Russian UI
- 📊 Session statistics
- 💾 Saved config and last channel

## 📦 Requirements

- Windows 10 / 11
- Python 3.8+
- `pywin32`
- `pystray`
- `Pillow`

## 🚀 Installation

```bash
git clone https://github.com/tailogs/twitch_chat.git
cd twitch_chat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Or install manually:

```bash
pip install pywin32 pystray Pillow
```

## ▶ Usage

Run normally:

```bash
python twitch_chat.pyw
```

Run with auto-connect channel:

```bash
python twitch_chat.pyw shroud
```

Run without saving logs:

```bash
python twitch_chat.pyw --test
```

## 🖥 Interface

- **Connection** — connect/disconnect from Twitch chat
- **Logs** — system messages and chat log
- **Settings** — position, size, opacity, font size, language
- **Statistics** — messages, users, reconnects, errors

## ⚙ Saved Files

- `overlay_config.json` — overlay settings
- `app_state.json` — last channel and language
- `chat_logs/` — system logs and anonymized stats

## 🔒 Privacy

- Anonymous connection only
- No Twitch login required
- Chat messages are not saved to disk
- Usernames in stats are hashed

## 📄 License

MIT