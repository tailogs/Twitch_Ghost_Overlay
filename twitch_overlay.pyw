import socket
import time
import re
import random
import os
import hashlib
import json
import argparse
import threading
import queue
import sys
from datetime import datetime
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, font as tkfont, filedialog
import ctypes
from ctypes import wintypes
import urllib.request
import io
import string
import struct

# ==================== ИМПОРТЫ ДЛЯ WINDOWS И GUI ====================

try:
    import win32gui
    import win32con
    WIN32_OK = True
except ImportError:
    WIN32_OK = False

try:
    import pystray
    TRAY_OK = True
except ImportError:
    TRAY_OK = False

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ==================== ИНФОРМАЦИЯ О ПРОГРАММЕ ====================
APP_NAME = "Twitch Ghost Overlay"
APP_VERSION = "1.2.4"
APP_AUTHOR = "Tailogs"
APP_YEAR = "2026"
APP_DESCRIPTION = "Overlay for Twitch chat with alert system"

# ==================== КОНСТАНТЫ И КОНФИГИ (оставил как было) ====================

HEARTBEAT_FILE = "heartbeat.tmp"
OVERLAY_CONFIG_FILE = "overlay_config.json"
APP_STATE_FILE = "app_state.json"
ALERTS_CONFIG_FILE = "alerts_config.json"
EMOTE_CACHE_DIR = "emote_cache"
LOGS_DIR = "chat_logs"

_emote_images = {}
_emote_frames = {}
_emote_delays = {}
_emote_is_animated = {}
_emote_download_lock = threading.Lock()
_animated_canvas_items = {}

HEARTBEAT_INTERVAL = 5

DEFAULT_OVERLAY_CONFIG = {
    "x": 50, "y": 50, "width": 550, "height": 450,
    "opacity": 0.78, "font_size": 13, "font_family": "Consolas",
    "text_color": "#FFFFFF", "max_messages": 80,
    "bg_color": "#0a0a0a",
    "bg_enabled": True,              # <-- новый ключ (вкл/выкл фона)
    "translation_color": "#44DDFF",
}

_emote_pending = set()
_emote_pending_lock = threading.Lock()

DEFAULT_APP_STATE = {
    "last_channel": "",
    "language": "en",
}

DEFAULT_ALERTS_CONFIG = {
    "alerts": [],
    "cooldown": 10,
    "enabled": True,
}

_alerts_config = DEFAULT_ALERTS_CONFIG.copy()
_alert_last_fired = {}
_alert_image_cache = {}
_alert_lock = threading.Lock()


TRANSLATIONS = {
    "en": {
        "app_title": "Twitch Overlay",
        "app_brand": "Twitch Ghost Overlay",
        "status_connected": "● Connected",
        "status_connecting": "● Connecting...",
        "status_disconnected": "● Disconnected",
        "tab_connection": "  📡  Connection  ",
        "tab_logs": "  📜  Logs  ",
        "tab_settings": "  ⚙  Settings  ",
        "tab_stats": "  📊  Statistics  ",
        "conn_title": "📡  Connect to Twitch chat",
        "conn_subtitle": "Enter a Twitch channel name to track its chat.\nConnection is anonymous — no tokens required.",
        "conn_channel_label": "Channel name:",
        "btn_connect": "🔌  Connect",
        "btn_disconnect": "⏸  Disconnect",
        "hint_title": "💡 Tips:",
        "hint_lines": (
            "• To change channel — disconnect and connect to a new one\n"
            "• Overlay shows over any window (including borderless games)\n"
            "• Mouse clicks pass through the overlay — it won't block your game\n"
            "• F8 = full restart (supervisor hotkey)\n"
            "• Anonymous nick: "
        ),
        "log_title": "📜  System messages and chat",
        "btn_clear_log": "🗑 Clear log",
        "btn_clear_overlay": "🧹 Clear Overlay",
        "settings_title": "⚙  Overlay Settings",
        "settings_hint": "Overlay borders are highlighted in red.\nChanges apply instantly.",
        "section_position": "📐  Position and size",
        "section_appearance": "🎨  Appearance",
        "section_language": "🌍  Language / Язык",
        "slider_x": "Position X:",
        "slider_y": "Position Y:",
        "slider_w": "Width:",
        "slider_h": "Height:",
        "slider_opacity": "Opacity:",
        "slider_font": "Font size:",
        "slider_max_msg": "Max messages:",
        "btn_save": "💾 Save",
        "btn_saved": "✓ Saved!",
        "btn_reset": "↺ Reset to defaults",
        "stats_title": "📊  Session statistics",
        "stats_channel": "Channel:",
        "stats_duration": "Duration:",
        "stats_messages": "Total messages:",
        "stats_users": "Unique users:",
        "stats_mods": "Moderators:",
        "stats_subs": "Subscribers:",
        "stats_vips": "VIPs:",
        "stats_reconnects": "Reconnects:",
        "stats_errors": "Errors:",
        "stats_pings": "IRC pings:",
        "tray_open": "🖥  Open program",
        "tray_quit": "❌  Quit",
        "err_empty": "Empty name",
        "err_short": "Too short",
        "err_long": "Too long",
        "err_chars": "Only latin letters, digits and _",
        "log_started": "Program started",
        "log_overlay_created": "Ghost Overlay created (click-through, always on top)",
        "log_tray_created": "Tray icon created. Right-click → menu",
        "log_irc_ready": "IRC thread ready. Waiting for connection...",
        "log_settings_saved": "Settings saved",
        "log_settings_reset": "Settings reset to defaults",
        "log_connecting": "Connecting to {host}:{port}",
        "log_connected": "Connected to #{ch}",
        "log_connect_request": "Connection requested: #{ch}",
        "log_disconnect_request": "Disconnect requested",
        "log_disconnected": "Disconnected from #{ch}",
        "log_max_reconnects": "Max reconnect attempts exceeded",
        "log_conn_failed": "Failed to connect: {e}",
        "log_conn_lost": "Connection lost: {e}",
        "log_error": "Error: {e}",
        "log_lang_changed": "Language changed to English",
        "ov_connecting": "Connecting to #{ch}...",
        "ov_connected": "✓ Connected to #{ch}",
        "ov_reconnecting": "⚠ Reconnecting...",
        "ov_disconnected": "Disconnected from #{ch}",
        "ov_too_many_recon": "✗ Too many reconnects",
        "ov_conn_error": "✗ Connection error: {e}",
        "lang_en": "🇬🇧 English",
        "lang_ru": "🇷🇺 Russian",
        "tab_alerts": "  🔔  Alerts  ",
        "alerts_title": "🔔  Keyword Alerts",
        "alerts_subtitle": "When a keyword appears in chat, an image pops up on the overlay.",
        "alerts_enable": "Enable alerts",
        "alerts_cooldown": "Cooldown (sec):",
        "alerts_keywords": "Keywords:",
        "alerts_keywords_hint": " (comma separated)",
        "alerts_image": "Image file:",
        "alerts_browse": "📂 Browse",
        "alerts_label": "Label:",
        "alerts_duration": "Duration (ms):",
        "alerts_add": "➕ Add / Update",
        "alerts_delete": "🗑 Delete selected",
        "alerts_test": "▶ Test alert",
        "alerts_saved": "Alert saved: {keywords}",
        "alerts_deleted": "Alert deleted",
        "alerts_test_fired": "Alert test fired: {label}",
        "about_title": "About",
        "about_text": "{name} v{version}\nDeveloped by {author}\n{year}\n\n{description}",
        "about_developer": "Developer: {author}",
        "about_version": "Version: {version}",
        "settings_show_bg": "Show message background",
        "settings_translation_color": "Translation color",
    },
    "ru": {
        "app_title": "Twitch Overlay",
        "app_brand": "Twitch Ghost Overlay",
        "status_connected": "● Подключено",
        "status_connecting": "● Подключение...",
        "status_disconnected": "● Не подключено",
        "tab_connection": "  📡  Подключение  ",
        "tab_logs": "  📜  Логи  ",
        "tab_settings": "  ⚙  Настройки  ",
        "tab_stats": "  📊  Статистика  ",
        "conn_title": "📡  Подключение к Twitch чату",
        "conn_subtitle": "Введите имя канала Twitch для отслеживания чата.\nПодключение анонимное — никаких токенов не требуется.",
        "conn_channel_label": "Имя канала:",
        "btn_connect": "🔌  Подключиться",
        "btn_disconnect": "⏸  Отключиться",
        "hint_title": "💡 Совет:",
        "hint_lines": (
            "• Чтобы сменить канал — отключитесь и подключитесь к новому\n"
            "• Overlay появится поверх любого окна (включая игры в borderless)\n"
            "• Сквозь overlay проходят клики мыши — он не мешает играть\n"
            "• F8 = полный перезапуск (хоткей супервизора)\n"
            "• Анонимный ник: "
        ),
        "log_title": "📜  Системные сообщения и чат",
        "btn_clear_log": "🗑 Очистить лог",
        "btn_clear_overlay": "🧹 Очистить Overlay",
        "settings_title": "⚙  Настройки Overlay",
        "settings_hint": "Границы overlay подсвечены красным.\nИзменения применяются мгновенно.",
        "section_position": "📐  Позиция и размер",
        "section_appearance": "🎨  Внешний вид",
        "section_language": "🌍  Language / Язык",
        "slider_x": "Позиция X:",
        "slider_y": "Позиция Y:",
        "slider_w": "Ширина:",
        "slider_h": "Высота:",
        "slider_opacity": "Прозрачность:",
        "slider_font": "Размер шрифта:",
        "slider_max_msg": "Макс. сообщений:",
        "btn_save": "💾 Сохранить",
        "btn_saved": "✓ Сохранено!",
        "btn_reset": "↺ Сброс к умолчанию",
        "stats_title": "📊  Статистика сессии",
        "stats_channel": "Канал:",
        "stats_duration": "Длительность:",
        "stats_messages": "Сообщений всего:",
        "stats_users": "Уникальных юзеров:",
        "stats_mods": "Модераторов:",
        "stats_subs": "Подписчиков:",
        "stats_vips": "VIP:",
        "stats_reconnects": "Переподключений:",
        "stats_errors": "Ошибок:",
        "stats_pings": "IRC PING:",
        "tray_open": "🖥  Открыть программу",
        "tray_quit": "❌  Выход",
        "err_empty": "Имя пустое",
        "err_short": "Слишком короткое",
        "err_long": "Слишком длинное",
        "err_chars": "Только латиница, цифры и _",
        "log_started": "Программа запущена",
        "log_overlay_created": "Ghost Overlay создан (click-through, всегда сверху)",
        "log_tray_created": "Иконка трея создана. ПКМ → меню",
        "log_irc_ready": "IRC поток готов. Ждёт подключения...",
        "log_settings_saved": "Настройки сохранены",
        "log_settings_reset": "Настройки сброшены к умолчаниям",
        "log_connecting": "Подключение к {host}:{port}",
        "log_connected": "Подключено к #{ch}",
        "log_connect_request": "Запрос на подключение к #{ch}",
        "log_disconnect_request": "Запрос на отключение",
        "log_disconnected": "Отключено от #{ch}",
        "log_max_reconnects": "Превышено количество переподключений",
        "log_conn_failed": "Не удалось подключиться: {e}",
        "log_conn_lost": "Соединение разорвано: {e}",
        "log_error": "Ошибка: {e}",
        "log_lang_changed": "Язык изменён на Русский",
        "ov_connecting": "Подключаюсь к #{ch}...",
        "ov_connected": "✓ Подключён к #{ch}",
        "ov_reconnecting": "⚠ Переподключение...",
        "ov_disconnected": "Отключено от #{ch}",
        "ov_too_many_recon": "✗ Слишком много переподключений",
        "ov_conn_error": "✗ Ошибка подключения: {e}",
        "lang_en": "🇬🇧 English",
        "lang_ru": "🇷🇺 Русский",
        "tab_alerts": "  🔔  Алерты  ",
        "alerts_title": "🔔  Алерты по ключевым словам",
        "alerts_subtitle": "Когда ключевое слово появляется в чате, на оверлее появляется изображение.",
        "alerts_enable": "Включить алерты",
        "alerts_cooldown": "Задержка (сек):",
        "alerts_keywords": "Ключевые слова:",
        "alerts_keywords_hint": " (через запятую)",
        "alerts_image": "Файл изображения:",
        "alerts_browse": "📂 Выбрать",
        "alerts_label": "Метка:",
        "alerts_duration": "Длительность (мс):",
        "alerts_add": "➕ Добавить / Обновить",
        "alerts_delete": "🗑 Удалить выбранное",
        "alerts_test": "▶ Тест алерта",
        "alerts_saved": "Алерт сохранён: {keywords}",
        "alerts_deleted": "Алерт удалён",
        "alerts_test_fired": "Тестовый алерт: {label}",
        "about_title": "О программе",
        "about_text": "{name} v{version}\nРазработчик: {author}\n{year}\n\n{description}",
        "about_developer": "Разработчик: {author}",
        "about_version": "Версия: {version}",
        "settings_show_bg": "Показывать фон сообщений",
        "settings_translation_color": "Цвет перевода",
    },
}

_current_lang = "en"


def t(key, **kwargs):
    lang = TRANSLATIONS.get(_current_lang, TRANSLATIONS["en"])
    s = lang.get(key, TRANSLATIONS["en"].get(key, key))
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s


def set_language(lang):
    global _current_lang
    if lang in TRANSLATIONS:
        _current_lang = lang


def load_overlay_config():
    try:
        if os.path.exists(OVERLAY_CONFIG_FILE):
            with open(OVERLAY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                for k, v in DEFAULT_OVERLAY_CONFIG.items():
                    if k not in cfg:
                        cfg[k] = v
                return cfg
    except Exception:
        pass
    return DEFAULT_OVERLAY_CONFIG.copy()


def save_overlay_config(cfg):
    try:
        with open(OVERLAY_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_app_state():
    try:
        if os.path.exists(APP_STATE_FILE):
            with open(APP_STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                for k, v in DEFAULT_APP_STATE.items():
                    if k not in state:
                        state[k] = v
                return state
    except Exception:
        pass
    return DEFAULT_APP_STATE.copy()


def save_app_state(state):
    try:
        with open(APP_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


TWITCH_HOST = "irc.chat.twitch.tv"
TWITCH_PORT = 6667
ANON_NICK   = "justinfan" + str(random.randint(10000, 99999))

DEFAULT_COLORS = [
    "#FF6699", "#00FFAA", "#FFAA00", "#66CCFF",
    "#FF66CC", "#AAFF66", "#FF8855", "#88AAFF",
    "#FFCC44", "#AA88FF", "#44FFCC", "#FF6644",
]

HASH_SALT = os.urandom(16).hex()

twitch_config = {
    "channel": None, "test_mode": False,
    "log_system": True, "log_stats": True, "max_reconnects": 50,
}

connection_state = {
    "connected": False, "connecting": False,
    "current_channel": None, "sock": None,
    "last_activity": time.time(),
}
connection_lock = threading.Lock()

chat_command  = queue.Queue()
user_colors   = {}
system_log_file = None
should_stop   = threading.Event()
log_queue     = queue.Queue()

stats = {
    "session_start":     time.time(),
    "session_start_iso": datetime.now().isoformat(),
    "channel":           None,
    "total_messages":    0,
    "unique_users_hashed": set(),
    "messages_per_minute": defaultdict(int),
    "users_by_role": {
        "moderators": set(), "subscribers": set(),
        "vips": set(), "broadcaster": set(),
    },
    "errors": 0, "reconnects": 0, "irc_pings": 0,
}


_translate_cache = {}
_translate_lock = threading.Lock()


def load_alerts_config():
    global _alerts_config
    try:
        if os.path.exists(ALERTS_CONFIG_FILE):
            with open(ALERTS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _alerts_config = data
                return data
    except Exception:
        pass
    _alerts_config = DEFAULT_ALERTS_CONFIG.copy()
    return _alerts_config.copy()


def save_alerts_config(cfg):
    global _alerts_config
    _alerts_config = cfg
    try:
        with open(ALERTS_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def check_message_for_alerts(message: str) -> dict | None:
    """
    Checks if message contains any alert keyword.
    Returns matching alert config dict or None.
    Respects per-alert cooldown.
    """
    if not _alerts_config.get('enabled', True):
        return None
    msg_lower = message.lower()
    cooldown  = _alerts_config.get('cooldown', 10)
    now       = time.time()
    for alert in _alerts_config.get('alerts', []):
        for kw in alert.get('keywords', []):
            if kw.lower() in msg_lower:
                last = _alert_last_fired.get(kw.lower(), 0)
                if now - last >= cooldown:
                    with _alert_lock:
                        _alert_last_fired[kw.lower()] = now
                    return alert
    return None


def fetch_alert_image(url: str) -> bytes | None:
    if not url:
        return None
    with _alert_lock:
        if url in _alert_image_cache:
            return _alert_image_cache[url]

    data = None

    if os.path.isfile(url):
        try:
            with open(url, 'rb') as f:
                data = f.read(15 * 1024 * 1024)
        except Exception as e:
            log_to_gui(f"Error reading local alert file: {e}", "ERROR")
    elif url.startswith('http://') or url.startswith('https://'):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'TwitchOverlay/1.0'})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = resp.read(15 * 1024 * 1024)
        except Exception as e:
            log_to_gui(f"Error downloading alert image: {e}", "ERROR")

    with _alert_lock:
        _alert_image_cache[url] = data
    return data


def _is_mostly_english(text: str) -> bool:
    if not text:
        return False

    text = re.sub(r'!\w+', '', text)
    
    text = re.sub(r'@\w+', '', text)
    
    text = re.sub(r'\b[A-Z][a-z]+[A-Z]\w*\b', '', text)
    text = re.sub(r'\b[A-Z]{2,}\w*\b', '', text)
    
    text = re.sub(r'\b\w*[A-Z]\w*[A-Z]\w*\b', '', text)
    
    text = re.sub(r'\b\d+\b', '', text)
    text = re.sub(r'\[🔗[^\]]+\]', '', text)
    
    text = text.strip()
    if not text or len(text) < 3:
        return False

    latin_chars = sum(1 for c in text if c.isascii() and c.isalpha())
    cyrillic_chars = sum(1 for c in text 
                        if '\u0400' <= c <= '\u04FF' or c in 'ёЁ')
    total_alpha = latin_chars + cyrillic_chars

    if total_alpha == 0:
        return False

    latin_ratio = latin_chars / total_alpha

    return latin_ratio > 0.75 and latin_chars >= 3


def _google_translate_free(text, dest='ru'):
    """Перевод с автоопределением языка на указанный целевой язык."""
    if not text or len(text) > 300:
        return None
    try:
        import urllib.parse
        safe_text = re.sub(r'[^\w\s\.,!?;:\'"()\[\]{}\-–—]', ' ', text, flags=re.UNICODE)
        safe_text = safe_text[:300].strip()
        if not safe_text:
            return None

        encoded = urllib.parse.quote(safe_text)
        # Используем 'auto' для автоматического определения исходного языка
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl={dest}&dt=t&q={encoded}"
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read(64 * 1024)
            data = json.loads(raw.decode('utf-8'))

        translated_parts = []
        if data and isinstance(data, list) and data[0]:
            for part in data[0]:
                if isinstance(part, list) and part and isinstance(part[0], str):
                    translated_parts.append(part[0])
        result = ''.join(translated_parts)
        result = sanitize_message(result)
        return result if result else None
    except Exception:
        return None


def translate_if_needed(text: str):
    """Пытается перевести текст на текущий язык интерфейса, если это необходимо."""
    if not text or len(text) < 4:
        return text, None

    # Команды не переводим
    if text.lstrip().startswith('!'):
        return text, None

    cache_key = text.lower().strip()
    with _translate_lock:
        if cache_key in _translate_cache:
            return text, _translate_cache[cache_key]

    # Переводим на текущий язык интерфейса
    translated = _google_translate_free(text, dest=_current_lang)

    if translated and translated.lower().strip() != text.lower().strip():
        with _translate_lock:
            _translate_cache[cache_key] = translated
            if len(_translate_cache) > 2000:
                keys = list(_translate_cache.keys())
                for k in keys[:500]:
                    _translate_cache.pop(k, None)
        return text, translated

    return text, None


def translate_async(text, callback):
    def _do():
        original, translated = translate_if_needed(text)
        if callback:
            callback(original, translated)
    threading.Thread(target=_do, daemon=True, name="Translate").start()


COMMAND_8BALL_ANSWERS_EN = [
    "It is certain", "Without a doubt", "Yes definitely",
    "You may rely on it", "Most likely", "Outlook good",
    "Yes", "Signs point to yes", "Reply hazy, try again",
    "Ask again later", "Better not tell you now",
    "Cannot predict now", "Concentrate and ask again",
    "Don't count on it", "My reply is no",
    "My sources say no", "Outlook not so good", "Very doubtful",
]

COMMAND_8BALL_ANSWERS_RU = [
    "Бесспорно", "Без сомнений", "Определённо да",
    "Можешь положиться на это", "Скорее всего", "Хорошие перспективы",
    "Да", "Знаки указывают — да", "Пока неясно, попробуй снова",
    "Спроси позже", "Лучше не говорить сейчас",
    "Невозможно предсказать", "Сконцентрируйся и спроси снова",
    "Не рассчитывай на это", "Мой ответ — нет",
    "Мои источники говорят — нет", "Перспективы не очень", "Весьма сомнительно",
]

COMMAND_PATTERNS = {
    '!8ball':  r'!8ball',
    '!roll':   r'!roll(?:\s+(\d+))?',
    '!coin':   r'!coin|!flip',
    '!choose': r'!choose\s+(.+)',
    '!rate':   r'!rate\s+(.+)',
    '!hug':    r'!hug\s+(\S+)',
    '!love':   r'!love\s+(\S+)',
}


def process_chat_commands(message):
    msg_lower = message.lower().strip()

    if '!8ball' in msg_lower:
        if _current_lang == 'ru':
            answer = random.choice(COMMAND_8BALL_ANSWERS_RU)
        else:
            answer = random.choice(COMMAND_8BALL_ANSWERS_EN)
        return message, f"🎱 {answer}"

    match = re.search(r'!roll(?:\s+(\d+))?', msg_lower)
    if match:
        max_val = int(match.group(1)) if match.group(1) else 100
        max_val = min(max_val, 1000000)
        result = random.randint(1, max(1, max_val))
        return message, f"🎲 {result}/{max_val}"

    if '!coin' in msg_lower or '!flip' in msg_lower:
        if _current_lang == 'ru':
            result = random.choice(["Орёл 🦅", "Решка 👑"])
        else:
            result = random.choice(["Heads 🦅", "Tails 👑"])
        return message, result

    match = re.search(r'!choose\s+(.+)', message, re.IGNORECASE)
    if match:
        options_str = match.group(1)
        if ' or ' in options_str.lower():
            options = [o.strip() for o in re.split(r'\s+or\s+', options_str, flags=re.IGNORECASE)]
        elif ',' in options_str:
            options = [o.strip() for o in options_str.split(',')]
        elif ' или ' in options_str.lower():
            options = [o.strip() for o in re.split(r'\s+или\s+', options_str, flags=re.IGNORECASE)]
        else:
            options = options_str.split()
        options = [o for o in options if o]
        if options:
            chosen = random.choice(options)
            return message, f"👉 {chosen}"

    match = re.search(r'!rate\s+(.+)', message, re.IGNORECASE)
    if match:
        thing = match.group(1).strip()
        score = int(hashlib.md5(thing.lower().encode()).hexdigest()[:8], 16) % 101
        bar_filled = score // 10
        bar_empty = 10 - bar_filled
        bar = '█' * bar_filled + '░' * bar_empty
        return message, f"📊 {thing}: {score}/100 [{bar}]"

    match = re.search(r'!hug\s+@?(\S+)', message, re.IGNORECASE)
    if match:
        target = match.group(1)
        if _current_lang == 'ru':
            return message, f"🤗 обнимает {target}!"
        else:
            return message, f"🤗 hugs {target}!"

    match = re.search(r'!love\s+@?(\S+)', message, re.IGNORECASE)
    if match:
        target = match.group(1)
        score = int(hashlib.md5(target.lower().encode()).hexdigest()[:8], 16) % 101
        return message, f"💕 {target}: {score}% love"

    return message, None


_RU_PROFANITY_ROOTS = [
    r'[хx][уy][ёеeийяю]',
    r'[хx][уy][йяию]',
    r'[пp][иieё][зz3][дd]',
    r'[бb6][лl][яыаеёию][дdтt]',
    r'[бb6][лl][яь]',
    r'[еe][бb6][аaуыоёлнт]',
    r'[ёе][бb6](?:[аaуыоёлнтиь])',
    r'[сsc][уy][чкк][аоиьея]',
    r'[сsc][рr][аa][нт]',
    r'[мm][уy][дd][аоиьея]',
    r'[дd][еe][рr][ьъ][мm]',
    r'[жж][оo][пp][аоуые]',
    r'[гg][аa][нn][дd][оo][нn]',
    r'[зz3][аa][лl][уy][пp]',
    r'[пp][иieё][дd][аa][рr]',
    r'[пp][еe][дd][иieё][кk]',
    r'[шш][лl][юy][хx]',
    r'[шш][аa][лl][аa][вв]',
    r'[дd][рr][оo][чч]',
    r'[тt][рr][аa][хx]',
    r'[нn][аa][хx][уy]',
]

_EN_PROFANITY_ROOTS = [
    r'f+[uü]+c+k+',
    r'f+[uü]+k+',
    r's+h+[i1]+t+',
    r'b+[i1]+t+c+h+',
    r'a+s+s+h+[o0]+l+e+',
    r'c+[uü]+n+t+',
    r'd+[i1]+c+k+',
    r'c+[o0]+c+k+',
    r'p+[uü]+s+s+[yie]+',
    r'w+h+[o0]+r+e+',
    r'n+[i1]+g+g+',
    r'f+a+g+',
    r'd+a+m+n+',
    r'b+[o0]+l+l+[o0]+c+k+',
    r'w+a+n+k+',
    r't+w+a+t+',
    r'p+r+[i1]+c+k+',
]

_profanity_pattern = None


_MAX_MSG_LEN        = 500
_MAX_USERNAME_LEN   = 25
_MAX_EMOTES_COUNT   = 50
_MAX_WORD_LEN       = 60
_MAX_REPEAT_RUN     = 8

_DANGEROUS_UNICODE_RANGES = [
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2066, 0x2069),
    (0xFFF0, 0xFFFF),
    (0xE0000, 0xE007F),
    (0xFE00, 0xFE0F),
]

_FORBIDDEN_CHARS = frozenset([
    '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
    '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12',
    '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a',
    '\x1b', '\x1c', '\x1d', '\x1e', '\x1f', '\x7f',
    '\u200b', '\u200c', '\u200d', '\u200e', '\u200f',
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
    '\u2066', '\u2067', '\u2068', '\u2069',
    '\ufeff',
    '\u034f',
    '\u00ad',
])

_URL_PATTERN = re.compile(
    r'(?i)\b(?:https?://|ftp://|//)?'
    r'(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)'
    r'+(?:com|ru|net|org|io|gg|tv|me|co|uk|de|fr|jp|cn|'
    r'xyz|site|online|club|info|biz|live|stream|watch|'
    r'bit\.ly|t\.co|goo\.gl|tinyurl)'
    r'(?:/[^\s]*)?',
    re.IGNORECASE | re.UNICODE
)

_IP_PATTERN = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
    r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
)

_REPEAT_PATTERN = re.compile(r'(.)\1{' + str(_MAX_REPEAT_RUN) + r',}', re.UNICODE)

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{1,25}$')


def _is_dangerous_codepoint(cp: int) -> bool:
    for start, end in _DANGEROUS_UNICODE_RANGES:
        if start <= cp <= end:
            return True
    return False


def sanitize_username(username: str) -> str:
    if not username or not isinstance(username, str):
        return "unknown"

    clean = re.sub(r'[^a-zA-Z0-9_]', '', username)

    clean = clean[:_MAX_USERNAME_LEN]

    return clean if clean else "unknown"


def sanitize_color(color: str) -> str:
    if not color or not isinstance(color, str):
        return '#9146FF'

    color = color.strip()
    if re.match(r'^#[0-9A-Fa-f]{6}$', color):
        return color

    m = re.match(r'^#([0-9A-Fa-f]{3})$', color)
    if m:
        r, g, b = m.group(1)
        return f'#{r}{r}{g}{g}{b}{b}'

    return '#9146FF'


def mask_url(text: str) -> str:
    def _replace_url(match):
        url = match.group(0)
        domain_match = re.search(
            r'(?:https?://|ftp://|//)?([^/\s?#]+)',
            url, re.IGNORECASE
        )
        if domain_match:
            domain = domain_match.group(1)
            domain = re.sub(r'^www\.', '', domain)
            if len(domain) > 30:
                domain = domain[:27] + '...'
            return f'[🔗 {domain}]'
        return '[🔗 ссылка]'

    return _URL_PATTERN.sub(_replace_url, text)


def mask_ip(text: str) -> str:
    return _IP_PATTERN.sub('[IP скрыт]', text)


def remove_forbidden_chars(text: str) -> str:
    result = []
    for char in text:
        cp = ord(char)

        if cp < 0x20 and char not in ('\t', '\n', '\r'):
            continue

        if char in _FORBIDDEN_CHARS:
            continue

        if _is_dangerous_codepoint(cp):
            continue

        result.append(char)

    return ''.join(result)


def collapse_repeats(text: str) -> str:
    def _replace_repeat(match):
        char = match.group(1)
        count = len(match.group(0))
        return f'{char}×{count}'

    return _REPEAT_PATTERN.sub(_replace_repeat, text)


def truncate_words(text: str) -> str:
    words = text.split(' ')
    result = []
    for word in words:
        if len(word) > _MAX_WORD_LEN:
            word = word[:_MAX_WORD_LEN] + '…'
        result.append(word)
    return ' '.join(result)


def limit_emotes(emotes_raw: str, message: str) -> str:
    if not emotes_raw:
        return ""

    msg_len = len(message)

    try:
        total_positions = 0
        blocks = emotes_raw.split('/')
        safe_blocks = []

        for block in blocks:
            if ':' not in block:
                continue
            emote_id, positions_str = block.split(':', 1)
            emote_id = emote_id.strip()

            if not re.match(r'^[a-zA-Z0-9_]{1,64}$', emote_id):
                continue

            positions = positions_str.split(',')
            safe_positions = []

            for pos in positions:
                if total_positions >= _MAX_EMOTES_COUNT:
                    break
                pos = pos.strip()
                if '-' not in pos:
                    continue
                parts = pos.split('-', 1)
                if len(parts) != 2:
                    continue
                try:
                    start = int(parts[0])
                    end   = int(parts[1])

                    if start < 0 or end < start or start >= msg_len:
                        continue
                    
                    safe_positions.append(f'{start}-{end}')
                    total_positions += 1
                except (ValueError, OverflowError):
                    continue

            if safe_positions:
                safe_blocks.append(f'{emote_id}:{",".join(safe_positions)}')

        return '/'.join(safe_blocks)

    except Exception:
        return emotes_raw


def sanitize_message(text: str, preserve_positions: bool = False) -> str:
    if not text or not isinstance(text, str):
        return ''

    text = text[:_MAX_MSG_LEN * 2]

    if preserve_positions:
        result = []
        for char in text:
            cp = ord(char)
            if cp < 0x20 and char not in ('\t', '\n', '\r'):
                result.append(' ')
            elif char in _FORBIDDEN_CHARS:
                result.append(' ')
            elif _is_dangerous_codepoint(cp):
                result.append(' ')
            else:
                result.append(char)
        text = ''.join(result)
    else:
        text = remove_forbidden_chars(text)

    if not preserve_positions:
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = text.strip()

    if not preserve_positions:
        text = mask_url(text)
        text = mask_ip(text)
        text = collapse_repeats(text)
        text = truncate_words(text)

    if len(text) > _MAX_MSG_LEN:
        text = text[:_MAX_MSG_LEN - 1] + '…'

    return text


def sanitize_emote_id(emote_id: str) -> str | None:
    if not emote_id or not isinstance(emote_id, str):
        return None
    emote_id = emote_id.strip()
    if re.match(r'^[a-zA-Z0-9_]{1,64}$', emote_id):
        return emote_id
    return None


def _build_profanity_pattern():
    global _profanity_pattern
    all_roots = _RU_PROFANITY_ROOTS + _EN_PROFANITY_ROOTS
    combined = '|'.join(f'(?:{r})' for r in all_roots)
    _profanity_pattern = re.compile(
        r'(?<![a-zA-Zа-яА-ЯёЁ])(' + combined + r')[a-zA-Zа-яА-ЯёЁ]*',
        re.IGNORECASE | re.UNICODE
    )


def censor_profanity(text):
    if _profanity_pattern is None:
        _build_profanity_pattern()

    ranges = []
    result_parts = []
    last_end = 0

    for match in _profanity_pattern.finditer(text):
        start, end = match.start(), match.end()
        word = match.group(0)

        if start > last_end:
            result_parts.append(('clean', text[last_end:start]))

        censored = _censor_word(word)
        result_parts.append(('censored', censored))
        last_end = end

    if last_end < len(text):
        result_parts.append(('clean', text[last_end:]))

    if not any(p[0] == 'censored' for p in result_parts):
        return text, []

    final_text = ""
    censored_ranges = []
    for part_type, part_text in result_parts:
        if part_type == 'censored':
            start_pos = len(final_text)
            final_text += part_text
            censored_ranges.append((start_pos, len(final_text)))
        else:
            final_text += part_text

    return final_text, censored_ranges


def _censor_word(word):
    if len(word) <= 1:
        return word
    blur_chars = ['░', '▒', '▓', '█', '◼', '●', '◆']
    result = word[0]
    for i in range(1, len(word)):
        result += random.choice(blur_chars)
    return result


def process_message_pipeline(username, message, has_emotes=False):
    if has_emotes:
        censored_msg = message
        censored_ranges = []
    else:
        censored_msg, censored_ranges = censor_profanity(message)

    cmd_msg, command_response = process_chat_commands(censored_msg)

    # Очищаем от команд и упоминаний для проверки
    clean_check = re.sub(r'!\w+|@\w+', '', cmd_msg).strip()
    # Убираем ограничение на количество слов – оставляем только длину >= 4 и не команду
    needs_translation = (
        len(clean_check) >= 4
        and not cmd_msg.lstrip().startswith('!')
    )

    return {
        'message': cmd_msg,
        'command_response': command_response,
        'censored_ranges': censored_ranges,
        'needs_translation': needs_translation,
    }


class GhostOverlay:
    def __init__(self, overlay_cfg):
        self.cfg            = overlay_cfg
        self.root           = tk.Tk()
        self.running        = True
        self.visible        = True
        self.settings_mode  = False
        self._message_queue = []
        self._queue_lock    = threading.Lock()
        self.message_blocks = []

        self.root.title("Twitch Ghost Overlay")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', self.cfg['opacity'])
        self.root.configure(bg='black')
        self.root.attributes('-transparentcolor', 'black')
        self._apply_geometry()

        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.text_font = tkfont.Font(
            family=self.cfg['font_family'],
            size=self.cfg['font_size'], weight='normal'
        )
        self.name_font = tkfont.Font(
            family=self.cfg['font_family'],
            size=max(9, self.cfg['font_size'] - 2), weight='bold'
        )

        self.padding          = 12
        self.line_spacing     = self.cfg['font_size'] + 8
        self.name_line_height = max(9, self.cfg['font_size'] - 2) + 8
        self.msg_block_spacing = 10
        self.name_to_msg_gap  = 3
        self.settings_border_ids = []
        self._animated_items = {}
        self._animation_running = True
        self.root.after(50, self._animate_emotes_loop)

        self.root.after(50,  self._make_click_through)
        self.root.after(200, self._make_click_through)
        self.root.after(500, self._keep_topmost_loop)
        self.root.after(33,  self._process_queue)

    def _get_bg_color_with_alpha(self):
        """Возвращает цвет фона (без альфа-канала)."""
        return self.cfg.get('bg_color', '#0a0a0a')

    def _apply_geometry(self):
        w, h = self.cfg['width'], self.cfg['height']
        x, y = self.cfg['x'],     self.cfg['y']
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _get_hwnd(self):
        return ctypes.windll.user32.GetParent(self.root.winfo_id())

    def _make_click_through(self):
        if not WIN32_OK:
            return
        try:
            hwnd     = self._get_hwnd()
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                ex_style
                | win32con.WS_EX_LAYERED
                | win32con.WS_EX_TRANSPARENT
                | win32con.WS_EX_TOOLWINDOW
                | win32con.WS_EX_NOACTIVATE
            )
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
        except Exception as e:
            log_to_gui(f"Click-through error: {e}", "ERROR")

    def _keep_topmost_loop(self):
        if not self.running:
            return
        if WIN32_OK:
            try:
                hwnd     = self._get_hwnd()
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                need = (win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
                        | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE)
                if (ex_style & need) != need:
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style | need)
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
                )
            except Exception:
                pass
        self.root.after(1000, self._keep_topmost_loop)

    def set_settings_mode(self, enabled):
        self.settings_mode = enabled
        self._redraw_settings_border()

    def _redraw_settings_border(self):
        for item_id in self.settings_border_ids:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self.settings_border_ids = []
        if not self.settings_mode:
            return

        w, h = self.cfg['width'], self.cfg['height']
        ids  = []
        ids.append(self.canvas.create_rectangle(1, 1, w-1, h-1,
            outline='#FF3366', width=2, tags='settings_border'))
        ids.append(self.canvas.create_rectangle(4, 4, w-4, h-4,
            outline='#FFAA00', width=1, tags='settings_border'))

        cs, cc, cw = 18, '#00FFFF', 3
        for line_coords in [
            (0,0,cs,0),(0,0,0,cs),(w,0,w-cs,0),(w,0,w,cs),
            (0,h,cs,h),(0,h,0,h-cs),(w,h,w-cs,h),(w,h,w,h-cs),
        ]:
            ids.append(self.canvas.create_line(*line_coords,
                fill=cc, width=cw, tags='settings_border'))

        ids.append(self.canvas.create_text(
            w//2, h-14,
            text=f"  {w} × {h}  @  ({self.cfg['x']}, {self.cfg['y']})  ",
            font=('Segoe UI', 9, 'bold'), fill='#FFFF00', tags='settings_border'
        ))
        self.settings_border_ids = ids
        for item_id in ids:
            try:
                self.canvas.tag_raise(item_id)
            except Exception:
                pass

    def _animate_emotes_loop(self):
        if not self.running or not self._animation_running:
            return

        items_to_remove = []

        for item_id, info in self._animated_items.items():
            emote_id = info['emote_id']
            frames = _emote_frames.get(emote_id)
            delays = _emote_delays.get(emote_id)

            if not frames or not delays:
                continue

            try:
                self.canvas.coords(item_id)
            except tk.TclError:
                items_to_remove.append(item_id)
                continue

            info['frame_idx'] = (info['frame_idx'] + 1) % len(frames)
            try:
                self.canvas.itemconfig(item_id, image=frames[info['frame_idx']])
            except tk.TclError:
                items_to_remove.append(item_id)

        for item_id in items_to_remove:
            self._animated_items.pop(item_id, None)

        self.root.after(80, self._animate_emotes_loop)

    def _register_animated_item(self, canvas_item_id, emote_id):
        if _emote_is_animated.get(emote_id, False):
            self._animated_items[canvas_item_id] = {
                'emote_id': emote_id,
                'frame_idx': 0,
            }

    def _wrap_to_lines(self, text, max_width, font):
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return [""]
        words        = text.split(' ')
        lines        = []
        current_line = ""
        i = 0
        while i < len(words):
            word = words[i]
            if font.measure(word) > max_width:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                chunk = ""
                for ch in word:
                    test = chunk + ch
                    if font.measure(test) <= max_width:
                        chunk = test
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                if chunk:
                    current_line = chunk
                i += 1
                continue
            test_line = current_line + " " + word if current_line else word
            if font.measure(test_line) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
            i += 1
        if current_line:
            lines.append(current_line)
        return lines if lines else [""]

    def _make_space(self, needed_height):
        canvas_h = self.canvas.winfo_height()
        if canvas_h < 10:
            canvas_h = self.cfg['height']
        bottom_limit   = canvas_h - self.padding
        current_bottom = self._get_current_bottom()
        if current_bottom + needed_height <= bottom_limit:
            return
        deficit          = (current_bottom + needed_height) - bottom_limit
        removed_height   = 0
        blocks_to_remove = []
        for block in self.message_blocks:
            if removed_height >= deficit:
                break
            blocks_to_remove.append(block)
            removed_height += block['height']
        for block in blocks_to_remove:
            for item_id in block['items']:
                self._animated_items.pop(item_id, None)
                try:
                    self.canvas.delete(item_id)
                except Exception:
                    pass
        self.message_blocks = self.message_blocks[len(blocks_to_remove):]
        if removed_height > 0:
            self.canvas.move('msg', 0, -removed_height)
            for block in self.message_blocks:
                block['start_y'] -= removed_height
        max_msg = self.cfg.get('max_messages', 80)
        if len(self.message_blocks) > max_msg:
            extra   = self.message_blocks[:len(self.message_blocks) - max_msg]
            extra_h = sum(b['height'] for b in extra)
            for block in extra:
                for item_id in block['items']:
                    self._animated_items.pop(item_id, None)
                    try:
                        self.canvas.delete(item_id)
                    except Exception:
                        pass
            self.message_blocks = self.message_blocks[len(extra):]
            if extra_h > 0:
                self.canvas.move('msg', 0, -extra_h)
                for block in self.message_blocks:
                    block['start_y'] -= extra_h

    def _get_current_bottom(self):
        if not self.message_blocks:
            return self.padding
        last = self.message_blocks[-1]
        return last['start_y'] + last['height']

    def _draw_outlined_text(self, x, y, text, font, color, items_collector):
        for ox, oy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
            tid = self.canvas.create_text(
                x+ox, y+oy, text=text, font=font,
                fill='#000000', anchor='nw', tags='msg'
            )
            items_collector.append(tid)
        tid = self.canvas.create_text(
            x, y, text=text, font=font,
            fill=color, anchor='nw', tags='msg'
        )
        items_collector.append(tid)
        return tid

    def _draw_name_header(self, x, y, badge_icon, username, name_color, items_collector):
        cur_x = x
        if badge_icon:
            icon_id = self.canvas.create_text(
                cur_x, y, text=badge_icon, font=self.name_font,
                fill='#FFCC44', anchor='nw', tags='msg'
            )
            items_collector.append(icon_id)
            cur_x += self.name_font.measure(badge_icon) + 6

        name_w = self.name_font.measure(username)
        pad_x, pad_y = 7, 2
        font_h = self.name_font.metrics('linespace')
        pill_h = font_h + pad_y * 2

        try:
            r = int(name_color[1:3], 16)
            g = int(name_color[3:5], 16)
            b = int(name_color[5:7], 16)
            text_on_pill = '#FFFFFF' if (0.299*r + 0.587*g + 0.114*b) < 140 else '#1A1A1A'
        except Exception:
            text_on_pill = '#FFFFFF'

        items_collector.append(self.canvas.create_rectangle(
            cur_x, y, cur_x + name_w + pad_x*2, y + pill_h,
            fill=name_color, outline=name_color, tags='msg'
        ))
        items_collector.append(self.canvas.create_text(
            cur_x + pad_x, y + pad_y, text=username, font=self.name_font,
            fill=text_on_pill, anchor='nw', tags='msg'
        ))
        return pill_h, cur_x + name_w + pad_x*2

    def add_chat_message(self, username, message,
                         name_color='#9146FF', msg_color=None, badge=None,
                         emotes_raw=""):
        if msg_color is None:
            msg_color = self.cfg.get('text_color', '#FFFFFF')

        alert = check_message_for_alerts(message)
        if alert:
            self.root.after(0, lambda a=alert: self.trigger_alert(a))

        has_emotes        = bool(emotes_raw)
        result            = process_message_pipeline(username, message, has_emotes=has_emotes)
        processed_msg    = result['message']
        command_response = result['command_response']
        censored_ranges  = result['censored_ranges']
        needs_translation = result['needs_translation']

        with self._queue_lock:
            self._message_queue.append(
                ('chat', username, processed_msg, name_color, msg_color, badge,
                 emotes_raw, command_response, censored_ranges)
            )

        if needs_translation:
            def on_translated(original, translated):
                if translated:
                    with self._queue_lock:
                        self._message_queue.append(
                            ('translation', username, original, translated, name_color)
                        )
            translate_async(message, on_translated)

    def add_system_message(self, message, color='#AAAAAA'):
        with self._queue_lock:
            self._message_queue.append(('system', None, message, color, color, None))

    def clear(self):
        with self._queue_lock:
            self._message_queue.append(('_clear',))

    def trigger_alert(self, alert_cfg: dict):
        if not PIL_OK:
            return

        duration = alert_cfg.get('duration', 4000)
        label    = alert_cfg.get('label', '🔥')
        url      = alert_cfg.get('image_url', '')

        def _do_alert(image_data):
            if not self.running:
                return

            w         = self.cfg['width']
            h         = self.cfg['height']
            pad       = self.padding
            items     = []

            alert_photo   = [None]
            anim_frames   = [None]
            anim_delays   = [None]
            img_w, img_h  = 0, 0

            if image_data:
                try:
                    from PIL import ImageTk
                    img_io  = io.BytesIO(image_data)
                    pil_img = Image.open(img_io)

                    max_img_w = int(w * 0.9)
                    max_img_h = int(h * 0.55)
                    ow, oh    = pil_img.size if hasattr(pil_img, 'size') else (100, 100)
                    scale     = min(max_img_w / max(ow, 1), max_img_h / max(oh, 1), 1.0)
                    target    = (max(1, int(ow * scale)), max(1, int(oh * scale)))
                    img_w, img_h = target

                    is_anim  = getattr(pil_img, 'is_animated', False)
                    n_frames = getattr(pil_img, 'n_frames', 1)

                    if is_anim and n_frames > 1:
                        frames, delays = [], []
                        for i in range(n_frames):
                            pil_img.seek(i)
                            f = pil_img.copy().convert('RGBA').resize(target, Image.LANCZOS)
                            frames.append(ImageTk.PhotoImage(f, master=self.root))
                            d = pil_img.info.get('duration', 80)
                            delays.append(max(20, d))
                        anim_frames[0] = frames
                        anim_delays[0] = delays
                        alert_photo[0] = frames[0]
                    else:
                        f = pil_img.convert('RGBA').resize(target, Image.LANCZOS)
                        alert_photo[0] = ImageTk.PhotoImage(f, master=self.root)

                    self._active_alert_img_ref = alert_photo[0]
                    self._active_alert_frames_ref = anim_frames[0]

                except Exception as e:
                    log_to_gui(f"Alert image processing error: {e}", "WARN")

            label_font  = tkfont.Font(family='Segoe UI', size=16, weight='bold')
            label_h     = 28
            img_block_h = img_h + 8 if img_h else 0
            block_h     = label_h + img_block_h + pad * 2

            canvas_h = self.canvas.winfo_height()
            if canvas_h < 10:
                canvas_h = h

            start_y  = canvas_h
            target_y = canvas_h - block_h - pad
            cx       = w // 2

            bg_item = self.canvas.create_rectangle(
                pad, start_y,
                w - pad, start_y + block_h,
                fill='#111111', outline='#9146FF', width=2,
                tags='alert'
            )
            items.append(bg_item)

            lbl_shadow = self.canvas.create_text(
                cx + 1, start_y + label_h // 2 + 1,
                text=label, font=label_font,
                fill='#000000', anchor='center', tags='alert'
            )
            lbl_main = self.canvas.create_text(
                cx, start_y + label_h // 2,
                text=label, font=label_font,
                fill='#FFD700', anchor='center', tags='alert'
            )
            items += [lbl_shadow, lbl_main]

            img_item = None
            if alert_photo[0]:
                img_y    = start_y + label_h + img_h // 2 + 4
                img_item = self.canvas.create_image(
                    cx, img_y, image=alert_photo[0],
                    anchor='center', tags='alert'
                )
                items.append(img_item)

            anim_state = {'idx': 0, 'job': None, 'running': True}
            if anim_frames[0] and img_item:
                def _next_anim_frame():
                    if not self.running or not anim_state['running']:
                        return
                    anim_state['idx'] = (anim_state['idx'] + 1) % len(anim_frames[0])
                    try:
                        self.canvas.itemconfig(img_item, image=anim_frames[0][anim_state['idx']])
                    except Exception:
                        return
                    anim_state['job'] = self.root.after(
                        anim_delays[0][anim_state['idx']], _next_anim_frame
                    )
                anim_state['job'] = self.root.after(anim_delays[0][0], _next_anim_frame)

            border_colors = ['#9146FF', '#FF4488', '#FF8800', '#FFFF00',
                             '#00FF88', '#00AAFF', '#9146FF']
            pulse_state   = {'phase': 0, 'job': None}

            def _pulse():
                if not self.running:
                    return
                pulse_state['phase'] = (pulse_state['phase'] + 1) % len(border_colors)
                try:
                    self.canvas.itemconfig(
                        bg_item, outline=border_colors[pulse_state['phase']]
                    )
                except Exception:
                    return
                pulse_state['job'] = self.root.after(150, _pulse)

            pulse_state['job'] = self.root.after(150, _pulse)

            for item in items:
                try:
                    self.canvas.tag_raise(item)
                except Exception:
                    pass

            # Slide-in анимация
            SLIDE_STEPS = 12
            SLIDE_MS    = 18
            dy          = (target_y - start_y) / SLIDE_STEPS
            step_state  = {'step': 0}

            def _slide_in():
                if not self.running:
                    return
                step_state['step'] += 1
                self.canvas.move('alert', 0, dy)
                if step_state['step'] < SLIDE_STEPS:
                    self.root.after(SLIDE_MS, _slide_in)

            self.root.after(SLIDE_MS, _slide_in)

            def _start_slide_out():
                if not self.running:
                    return
                anim_state['running'] = False
                if pulse_state['job']:
                    try:
                        self.root.after_cancel(pulse_state['job'])
                    except Exception:
                        pass

                out_step  = [0]
                out_total = SLIDE_STEPS
                out_dy    = (start_y - target_y) / out_total

                def _slide_out():
                    if not self.running:
                        self.canvas.delete('alert')
                        return
                    out_step[0] += 1
                    self.canvas.move('alert', 0, out_dy)
                    if out_step[0] < out_total:
                        self.root.after(SLIDE_MS, _slide_out)
                    else:
                        self.canvas.delete('alert')
                        self._active_alert_img_ref = None
                        self._active_alert_frames_ref = None
                        
                        if self.settings_mode:
                            for sid in self.settings_border_ids:
                                try:
                                    self.canvas.tag_raise(sid)
                                except Exception:
                                    pass

                self.root.after(SLIDE_MS, _slide_out)

            self.root.after(duration, _start_slide_out)

        def _fetch_and_show():
            data = fetch_alert_image(url) if url else None
            if url and not data:
                log_to_gui(f"Alert image load failed for: {url}", "WARN")
            self.root.after(0, lambda: _do_alert(data))

        threading.Thread(target=_fetch_and_show, daemon=True, name="AlertFetch").start()

    def _process_queue(self):
        if not self.running:
            return
        with self._queue_lock:
            messages = self._message_queue[:]
            self._message_queue.clear()
        batch     = messages[:4]
        remaining = messages[4:]
        if remaining:
            with self._queue_lock:
                self._message_queue = remaining + self._message_queue
        for msg in batch:
            try:
                if msg[0] == '_clear':
                    self._do_clear()
                elif msg[0] == 'translation':
                    self._render_translation(msg)
                else:
                    self._render_message(msg)
            except Exception as e:
                log_to_gui(f"Overlay render error: {e}", "ERROR")
        if self.settings_mode and not self.settings_border_ids:
            self._redraw_settings_border()
        self.root.after(20 if remaining else 40, self._process_queue)

    def _do_clear(self):
        self.canvas.delete('msg')
        self.message_blocks = []
        self._animated_items = {}

    def _render_message(self, msg):
        msg_type = msg[0]
        max_width = self.cfg['width'] - (self.padding * 2)
        items = []

        if msg_type == 'system':
            _, _, message, color, _, _ = msg[:6]
            lines = self._wrap_to_lines("» " + message, max_width, self.text_font)
            total_h = len(lines) * self.line_spacing + self.msg_block_spacing
            self._make_space(total_h)
            start_y = self._get_current_bottom()
            y = start_y

            bg_id = None
            if self.cfg.get('bg_enabled', True):
                bg_id = self.canvas.create_rectangle(
                    self.padding, start_y,
                    self.cfg['width'] - self.padding, start_y + total_h,
                    fill=self._get_bg_color_with_alpha(), outline='', tags='msg'
                )
                items.append(bg_id)

            for line in lines:
                self._draw_outlined_text(self.padding, y, line, self.text_font, color, items)
                y += self.line_spacing
            self.message_blocks.append({
                'start_y': start_y,
                'height': total_h,
                'items': items,
                'bg_id': bg_id   # может быть None
            })
            return

        if msg_type == 'chat':
            _, username, message, name_color, msg_color, badge = msg[:6]
            emotes_raw = msg[6] if len(msg) > 6 else ""
            command_response = msg[7] if len(msg) > 7 else None
            censored_ranges = msg[8] if len(msg) > 8 else []

            emotes_list = parse_emotes_tag(emotes_raw, message)

            if emotes_list:
                self._render_chat_with_emotes(
                    username, message, name_color, msg_color, badge,
                    emotes_list, max_width, items,
                    command_response=command_response,
                    censored_ranges=censored_ranges,
                )
            else:
                self._render_chat_text(
                    username, message, name_color, msg_color, badge,
                    max_width, items,
                    command_response=command_response,
                    censored_ranges=censored_ranges,
                )

    def _render_chat_text(self, username, message, name_color, msg_color,
                          badge, max_width, items,
                          command_response=None, censored_ranges=None):
        header_h = self.name_line_height
        NAME_TO_MSG_GAP = max(self.name_to_msg_gap, 6)

        msg_lines = self._wrap_to_lines(message, max_width, self.text_font)

        cmd_lines = []
        if command_response:
            cmd_lines = self._wrap_to_lines(command_response, max_width, self.text_font)

        total_h = (header_h + NAME_TO_MSG_GAP
                   + len(msg_lines) * self.line_spacing
                   + (len(cmd_lines) * self.line_spacing if cmd_lines else 0)
                   + self.msg_block_spacing)

        self._make_space(total_h)
        start_y = self._get_current_bottom()
        y = start_y

        bg_id = None
        if self.cfg.get('bg_enabled', True):
            bg_id = self.canvas.create_rectangle(
                self.padding, start_y,
                self.cfg['width'] - self.padding, start_y + total_h,
                fill=self._get_bg_color_with_alpha(), outline='', tags='msg'
            )
            items.append(bg_id)

        self._draw_name_header(self.padding, y, badge, username, name_color, items)
        y += header_h + NAME_TO_MSG_GAP

        if censored_ranges:
            self._draw_text_with_censorship(
                self.padding + 4, y, message, msg_color, items, censored_ranges
            )
            y += len(msg_lines) * self.line_spacing
        else:
            for line in msg_lines:
                self._draw_outlined_text(
                    self.padding + 4, y, line, self.text_font, msg_color, items
                )
                y += self.line_spacing

        if cmd_lines:
            for line in cmd_lines:
                self._draw_outlined_text(
                    self.padding + 8, y, line, self.text_font, '#FFCC44', items
                )
                y += self.line_spacing

        self.message_blocks.append({
            'start_y': start_y,
            'height': total_h,
            'items': items,
            'bg_id': bg_id
        })

    def _draw_text_with_censorship(self, x, y, text, base_color, items, censored_ranges):
        max_width = self.cfg['width'] - (self.padding * 2)
        lines = self._wrap_to_lines(text, max_width, self.text_font)

        char_offset = 0
        for line in lines:
            line_start = text.find(line, char_offset)
            if line_start == -1:
                line_start = char_offset

            segments = self._split_line_by_censorship(
                line, line_start, censored_ranges
            )

            cur_x = x
            for seg_text, is_censored in segments:
                if not seg_text:
                    continue
                if is_censored:
                    color = '#666666'
                    self._draw_outlined_text(
                        cur_x, y, seg_text, self.text_font, color, items
                    )
                else:
                    self._draw_outlined_text(
                        cur_x, y, seg_text, self.text_font, base_color, items
                    )
                cur_x += self.text_font.measure(seg_text)

            char_offset = line_start + len(line)
            y += self.line_spacing

    def _split_line_by_censorship(self, line, line_start_in_text, censored_ranges):
        if not censored_ranges:
            return [(line, False)]

        line_end = line_start_in_text + len(line)
        segments = []
        pos = 0

        for censor_start, censor_end in censored_ranges:
            overlap_start = max(censor_start - line_start_in_text, 0)
            overlap_end = min(censor_end - line_start_in_text, len(line))

            if overlap_start >= len(line) or overlap_end <= 0:
                continue

            if overlap_start > pos:
                segments.append((line[pos:overlap_start], False))

            segments.append((line[overlap_start:overlap_end], True))
            pos = overlap_end

        if pos < len(line):
            segments.append((line[pos:], False))

        return segments if segments else [(line, False)]

    def _render_translation(self, msg):
        _, username, original, translated, name_color = msg[:5]
        max_width = self.cfg['width'] - (self.padding * 2)
        items = []

        trans_text = f"  ↳ {translated}"
        lines = self._wrap_to_lines(trans_text, max_width - 16, self.text_font)
        total_h = len(lines) * self.line_spacing + 4

        self._make_space(total_h)
        start_y = self._get_current_bottom()
        y = start_y

        bg_id = None
        if self.cfg.get('bg_enabled', True):
            bg_id = self.canvas.create_rectangle(
                self.padding, start_y,
                self.cfg['width'] - self.padding, start_y + total_h,
                fill=self._get_bg_color_with_alpha(), outline='', tags='msg'
            )
            items.append(bg_id)

        for line in lines:
            translation_color = self.cfg.get('translation_color', '#44DDFF')
            self._draw_outlined_text(
                self.padding + 16, y, line, self.text_font, translation_color, items
            )
            y += self.line_spacing

        self.message_blocks.append({
            'start_y': start_y,
            'height': total_h,
            'items': items,
            'bg_id': bg_id
        })

    def _render_chat_with_emotes(self, username, message, name_color, msg_color,
                                  badge, emotes_list, max_width, items,
                                  command_response=None, censored_ranges=None):
        log_to_gui(f"[EMOTE] render_with_emotes: user={username}, emotes={emotes_list[:3]}", "INFO")
        parts = split_message_with_emotes(message, emotes_list)
        log_to_gui(f"[EMOTE] parts: {parts}", "INFO")

        emote_photos = {}
        missing_emotes = []

        for part in parts:
            if part[0] == 'emote':
                eid = part[1]
                if eid not in emote_photos:
                    photo = get_emote_photo(eid, self.root)
                    emote_photos[eid] = photo
                    if photo is None:
                        missing_emotes.append(eid)

        has_real_emotes = any(v is not None for v in emote_photos.values())

        # ==================== Блок, если эмодзи ещё не загружены ====================
        if not has_real_emotes and missing_emotes:
            self._schedule_emote_retry(
                username, message, name_color, msg_color, badge,
                emotes_list, command_response, censored_ranges,
                retry_count=0
            )
            msg_lines = self._wrap_to_lines(message, max_width, self.text_font)
            header_h = self.name_line_height
            NAME_TO_MSG_GAP = max(self.name_to_msg_gap, 6)
            total_h = (header_h + NAME_TO_MSG_GAP
                       + len(msg_lines) * self.line_spacing
                       + self.msg_block_spacing)
            self._make_space(total_h)
            start_y = self._get_current_bottom()
            y = start_y

            bg_id = None
            if self.cfg.get('bg_enabled', True):
                bg_id = self.canvas.create_rectangle(
                    self.padding, start_y,
                    self.cfg['width'] - self.padding, start_y + total_h,
                    fill=self._get_bg_color_with_alpha(), outline='', tags='msg'
                )
                items.append(bg_id)

            self._draw_name_header(self.padding, y, badge, username, name_color, items)
            y += header_h + NAME_TO_MSG_GAP
            for line in msg_lines:
                self._draw_outlined_text(
                    self.padding + 4, y, line, self.text_font, msg_color, items
                )
                y += self.line_spacing
            self.message_blocks.append({
                'start_y': start_y,
                'height': total_h,
                'items': items,
                'bg_id': bg_id,
                '_pending_emotes': True
            })
            return

        # ==================== Основной блок (эмодзи загружены) ====================
        EMOTE_SIZE = 22
        EMOTE_W = EMOTE_SIZE + 6
        EMOTE_H = EMOTE_SIZE
        EMOTE_PAD_LEFT = 3
        EMOTE_PAD_RIGHT = 3
        indent = 4
        NAME_TO_MSG_GAP = max(self.name_to_msg_gap, 6)

        lines_content = []
        current_line = []
        current_line_w = 0

        for pi, part in enumerate(parts):
            if part[0] == 'text':
                text = part[1]
                if not text:
                    continue
                words = text.split(' ')
                for wi, word in enumerate(words):
                    if not word:
                        if current_line:
                            current_line_w += self.text_font.measure(' ')
                        continue

                    word_display = word
                    need_space = False
                    if current_line and wi > 0:
                        need_space = True
                    elif current_line and wi == 0:
                        if current_line[-1][0] == 'emote':
                            need_space = True

                    if need_space:
                        word_display = ' ' + word

                    w = self.text_font.measure(word_display)

                    if current_line_w + w > max_width - indent and current_line:
                        lines_content.append(current_line)
                        current_line = []
                        current_line_w = 0
                        word_display = word
                        w = self.text_font.measure(word_display)

                    current_line.append(('text', word_display))
                    current_line_w += w

            elif part[0] == 'emote':
                eid = part[1]
                ename = part[2] if len(part) > 2 else ""

                total_emote_w = EMOTE_PAD_LEFT + EMOTE_W + EMOTE_PAD_RIGHT
                total_emote_w_check = total_emote_w if current_line else EMOTE_W + EMOTE_PAD_RIGHT

                if current_line_w + total_emote_w_check > max_width - indent and current_line:
                    lines_content.append(current_line)
                    current_line = []
                    current_line_w = 0

                if emote_photos.get(eid) is not None:
                    current_line.append(('emote', eid))
                    if current_line_w > 0:
                        current_line_w += EMOTE_PAD_LEFT + EMOTE_W + EMOTE_PAD_RIGHT
                    else:
                        current_line_w += EMOTE_W + EMOTE_PAD_RIGHT
                else:
                    fallback = ename or f":{eid}:"
                    if current_line:
                        fallback = ' ' + fallback
                    w = self.text_font.measure(fallback)
                    current_line.append(('text', fallback))
                    current_line_w += w

        if current_line:
            lines_content.append(current_line)

        if not lines_content:
            lines_content = [[('text', message)]]

        header_h = self.name_line_height
        text_line_h = self.line_spacing
        emote_line_h = max(self.line_spacing, EMOTE_H + 6)

        line_heights = []
        for line_parts in lines_content:
            has_emote_in_line = any(lp[0] == 'emote' for lp in line_parts)
            line_heights.append(emote_line_h if has_emote_in_line else text_line_h)

        total_content_h = sum(line_heights)
        total_h = header_h + NAME_TO_MSG_GAP + total_content_h + self.msg_block_spacing

        self._make_space(total_h)
        start_y = self._get_current_bottom()
        y = start_y

        # ----- Прямоугольник фона (с проверкой) -----
        bg_id = None
        if self.cfg.get('bg_enabled', True):
            bg_id = self.canvas.create_rectangle(
                self.padding, start_y,
                self.cfg['width'] - self.padding, start_y + total_h,
                fill=self._get_bg_color_with_alpha(), outline='', tags='msg'
            )
            items.append(bg_id)

        self._draw_name_header(self.padding, y, badge, username, name_color, items)
        y += header_h + NAME_TO_MSG_GAP

        for line_idx, line_parts in enumerate(lines_content):
            x = self.padding + indent
            line_h = line_heights[line_idx]
            text_baseline_y = y + (line_h - self.text_font.metrics('linespace')) // 2

            for lpi, lp in enumerate(line_parts):
                if lp[0] == 'text':
                    text_str = lp[1]
                    if text_str:
                        self._draw_outlined_text(
                            x, text_baseline_y, text_str,
                            self.text_font, msg_color, items
                        )
                        x += self.text_font.measure(text_str)

                elif lp[0] == 'emote':
                    eid = lp[1]
                    photo = emote_photos.get(eid)
                    if photo:
                        if lpi > 0:
                            x += EMOTE_PAD_LEFT
                        emote_y = y + (line_h - EMOTE_H) // 2
                        img_id = self.canvas.create_image(
                            x, emote_y, image=photo, anchor='nw', tags='msg'
                        )
                        items.append(img_id)
                        self._register_animated_item(img_id, eid)
                        x += EMOTE_SIZE + EMOTE_PAD_RIGHT

            y += line_h

        if command_response:
            cmd_lines = self._wrap_to_lines(command_response, max_width, self.text_font)
            for line in cmd_lines:
                self._draw_outlined_text(
                    self.padding + 8, y, line, self.text_font, '#FFCC44', items
                )
                y += self.line_spacing
            total_h += len(cmd_lines) * self.line_spacing

        self.message_blocks.append({
            'start_y': start_y,
            'height': total_h,
            'items': items,
            'bg_id': bg_id
        })

    def _schedule_emote_retry(self, username, message, name_color, msg_color,
                               badge, emotes_list, command_response, censored_ranges,
                               retry_count=0):
        MAX_RETRIES = 20
        RETRY_DELAY = 400

        if retry_count >= MAX_RETRIES:
            return

        def _check():
            if not self.running:
                return

            all_ready = True
            for _, _, eid in emotes_list:
                if eid not in _emote_images or _emote_images[eid] is None:
                    gif_path = os.path.join(EMOTE_CACHE_DIR, f"{eid}.gif")
                    png_path = os.path.join(EMOTE_CACHE_DIR, f"{eid}.png")
                    path = None
                    if os.path.exists(gif_path):
                        path = gif_path
                    elif os.path.exists(png_path):
                        path = png_path

                    if path:
                        _load_emote_from_file(eid, path, self.root)

                    if eid not in _emote_images or _emote_images[eid] is None:
                        all_ready = False

            if all_ready:
                if self.message_blocks:
                    last_block = self.message_blocks[-1]
                    if last_block.get('_pending_emotes'):
                        for iid in last_block['items']:
                            self._animated_items.pop(iid, None)
                            try:
                                self.canvas.delete(iid)
                            except Exception:
                                pass
                        self.message_blocks.pop()

                max_width = self.cfg['width'] - (self.padding * 2)
                items = []
                self._render_chat_with_emotes(
                    username, message, name_color, msg_color, badge,
                    emotes_list, max_width, items,
                    command_response=command_response,
                    censored_ranges=censored_ranges,
                )
            else:
                self.root.after(
                    RETRY_DELAY,
                    lambda: self._schedule_emote_retry(
                        username, message, name_color, msg_color, badge,
                        emotes_list, command_response, censored_ranges,
                        retry_count + 1
                    )
                )

        self.root.after(RETRY_DELAY, _check)

    def update_config(self, new_cfg):
        old_w = self.cfg['width']
        old_h = self.cfg['height']
        old_bg = self.cfg.get('bg_color')
        old_trans = self.cfg.get('translation_color')
        old_enabled = self.cfg.get('bg_enabled', True)
        
        self.cfg.update(new_cfg)
        self._apply_geometry()
        self.root.attributes('-alpha', self.cfg['opacity'])
        
        if (self.text_font.cget('size') != self.cfg['font_size']
                or self.text_font.cget('family') != self.cfg['font_family']):
            self.text_font.configure(size=self.cfg['font_size'], family=self.cfg['font_family'])
            self.name_font.configure(
                size=max(9, self.cfg['font_size'] - 2), family=self.cfg['font_family']
            )
            self.line_spacing = self.cfg['font_size'] + 8
            self.name_line_height = max(9, self.cfg['font_size'] - 2) + 8

        # Если изменился цвет фона или его включение – перерисовываем всё
        if (self.cfg.get('bg_color') != old_bg or
            self.cfg.get('bg_enabled', True) != old_enabled):
            self._do_clear()

        # Если изменился цвет перевода – перерисовываем
        if self.cfg.get('translation_color') != old_trans:
            self._do_clear()

        # Если изменились размеры окна – перерисовываем
        if old_w != self.cfg['width'] or old_h != self.cfg['height']:
            self._do_clear()
            
        if self.settings_mode:
            self._redraw_settings_border()
        self.root.after(100, self._make_click_through)

    def show(self):
        self.visible = True
        self.root.deiconify()
        self.root.after(50, self._make_click_through)

    def hide(self):
        self.visible = False
        self.root.withdraw()

    def close(self):
        self.running = False
        self._animation_running = False
        self._animated_items = {}
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


class ControlPanel:
    WIN_W = 760
    WIN_H = 670

    def __init__(self, overlay: GhostOverlay, tray_ref=None):
        self.overlay       = overlay
        self.tray_ref      = tray_ref
        self.window        = None
        self.log_text      = None
        self.sliders       = {}
        self.is_open       = False
        self.max_log_lines = 500
        self.app_state     = load_app_state()
        self._slider_debounce = {}
        self.channel_entry = None
        self.connect_btn   = None
        self.disconnect_btn = None
        self.status_label  = None
        self.current_channel_label = None
        self.brand_label   = None
        self._status_poll_id = None
        self._notebook     = None

    def _color_setting(self, parent, label_text, key):
        """Добавляет строку с полем ввода цвета и кнопкой выбора."""
        frame = tk.Frame(parent, bg='#1e1e1e')
        frame.pack(fill=tk.X, pady=4)

        tk.Label(frame, text=label_text, font=('Segoe UI', 10),
                 bg='#1e1e1e', fg='#aaaaaa', width=20, anchor='w').pack(side=tk.LEFT)

        var = tk.StringVar(value=self.overlay.cfg.get(key, '#000000'))
        entry = tk.Entry(frame, textvariable=var, width=10,
                         bg='#0d0d0d', fg='white', relief='flat',
                         font=('Consolas', 10))
        entry.pack(side=tk.LEFT, padx=(5, 5))

        def pick_color():
            from tkinter import colorchooser
            color = colorchooser.askcolor(title="Choose color", initialcolor=var.get())
            if color and color[1]:
                var.set(color[1])
                self.overlay.cfg[key] = color[1]
                self.overlay.update_config(self.overlay.cfg)
                self.overlay._do_clear()  # перерисовываем все сообщения с новым цветом

        btn = tk.Button(frame, text="🎨", command=pick_color,
                        bg='#3a3a3a', fg='white', relief='flat',
                        padx=6, pady=2, cursor='hand2')
        btn.pack(side=tk.LEFT)

        def on_color_change(*args):
            val = var.get().strip()
            if re.match(r'^#[0-9a-fA-F]{6}$', val):
                self.overlay.cfg[key] = val
                self.overlay.update_config(self.overlay.cfg)
                self.overlay._do_clear()

        var.trace('w', on_color_change)

    def _save_on_close(self):
        try:
            if self.window and self.window.winfo_exists() and self.channel_entry:
                channel = self.channel_entry.get().strip()
                if channel:
                    state = load_app_state()
                    state['last_channel'] = channel
                    save_app_state(state)
        except Exception:
            pass

    def open(self):
        if self.is_open and self.window is not None:
            try:
                self.window.lift()
                self.window.focus_force()
                return
            except Exception:
                pass

        self.window = tk.Toplevel(self.overlay.root)
        self.window.title(f"{t('app_title')} v{APP_VERSION}")
        self.window.configure(bg='#1e1e1e')
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        self.window.geometry(
            f"{self.WIN_W}x{self.WIN_H}+{(sw-self.WIN_W)//2}+{(sh-self.WIN_H)//2}"
        )
        self.window.minsize(640, 540)
        self._build_all()
        self.is_open = True
        self._poll_logs()
        self._poll_stats()
        self._poll_status()
        
        self.window.bind('<Destroy>', lambda e: self._save_on_close())

    def _show_about(self):
        about_text = t("about_text", 
                       name=APP_NAME,
                       version=APP_VERSION,
                       author=APP_AUTHOR,
                       year=APP_YEAR,
                       description=APP_DESCRIPTION)
        
        about_window = tk.Toplevel(self.window)
        about_window.title(t("about_title"))
        about_window.configure(bg='#1e1e1e')
        about_window.geometry("400x250")
        about_window.resizable(False, False)
        
        about_window.transient(self.window)
        about_window.grab_set()
        
        tk.Label(about_window, text="🎬", font=('Segoe UI', 48),
                 bg='#1e1e1e', fg='#9146FF').pack(pady=(20, 5))
        
        tk.Label(about_window, text=f"{APP_NAME} v{APP_VERSION}",
                 font=('Segoe UI', 16, 'bold'), bg='#1e1e1e', fg='#FFFFFF').pack()
        
        tk.Label(about_window, text=f"{t('about_developer', author=APP_AUTHOR)}",
                 font=('Segoe UI', 10), bg='#1e1e1e', fg='#888888').pack(pady=(5, 0))
        
        tk.Label(about_window, text=APP_YEAR,
                 font=('Segoe UI', 10), bg='#1e1e1e', fg='#666666').pack()
        
        tk.Label(about_window, text=APP_DESCRIPTION,
                 font=('Segoe UI', 9), bg='#1e1e1e', fg='#aaaaaa',
                 wraplength=350, justify='center').pack(pady=(15, 10))
        
        tk.Button(about_window, text="OK", command=about_window.destroy,
                  bg='#9146FF', fg='white', font=('Segoe UI', 10, 'bold'),
                  relief='flat', padx=30, pady=8, cursor='hand2').pack(pady=10)

    def _build_all(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('TNotebook', background='#1e1e1e', borderwidth=0)
        style.configure('TNotebook.Tab', background='#2a2a2a', foreground='#cccccc',
                        padding=[18, 8], font=('Segoe UI', 10))
        style.map('TNotebook.Tab',
                  background=[('selected', '#9146FF')],
                  foreground=[('selected', 'white')])
        style.configure('TScale', background='#1e1e1e', troughcolor='#333333')

        saved_lang = self.app_state.get('language', 'en')
        set_language(saved_lang)

        self._build_status_bar()
        self._notebook = ttk.Notebook(self.window)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        for tab_key, builder in [
            ("tab_connection", self._build_connection_tab),
            ("tab_logs",       self._build_log_tab),
            ("tab_settings",   self._build_settings_tab),
            ("tab_stats",      self._build_stats_tab),
            ("tab_alerts",     self._build_alerts_tab),
        ]:
            frame = tk.Frame(self._notebook, bg='#1e1e1e')
            self._notebook.add(frame, text=t(tab_key))
            builder(frame)

        def on_tab_change(event):
            idx = self._notebook.index(self._notebook.select())
            self.overlay.set_settings_mode(idx == 2)
        self._notebook.bind('<<NotebookTabChanged>>', on_tab_change)

    def _rebuild_ui(self):
        if not self.window:
            return
        for widget in self.window.winfo_children():
            widget.destroy()
        self.window.title(t("app_title"))
        self._build_all()
        if self.tray_ref:
            self.tray_ref.rebuild_menu()
        
        if hasattr(self, '_notebook') and self._notebook:
            self._notebook.select(0)
            self.overlay.set_settings_mode(False)

    def _build_status_bar(self):
        bar = tk.Frame(self.window, bg='#0d0d0d', height=42)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        inner = tk.Frame(bar, bg='#0d0d0d')
        inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        tk.Label(inner, text="🎬 ", font=('Segoe UI', 14),
                 bg='#0d0d0d', fg='#9146FF').pack(side=tk.LEFT)
        self.brand_label = tk.Label(inner, text=f"{t('app_brand')} v{APP_VERSION}",
            font=('Segoe UI', 11, 'bold'), bg='#0d0d0d', fg='#FFFFFF')
        self.brand_label.pack(side=tk.LEFT)
        
        dev_label = tk.Label(inner, text=f"  |  {t('about_developer', author=APP_AUTHOR)}",
            font=('Segoe UI', 9), bg='#0d0d0d', fg='#666666')
        dev_label.pack(side=tk.LEFT, padx=(8, 0))
        
        self.status_label = tk.Label(inner, text=t("status_disconnected"),
            font=('Segoe UI', 10, 'bold'), bg='#0d0d0d', fg='#888888')
        self.status_label.pack(side=tk.RIGHT)
        self.current_channel_label = tk.Label(inner, text="",
            font=('Consolas', 10, 'bold'), bg='#0d0d0d', fg='#9146FF')
        self.current_channel_label.pack(side=tk.RIGHT, padx=(0, 10))

    def _build_connection_tab(self, parent):
        outer = tk.Frame(parent, bg='#1e1e1e', padx=32, pady=24)
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(outer, text=t("conn_title"), font=('Segoe UI', 16, 'bold'),
                 bg='#1e1e1e', fg='#9146FF').pack(pady=(0, 6), anchor='w')
        tk.Label(outer, text=t("conn_subtitle"), font=('Segoe UI', 10),
                 bg='#1e1e1e', fg='#888888', justify='left').pack(pady=(0, 24), anchor='w')

        card = tk.Frame(outer, bg='#252525', padx=24, pady=20)
        card.pack(fill=tk.X)

        tk.Label(card, text=t("conn_channel_label"), font=('Segoe UI', 11, 'bold'),
                 bg='#252525', fg='#cccccc').pack(anchor='w', pady=(0, 8))

        entry_frame = tk.Frame(card, bg='#0d0d0d',
                               highlightbackground='#9146FF', highlightthickness=1)
        entry_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(entry_frame, text="  # ", font=('Consolas', 14, 'bold'),
                 bg='#0d0d0d', fg='#9146FF').pack(side=tk.LEFT)
        self.channel_entry = tk.Entry(entry_frame, font=('Consolas', 14),
            bg='#0d0d0d', fg='#FFFFFF', insertbackground='#9146FF', relief='flat', bd=0)
        self.channel_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(0, 8))
        self.channel_entry.insert(0, self.app_state.get('last_channel', ''))
        self.channel_entry.bind('<Return>', lambda e: self._on_connect_click())

        self.conn_error_label = tk.Label(card, text="", font=('Segoe UI', 9),
                                         bg='#252525', fg='#FF5555')
        self.conn_error_label.pack(anchor='w', pady=(4, 12))

        btn_frame = tk.Frame(card, bg='#252525')
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        self.connect_btn = tk.Button(btn_frame, text=t("btn_connect"),
            command=self._on_connect_click, bg='#9146FF', fg='white',
            font=('Segoe UI', 11, 'bold'), relief='flat', padx=30, pady=12,
            cursor='hand2', activebackground='#7a36d6', activeforeground='white')
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.disconnect_btn = tk.Button(btn_frame, text=t("btn_disconnect"),
            command=self._on_disconnect_click, bg='#444444', fg='white',
            font=('Segoe UI', 11), relief='flat', padx=30, pady=12,
            cursor='hand2', activebackground='#666666', activeforeground='white',
            state='disabled')
        self.disconnect_btn.pack(side=tk.LEFT)

        hint = tk.Frame(outer, bg='#1e1e1e')
        hint.pack(fill=tk.X, pady=(20, 0))
        tk.Label(hint, text=t("hint_title"), font=('Segoe UI', 9, 'bold'),
                 bg='#1e1e1e', fg='#FFCC44').pack(anchor='w')
        tk.Label(hint, text=t("hint_lines") + ANON_NICK, font=('Segoe UI', 9),
                 bg='#1e1e1e', fg='#888888', justify='left').pack(anchor='w', pady=(4, 0))

    def _on_connect_click(self):
        raw = self.channel_entry.get().strip()
        ok, val = validate_channel_name(raw)
        if not ok:
            self.conn_error_label.config(text=f"✗ {val}")
            return
        self.conn_error_label.config(text="")
        self.app_state['last_channel'] = val
        save_app_state(self.app_state)  # Уже есть
        chat_command.put(f"CONNECT:{val}")
        log_to_gui(t("log_connect_request", ch=val), "INFO")

    def _on_disconnect_click(self):
        chat_command.put("DISCONNECT")
        log_to_gui(t("log_disconnect_request"), "INFO")

    def _poll_status(self):
        if not self.is_open or self.window is None:
            return
        try:
            with connection_lock:
                connected  = connection_state['connected']
                connecting = connection_state['connecting']
                current    = connection_state['current_channel']
            ch_text = f"#{current}" if current else ""
            if connected:
                self.status_label.config(text=t("status_connected"), fg='#55FF77')
                self.current_channel_label.config(text=ch_text)
                if self.connect_btn:
                    self.connect_btn.config(state='disabled', bg='#444444')
                if self.disconnect_btn:
                    self.disconnect_btn.config(state='normal', bg='#aa3333')
            elif connecting:
                self.status_label.config(text=t("status_connecting"), fg='#FFCC44')
                self.current_channel_label.config(text=ch_text)
                if self.connect_btn:
                    self.connect_btn.config(state='disabled', bg='#444444')
                if self.disconnect_btn:
                    self.disconnect_btn.config(state='normal', bg='#aa3333')
            else:
                self.status_label.config(text=t("status_disconnected"), fg='#888888')
                self.current_channel_label.config(text="")
                if self.connect_btn:
                    self.connect_btn.config(state='normal', bg='#9146FF')
                if self.disconnect_btn:
                    self.disconnect_btn.config(state='disabled', bg='#444444')
            self._status_poll_id = self.window.after(500, self._poll_status)
        except Exception:
            pass

    def _build_log_tab(self, parent):
        top = tk.Frame(parent, bg='#1e1e1e')
        top.pack(fill=tk.X, padx=8, pady=(8, 4))
        tk.Label(top, text=t("log_title"), font=('Segoe UI', 11, 'bold'),
                 bg='#1e1e1e', fg='#9146FF').pack(side=tk.LEFT)
        tk.Button(top, text=t("btn_clear_log"), command=self._clear_log,
                  bg='#3a3a3a', fg='white', font=('Segoe UI', 9),
                  relief='flat', padx=12, pady=4, cursor='hand2').pack(side=tk.RIGHT, padx=2)
        tk.Button(top, text=t("btn_clear_overlay"), command=self.overlay.clear,
                  bg='#3a3a3a', fg='white', font=('Segoe UI', 9),
                  relief='flat', padx=12, pady=4, cursor='hand2').pack(side=tk.RIGHT, padx=2)

        log_frame = tk.Frame(parent, bg='#0d0d0d')
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        scrollbar = tk.Scrollbar(log_frame, bg='#1e1e1e', troughcolor='#0d0d0d')
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text = tk.Text(log_frame, bg='#0d0d0d', fg='#d0d0d0',
            font=('Consolas', 10), yscrollcommand=scrollbar.set,
            wrap='word', relief='flat', bd=0, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)
        self.log_text.tag_config('time',  foreground='#666666')
        self.log_text.tag_config('INFO',  foreground='#5599FF')
        self.log_text.tag_config('OK',    foreground='#55FF77')
        self.log_text.tag_config('WARN',  foreground='#FFCC44')
        self.log_text.tag_config('ERROR', foreground='#FF5555')
        self.log_text.tag_config('CHAT',  foreground='#d0d0d0')
        self.log_text.tag_config('user',  foreground='#9146FF',
                                          font=('Consolas', 10, 'bold'))
        self.log_text.tag_config('badge', foreground='#FFCC44',
                                          font=('Consolas', 9, 'bold'))

    def _build_settings_tab(self, parent):
        canvas = tk.Canvas(parent, bg='#1e1e1e', highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        scrollable = tk.Frame(canvas, bg='#1e1e1e')
        scrollable.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        main = tk.Frame(scrollable, bg='#1e1e1e', padx=24, pady=18)
        main.pack(fill=tk.BOTH, expand=True)
        tk.Label(main, text=t("settings_title"), font=('Segoe UI', 14, 'bold'),
                 bg='#1e1e1e', fg='#9146FF').pack(pady=(0, 4), anchor='w')
        tk.Label(main, text=t("settings_hint"), font=('Segoe UI', 9),
                 bg='#1e1e1e', fg='#888888', justify='left').pack(pady=(0, 16), anchor='w')

        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()

        # ----- Позиция и размер -----
        self._section_title(main, t("section_position"))
        self._slider(main, t("slider_x"),   'x',            0,   sw - 100)
        self._slider(main, t("slider_y"),   'y',            0,   sh - 100)
        self._slider(main, t("slider_w"),   'width',        200, 1600)
        self._slider(main, t("slider_h"),   'height',       100, 1000)

        # ----- Внешний вид -----
        self._section_title(main, t("section_appearance"))
        self._slider(main, t("slider_opacity"),  'opacity',      0.1, 1.0, is_float=True)
        self._slider(main, t("slider_font"),     'font_size',    8,   32)
        self._slider(main, t("slider_max_msg"),  'max_messages', 20,  300)

        # ----- Включение фона сообщений (галочка) -----
        bg_enabled_var = tk.BooleanVar(value=self.overlay.cfg.get('bg_enabled', True))
        def on_bg_toggle():
            self.overlay.cfg['bg_enabled'] = bg_enabled_var.get()
            self.overlay.update_config(self.overlay.cfg)
        cb = tk.Checkbutton(main, text=t("settings_show_bg"),
                            variable=bg_enabled_var, command=on_bg_toggle,
                            bg='#1e1e1e', fg='white', selectcolor='#9146FF',
                            activebackground='#1e1e1e', activeforeground='white',
                            font=('Segoe UI', 10))
        cb.pack(anchor='w', pady=4)

        # ----- Язык -----
        self._section_title(main, t("section_language"))
        self._build_language_selector(main)

        # ----- Цвет перевода -----
        self._section_title(main, "🎨 " + t("settings_translation_color"))
        self._color_setting(main, t("settings_translation_color") + ":", "translation_color")

        # ----- Кнопки -----
        btn_frame = tk.Frame(main, bg='#1e1e1e')
        btn_frame.pack(pady=20, fill=tk.X)
        self.save_btn = tk.Button(btn_frame, text=t("btn_save"), command=self._save,
            bg='#2d5a27', fg='white', font=('Segoe UI', 10, 'bold'),
            relief='flat', padx=20, pady=10, cursor='hand2')
        self.save_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Button(btn_frame, text=t("btn_reset"), command=self._reset,
            bg='#444444', fg='white', font=('Segoe UI', 10),
            relief='flat', padx=20, pady=10, cursor='hand2').pack(
            side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    def _build_language_selector(self, parent):
        frame = tk.Frame(parent, bg='#1e1e1e')
        frame.pack(fill=tk.X, pady=4)
        current = self.app_state.get('language', 'en')

        def make_btn(code, label):
            is_active = (current == code)
            btn = tk.Button(frame, text=label,
                command=lambda: self._change_language(code),
                bg='#9146FF' if is_active else '#3a3a3a', fg='white',
                font=('Segoe UI', 10, 'bold' if is_active else 'normal'),
                relief='flat', padx=20, pady=8, cursor='hand2',
                activebackground='#7a36d6', activeforeground='white')
            return btn

        btn_en = make_btn('en', t("lang_en"))
        btn_ru = make_btn('ru', t("lang_ru"))
        btn_en.pack(side=tk.LEFT, padx=(0, 8))
        btn_ru.pack(side=tk.LEFT)
        
        self.lang_btn_en = btn_en
        self.lang_btn_ru = btn_ru

    def _change_language(self, lang):
        if lang == self.app_state.get('language'):
            return
        self.app_state['language'] = lang
        save_app_state(self.app_state)
        set_language(lang)
        _build_profanity_pattern()
        log_to_gui(t("log_lang_changed"), "OK")
        self._rebuild_ui()

    def _build_stats_tab(self, parent):
        main = tk.Frame(parent, bg='#1e1e1e', padx=24, pady=18)
        main.pack(fill=tk.BOTH, expand=True)
        tk.Label(main, text=t("stats_title"), font=('Segoe UI', 14, 'bold'),
                 bg='#1e1e1e', fg='#9146FF').pack(pady=(0, 16), anchor='w')
        self.stats_labels = {}
        rows = [
            ('channel',    t("stats_channel")),
            ('duration',   t("stats_duration")),
            ('messages',   t("stats_messages")),
            ('users',      t("stats_users")),
            ('mods',       t("stats_mods")),
            ('subs',       t("stats_subs")),
            ('vips',       t("stats_vips")),
            ('reconnects', t("stats_reconnects")),
            ('errors',     t("stats_errors")),
            ('pings',      t("stats_pings")),
        ]
        for key, label_text in rows:
            row = tk.Frame(main, bg='#1e1e1e')
            row.pack(fill=tk.X, pady=4)
            tk.Label(row, text=label_text, font=('Segoe UI', 10),
                     bg='#1e1e1e', fg='#888888', width=22, anchor='w').pack(side=tk.LEFT)
            val = tk.Label(row, text='—', font=('Consolas', 11, 'bold'),
                           bg='#1e1e1e', fg='#00FFAA', anchor='w')
            val.pack(side=tk.LEFT)
            self.stats_labels[key] = val

    def _section_title(self, parent, text):
        tk.Label(parent, text=text, font=('Segoe UI', 11, 'bold'),
                 bg='#1e1e1e', fg='#9146FF', anchor='w').pack(fill=tk.X, pady=(10, 6))

    def _slider(self, parent, label_text, key, min_val, max_val, is_float=False):
        frame = tk.Frame(parent, bg='#1e1e1e')
        frame.pack(fill=tk.X, pady=4)
        top = tk.Frame(frame, bg='#1e1e1e')
        top.pack(fill=tk.X)
        tk.Label(top, text=label_text, font=('Segoe UI', 10),
                 bg='#1e1e1e', fg='#aaaaaa').pack(side=tk.LEFT)
        val_label = tk.Label(top, text=str(self.overlay.cfg[key]),
            font=('Consolas', 10, 'bold'), bg='#1e1e1e', fg='#00ff00', width=8)
        val_label.pack(side=tk.RIGHT)
        slider = ttk.Scale(frame, from_=min_val, to=max_val, orient='horizontal', length=500)
        slider.set(self.overlay.cfg[key])
        slider.pack(fill=tk.X, pady=(3, 0))

        def on_slide(val, k=key, vl=val_label, isf=is_float):
            v = round(float(val), 2) if isf else int(float(val))
            vl.config(text=str(v))
            self.overlay.cfg[k] = v
            if k in self._slider_debounce:
                try:
                    self.window.after_cancel(self._slider_debounce[k])
                except Exception:
                    pass
            self._slider_debounce[k] = self.window.after(
                30, lambda: self.overlay.update_config(self.overlay.cfg))

        slider.configure(command=on_slide)
        self.sliders[key] = slider

    def _save(self):
        save_overlay_config(self.overlay.cfg)
        orig = self.save_btn['text']
        self.save_btn.config(text=t("btn_saved"), bg='#1e7a1e')
        self.window.after(1200, lambda: self.save_btn.config(text=orig, bg='#2d5a27'))
        log_to_gui(t("log_settings_saved"), "OK")

    def _reset(self):
        new_cfg = DEFAULT_OVERLAY_CONFIG.copy()
        self.overlay.update_config(new_cfg)
        for key, slider in self.sliders.items():
            if key in new_cfg:
                slider.set(new_cfg[key])
        # Обновляем поля ввода цвета (если они есть) – можно пройтись по всем _color_setting виджетам
        # Проще перестроить интерфейс:
        self._rebuild_ui()
        log_to_gui(t("log_settings_reset"), "INFO")

    def _clear_log(self):
        if self.log_text:
            self.log_text.config(state='normal')
            self.log_text.delete('1.0', tk.END)
            self.log_text.config(state='disabled')

    def _poll_logs(self):
        if not self.is_open or self.window is None:
            return
        try:
            count = 0
            while count < 50:
                try:
                    item = log_queue.get_nowait()
                except queue.Empty:
                    break
                self._append_log(item)
                count += 1
            if self.log_text:
                line_count = int(self.log_text.index('end-1c').split('.')[0])
                if line_count > self.max_log_lines:
                    self.log_text.config(state='normal')
                    self.log_text.delete('1.0', f'{line_count - self.max_log_lines}.0')
                    self.log_text.config(state='disabled')
            self.window.after(100, self._poll_logs)
        except Exception:
            pass

    def _append_log(self, item):
        if not self.log_text:
            return
        try:
            self.log_text.config(state='normal')
            kind = item[0]
            if kind == 'system':
                _, ts, level, message = item
                self.log_text.insert(tk.END, f"[{ts}] ", 'time')
                self.log_text.insert(tk.END, f"[{level}] ", level)
                self.log_text.insert(tk.END, f"{message}\n", 'CHAT')
            elif kind == 'chat':
                _, ts, user, badges, message = item
                self.log_text.insert(tk.END, f"[{ts}] ", 'time')
                if badges:
                    self.log_text.insert(tk.END, f"[{'/'.join(badges)}] ", 'badge')
                self.log_text.insert(tk.END, f"{user}", 'user')
                self.log_text.insert(tk.END, f": {message}\n", 'CHAT')
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        except Exception:
            pass

    def _poll_stats(self):
        if not self.is_open or self.window is None:
            return
        try:
            duration = time.time() - stats['session_start']
            h = int(duration // 3600)
            m = int((duration % 3600) // 60)
            s = int(duration % 60)
            current_channel = connection_state.get('current_channel') or '—'
            updates = {
                'channel':    f"#{current_channel}" if current_channel != '—' else '—',
                'duration':   f"{h:02d}:{m:02d}:{s:02d}",
                'messages':   str(stats['total_messages']),
                'users':      str(len(stats['unique_users_hashed'])),
                'mods':       str(len(stats['users_by_role']['moderators'])),
                'subs':       str(len(stats['users_by_role']['subscribers'])),
                'vips':       str(len(stats['users_by_role']['vips'])),
                'reconnects': str(stats['reconnects']),
                'errors':     str(stats['errors']),
                'pings':      str(stats['irc_pings']),
            }
            for k, v in updates.items():
                if k in self.stats_labels:
                    self.stats_labels[k].config(text=v)
            self.window.after(1000, self._poll_stats)
        except Exception:
            pass

    def _on_close(self):
        self.is_open = False
        self.overlay.set_settings_mode(False)
        
        try:
            if self.channel_entry and self.window and self.window.winfo_exists():
                channel = self.channel_entry.get().strip()
                if channel:
                    self.app_state['last_channel'] = channel
                    save_app_state(self.app_state)
        except Exception:
            pass
        
        if self._status_poll_id:
            try:
                self.window.after_cancel(self._status_poll_id)
            except Exception:
                pass
        try:
            if self.window:
                self.window.destroy()
        except Exception:
            pass
        self.window = None

    def _build_alerts_tab(self, parent):
        outer = tk.Frame(parent, bg='#1e1e1e', padx=20, pady=16)
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(outer, text=t("alerts_title"),
                 font=('Segoe UI', 14, 'bold'), bg='#1e1e1e', fg='#9146FF').pack(anchor='w', pady=(0, 4))
        tk.Label(outer, text=t("alerts_subtitle"),
                 font=('Segoe UI', 9), bg='#1e1e1e', fg='#888888').pack(anchor='w', pady=(0, 14))

        glob_frame = tk.Frame(outer, bg='#252525', padx=12, pady=10)
        glob_frame.pack(fill=tk.X, pady=(0, 10))

        self._alerts_enabled_var = tk.BooleanVar(value=_alerts_config.get('enabled', True))
        tk.Checkbutton(glob_frame, text=t("alerts_enable"), variable=self._alerts_enabled_var,
                       bg='#252525', fg='white', selectcolor='#9146FF',
                       activebackground='#252525', activeforeground='white',
                       font=('Segoe UI', 10),
                       command=self._save_alerts_global).pack(side=tk.LEFT)

        tk.Label(glob_frame, text=t("alerts_cooldown"), bg='#252525', fg='#aaaaaa',
                 font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=(20, 4))
        self._cooldown_var = tk.StringVar(value=str(_alerts_config.get('cooldown', 10)))
        cooldown_entry = tk.Entry(glob_frame, textvariable=self._cooldown_var, width=5,
                                  bg='#0d0d0d', fg='white', insertbackground='white',
                                  relief='flat', font=('Consolas', 10))
        cooldown_entry.pack(side=tk.LEFT)
        cooldown_entry.bind('<Return>', lambda e: self._save_alerts_global())
        cooldown_entry.bind('<FocusOut>', lambda e: self._save_alerts_global())

        list_frame = tk.Frame(outer, bg='#1e1e1e')
        list_frame.pack(fill=tk.BOTH, expand=True)

        list_scroll = tk.Scrollbar(list_frame)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._alerts_listbox = tk.Listbox(list_frame,
            bg='#0d0d0d', fg='#d0d0d0', selectbackground='#9146FF',
            font=('Consolas', 10), relief='flat', bd=0,
            yscrollcommand=list_scroll.set, height=8)
        self._alerts_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.config(command=self._alerts_listbox.yview)
        self._alerts_listbox.bind('<<ListboxSelect>>', self._on_alert_select)

        editor = tk.Frame(outer, bg='#252525', padx=14, pady=12)
        editor.pack(fill=tk.X, pady=(10, 0))

        def lbl(row, col, text):
            tk.Label(row, text=text, bg='#252525', fg='#aaaaaa',
                     font=('Segoe UI', 9), width=14, anchor='w').pack(side=tk.LEFT)

        kw_row = tk.Frame(editor, bg='#252525')
        kw_row.pack(fill=tk.X, pady=3)
        lbl(kw_row, 0, t("alerts_keywords"))
        self._alert_kw_var = tk.StringVar()
        tk.Entry(kw_row, textvariable=self._alert_kw_var, bg='#0d0d0d', fg='white',
                 insertbackground='white', relief='flat', font=('Consolas', 10)).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(kw_row, text=t("alerts_keywords_hint"), bg='#252525', fg='#666666',
                 font=('Segoe UI', 8)).pack(side=tk.LEFT)

        url_row = tk.Frame(editor, bg='#252525')
        url_row.pack(fill=tk.X, pady=3)
        lbl(url_row, 0, t("alerts_image"))
        self._alert_url_var = tk.StringVar()
        tk.Entry(url_row, textvariable=self._alert_url_var, bg='#0d0d0d', fg='white',
                 insertbackground='white', relief='flat', font=('Consolas', 10)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        tk.Button(url_row, text=t("alerts_browse"), command=self._browse_alert_image,
                  bg='#3a3a3a', fg='white', font=('Segoe UI', 9),
                  relief='flat', padx=10, pady=3, cursor='hand2').pack(side=tk.LEFT)

        meta_row = tk.Frame(editor, bg='#252525')
        meta_row.pack(fill=tk.X, pady=3)
        lbl(meta_row, 0, t("alerts_label"))
        self._alert_label_var = tk.StringVar(value="🔥")
        tk.Entry(meta_row, textvariable=self._alert_label_var, width=12,
                 bg='#0d0d0d', fg='white', insertbackground='white',
                 relief='flat', font=('Consolas', 10)).pack(side=tk.LEFT, padx=(0, 20))
        tk.Label(meta_row, text=t("alerts_duration"), bg='#252525', fg='#aaaaaa',
                 font=('Segoe UI', 9)).pack(side=tk.LEFT)
        self._alert_dur_var = tk.StringVar(value="4000")
        tk.Entry(meta_row, textvariable=self._alert_dur_var, width=7,
                 bg='#0d0d0d', fg='white', insertbackground='white',
                 relief='flat', font=('Consolas', 10)).pack(side=tk.LEFT)

        btn_row = tk.Frame(editor, bg='#252525')
        btn_row.pack(fill=tk.X, pady=(10, 0))
        tk.Button(btn_row, text=t("alerts_add"), command=self._alert_add_or_update,
                  bg='#2d5a27', fg='white', font=('Segoe UI', 10, 'bold'),
                  relief='flat', padx=14, pady=7, cursor='hand2').pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_row, text=t("alerts_delete"), command=self._alert_delete,
                  bg='#6a1a1a', fg='white', font=('Segoe UI', 10),
                  relief='flat', padx=14, pady=7, cursor='hand2').pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_row, text=t("alerts_test"), command=self._alert_test,
                  bg='#1a3a6a', fg='white', font=('Segoe UI', 10),
                  relief='flat', padx=14, pady=7, cursor='hand2').pack(side=tk.LEFT)

        self._refresh_alerts_list()

    def _refresh_alerts_list(self):
        if not hasattr(self, '_alerts_listbox'):
            return
        self._alerts_listbox.delete(0, tk.END)
        for alert in _alerts_config.get('alerts', []):
            kws  = ', '.join(alert.get('keywords', []))
            lbl  = alert.get('label', '')
            dur  = alert.get('duration', 4000)
            self._alerts_listbox.insert(tk.END, f"{lbl}  [{kws}]  {dur}ms")

    def _on_alert_select(self, event=None):
        sel = self._alerts_listbox.curselection()
        if not sel:
            return
        idx   = sel[0]
        alert = _alerts_config.get('alerts', [])[idx]
        self._alert_kw_var.set(', '.join(alert.get('keywords', [])))
        self._alert_url_var.set(alert.get('image_url', ''))
        self._alert_label_var.set(alert.get('label', '🔥'))
        self._alert_dur_var.set(str(alert.get('duration', 4000)))

    def _alert_add_or_update(self):
        kws_raw = self._alert_kw_var.get().strip()
        url     = self._alert_url_var.get().strip()
        label   = self._alert_label_var.get().strip() or '🔥'
        try:
            duration = int(self._alert_dur_var.get().strip())
            duration = max(500, min(30000, duration))
        except:
            duration = 4000

        if not kws_raw:
            return

        keywords = [k.strip() for k in kws_raw.split(',') if k.strip()]
        new_alert = {'keywords': keywords, 'image_url': url, 'label': label, 'duration': duration}

        global _alerts_config
        cfg = _alerts_config.copy()
        alerts = cfg.get('alerts', [])
        
        sel = self._alerts_listbox.curselection()
        if sel:
            alerts[sel[0]] = new_alert
        else:
            alerts.append(new_alert)

        cfg['alerts'] = alerts
        save_alerts_config(cfg)
        self._refresh_alerts_list()
        
        self._alert_kw_var.set("")
        self._alert_url_var.set("")
        log_to_gui(t("alerts_saved", keywords=', '.join(keywords)), "OK")

    def _alert_delete(self):
        sel = self._alerts_listbox.curselection()
        if not sel:
            return
        
        global _alerts_config
        cfg = _alerts_config.copy()
        alerts = cfg.get('alerts', [])
        
        idx = sel[0]
        del alerts[idx]
        
        cfg['alerts'] = alerts
        save_alerts_config(cfg)
        self._refresh_alerts_list()
        log_to_gui(t("alerts_deleted"), "INFO")

    def _alert_test(self):
        url   = self._alert_url_var.get().strip()
        label = self._alert_label_var.get().strip() or '🔥'
        try:
            duration = int(self._alert_dur_var.get().strip())
        except Exception:
            duration = 4000
        test_alert = {'image_url': url, 'label': label, 'duration': duration, 'keywords': []}
        self.overlay.trigger_alert(test_alert)
        log_to_gui(t("alerts_test_fired", label=label), "INFO")

    def _save_alerts_global(self):
        cfg = _alerts_config.copy()
        cfg['enabled'] = self._alerts_enabled_var.get()
        try:
            cfg['cooldown'] = max(0, int(self._cooldown_var.get()))
        except Exception:
            pass
        save_alerts_config(cfg)

    def _browse_alert_image(self):
        filepath = filedialog.askopenfilename(
            title="Select alert image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                ("GIF animations", "*.gif"),
                ("All files", "*.*"),
            ]
        )
        if filepath:
            self._alert_url_var.set(filepath)


class TrayManager:
    def __init__(self, overlay: GhostOverlay, control_panel: ControlPanel):
        self.overlay       = overlay
        self.control_panel = control_panel
        self.icon          = None

    def _create_icon_image(self):
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, size-4, size-4], fill='#9146FF', outline='#6441A5', width=2)
        try:
            fnt = ImageFont.truetype("arial.ttf", 28)
            fnt_small = ImageFont.truetype("arial.ttf", 14)
        except Exception:
            fnt = ImageFont.load_default()
            fnt_small = ImageFont.load_default()
        
        draw.text((size//2, size//2 - 4), "T", fill='white', font=fnt, anchor='mm')
        
        draw.text((size//2, size//2 + 16), APP_VERSION, fill='#FFD700', 
                  font=fnt_small, anchor='mm')
        
        return img

    def _open_panel(self, icon=None, item=None):
        self.overlay.root.after_idle(self.control_panel.open)

    def _quit(self, icon=None, item=None):
        try:
            if (self.control_panel.window and 
                self.control_panel.window.winfo_exists() and 
                self.control_panel.channel_entry):
                channel = self.control_panel.channel_entry.get().strip()
                if channel:
                    state = load_app_state()
                    state['last_channel'] = channel
                    save_app_state(state)
        except Exception as e:
            pass
        
        should_stop.set()
        chat_command.put("STOP")
        if self.icon:
            self.icon.stop()
        self.overlay.close()

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(t("tray_open"), self._open_panel, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"ℹ️ {t('about_title')}", self._show_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"{APP_NAME} v{APP_VERSION}", None, enabled=False),
            pystray.MenuItem(t("tray_quit"), self._quit),
        )

    def _show_about(self, icon=None, item=None):
        if self.overlay.root:
            self.overlay.root.after_idle(self.control_panel._show_about)

    def rebuild_menu(self):
        if self.icon:
            try:
                self.icon.menu = self._build_menu()
                self.icon.update_menu()
            except Exception:
                pass

    def start(self):
        if not TRAY_OK or not PIL_OK:
            return
        self.icon = pystray.Icon(
            "TwitchOverlay", self._create_icon_image(),
            "Twitch Ghost Overlay", self._build_menu()
        )
        threading.Thread(target=self._run_icon, daemon=True).start()

    def _run_icon(self):
        if self.icon:
            self.icon.run()


def log_to_gui(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_queue.put(('system', timestamp, level, message))
    if system_log_file:
        try:
            system_log_file.write(f"[{timestamp}] [{level}] {message}\n")
            system_log_file.flush()
        except Exception:
            pass


def log_chat_to_gui(username, message, badges):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_queue.put(('chat', timestamp, username, badges, message))


def hash_user(username):
    return hashlib.sha256((HASH_SALT + username.lower()).encode()).hexdigest()[:12]


def get_color_for_user(username):
    if username not in user_colors:
        idx = sum(ord(c) for c in username) % len(DEFAULT_COLORS)
        user_colors[username] = DEFAULT_COLORS[idx]
    return user_colors[username]


def save_stats_snapshot():
    if not twitch_config["log_stats"] or twitch_config["test_mode"]:
        return
    try:
        channel  = connection_state.get('current_channel') or 'unknown'
        os.makedirs(LOGS_DIR, exist_ok=True)
        today    = datetime.now().strftime("%Y-%m-%d")
        filename = os.path.join(LOGS_DIR, f"{channel}_{today}_stats.json")
        duration = time.time() - stats["session_start"]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "channel":            channel,
                "session_start":      stats["session_start_iso"],
                "session_end":        datetime.now().isoformat(),
                "duration_seconds":   int(duration),
                "total_messages":     stats["total_messages"],
                "unique_users_count": len(stats["unique_users_hashed"]),
                "errors":             stats["errors"],
                "reconnects":         stats["reconnects"],
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def parse_emotes_tag(emotes_str, message_text):
    if not emotes_str:
        return []
    
    result = []
    try:
        for emote_block in emotes_str.split("/"):
            if ":" not in emote_block:
                continue
            emote_id, positions = emote_block.split(":", 1)
            for pos in positions.split(","):
                if "-" not in pos:
                    continue
                start_s, end_s = pos.split("-", 1)
                start = int(start_s)
                end = int(end_s) + 1
                result.append((start, end, emote_id))
    except Exception:
        return []
    
    result.sort(key=lambda x: x[0])
    return result


def get_emote_path(emote_id):
    os.makedirs(EMOTE_CACHE_DIR, exist_ok=True)
    return os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.png")


def download_emote(emote_id):
    if not emote_id or not re.search(r'^[a-zA-Z0-9_]+$', str(emote_id)):
        return None

    gif_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.gif")
    png_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.png")

    cache_abs = os.path.abspath(EMOTE_CACHE_DIR)
    for path in (gif_path, png_path):
        if not os.path.abspath(path).startswith(cache_abs):
            log_to_gui(f"[EMOTE] REJECT path traversal: {path}", "ERROR")
            return None

    os.makedirs(EMOTE_CACHE_DIR, exist_ok=True)

    if os.path.exists(gif_path):
        log_to_gui(f"[EMOTE] Already cached (gif): {emote_id}", "OK")
        return gif_path
    if os.path.exists(png_path):
        log_to_gui(f"[EMOTE] Already cached (png): {emote_id}", "OK")
        return png_path

    TRUSTED_CDN = "static-cdn.jtvnw.net"
    animated_url = f"https://{TRUSTED_CDN}/emoticons/v2/{emote_id}/animated/dark/1.0"
    static_url   = f"https://{TRUSTED_CDN}/emoticons/v2/{emote_id}/default/dark/1.0"

    for url, save_path in [(animated_url, gif_path), (static_url, png_path)]:
        try:
            log_to_gui(f"[EMOTE] Downloading: {url}", "INFO")
            req = urllib.request.Request(url, headers={'User-Agent': 'TwitchOverlay/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                content_type = resp.headers.get('Content-Type', '')
                log_to_gui(f"[EMOTE] Content-Type: {content_type}", "INFO")
                if not any(ct in content_type for ct in
                           ('image/gif', 'image/png', 'image/webp', 'image/jpeg')):
                    log_to_gui(f"[EMOTE] REJECT bad content-type: {content_type}", "WARN")
                    continue
                data = resp.read(5 * 1024 * 1024)
            if len(data) > 100:
                with open(save_path, 'wb') as f:
                    f.write(data)
                log_to_gui(f"[EMOTE] Saved {emote_id} → {save_path} ({len(data)} bytes)", "OK")
                return save_path
            else:
                log_to_gui(f"[EMOTE] Too small: {len(data)} bytes", "WARN")
        except Exception as e:
            log_to_gui(f"[EMOTE] Download error {url}: {e}", "WARN")
            continue

    log_to_gui(f"[EMOTE] FAILED to download: {emote_id}", "ERROR")
    return None


def get_emote_photo(emote_id, root):
    if emote_id in _emote_images:
        return _emote_images[emote_id]

    if not PIL_OK:
        return None

    gif_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.gif")
    png_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.png")

    existing_path = None
    if os.path.exists(gif_path):
        existing_path = gif_path
    elif os.path.exists(png_path):
        existing_path = png_path

    if existing_path:
        return _load_emote_from_file(emote_id, existing_path, root)
    else:
        with _emote_pending_lock:
            if emote_id not in _emote_pending:
                _emote_pending.add(emote_id)
                threading.Thread(
                    target=_download_and_cache_emote,
                    args=(emote_id,),        # без root!
                    daemon=True,
                    name=f"EmoteDL-{emote_id}"
                ).start()
        return None


def _load_emote_from_file(emote_id, path, root):
    try:
        from PIL import ImageTk
        log_to_gui(f"[EMOTE] Loading from file: {path}", "INFO")

        pil_img = Image.open(path)
        is_animated = getattr(pil_img, 'is_animated', False)
        n_frames = getattr(pil_img, 'n_frames', 1)
        log_to_gui(f"[EMOTE] {emote_id}: animated={is_animated}, frames={n_frames}", "INFO")

        if is_animated and n_frames > 1:
            frames = []
            delays = []
            for i in range(n_frames):
                pil_img.seek(i)
                frame = pil_img.copy().convert('RGBA')
                frame = frame.resize((22, 22), Image.LANCZOS)
                photo = ImageTk.PhotoImage(frame, master=root)
                frames.append(photo)
                delay = pil_img.info.get('duration', 100)
                if delay < 20:
                    delay = 100
                delays.append(delay)

            _emote_frames[emote_id] = frames
            _emote_delays[emote_id] = delays
            _emote_is_animated[emote_id] = True
            _emote_images[emote_id] = frames[0]
            log_to_gui(f"[EMOTE] Loaded animated {emote_id}: {n_frames} frames", "OK")
            return frames[0]
        else:
            frame = pil_img.convert('RGBA').resize((22, 22), Image.LANCZOS)
            photo = ImageTk.PhotoImage(frame, master=root)
            _emote_images[emote_id] = photo
            _emote_is_animated[emote_id] = False
            log_to_gui(f"[EMOTE] Loaded static {emote_id}", "OK")
            return photo

    except Exception as e:
        log_to_gui(f"[EMOTE] Load error {emote_id}: {e}", "ERROR")
        _emote_images[emote_id] = None
        return None


def _download_and_cache_emote(emote_id):
    try:
        path = download_emote(emote_id)
    finally:
        with _emote_pending_lock:
            _emote_pending.discard(emote_id)


def split_message_with_emotes(message, emotes_list):
    if not emotes_list:
        return [('text', message)]
    
    parts = []
    last_end = 0
    
    for start, end, emote_id in emotes_list:
        if start > last_end:
            text_chunk = message[last_end:start]
            if text_chunk:
                parts.append(('text', text_chunk))
        
        emote_name = message[start:end] if end <= len(message) else ""
        parts.append(('emote', emote_id, emote_name))
        last_end = end
    
    if last_end < len(message):
        remaining = message[last_end:]
        if remaining:
            parts.append(('text', remaining))
    
    return parts if parts else [('text', message)]


def parse_irc_message(line):
    if not line:
        return None, None, None, {}
    tags = {}
    rest = line
    if line.startswith("@"):
        space_idx = line.find(" ")
        if space_idx == -1:
            return None, None, None, {}
        for tag in line[1:space_idx].split(";"):
            if "=" in tag:
                k, v = tag.split("=", 1)
                tags[k] = v
        rest = line[space_idx + 1:]
    match = re.match(r":(\w+)!\w+@\S+\s+PRIVMSG\s+#\S+\s+:(.*)", rest)
    if not match:
        return None, None, None, {}
    username     = match.group(1)
    message      = match.group(2).strip()
    display_name = tags.get("display-name") or username
    color        = tags.get("color") or get_color_for_user(username)
    if not color:
        color = get_color_for_user(username)
    return display_name, message, color, tags


def update_stats(username, message, tags):
    if not twitch_config["log_stats"] or twitch_config["test_mode"]:
        return
    user_hash = hash_user(username)
    stats["total_messages"] += 1
    stats["unique_users_hashed"].add(user_hash)
    stats["messages_per_minute"][datetime.now().strftime("%Y-%m-%d %H:%M")] += 1
    if tags.get("mod")         == "1": stats["users_by_role"]["moderators"].add(user_hash)
    if tags.get("subscriber")  == "1": stats["users_by_role"]["subscribers"].add(user_hash)
    if tags.get("vip")         == "1": stats["users_by_role"]["vips"].add(user_hash)
    if tags.get("badges", "").startswith("broadcaster"):
        stats["users_by_role"]["broadcaster"].add(user_hash)


def setup_irc_connection(channel):
    log_to_gui(t("log_connecting", host=TWITCH_HOST, port=TWITCH_PORT), "INFO")
    sock = socket.socket()
    sock.settimeout(30)
    sock.connect((TWITCH_HOST, TWITCH_PORT))
    sock.settimeout(None)
    sock.send(b"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")
    sock.send(f"NICK {ANON_NICK}\r\n".encode())
    sock.send(f"JOIN #{channel}\r\n".encode())
    log_to_gui(t("log_connected", ch=channel), "OK")
    return sock


def close_sock(sock):
    if sock:
        try: sock.shutdown(socket.SHUT_RDWR)
        except Exception: pass
        try: sock.close()
        except Exception: pass


def chat_loop(overlay: GhostOverlay):
    sock            = None
    buffer          = ""
    last_reconnect  = 0
    last_stats_save = time.time()
    current_channel = None
    reconnect_count = 0

    while not should_stop.is_set():
        try:
            cmd = chat_command.get(timeout=0.5)
            if cmd == "STOP":
                break
            if cmd == "DISCONNECT":
                if sock:
                    close_sock(sock)
                    sock = None
                with connection_lock:
                    connection_state.update({
                        'connected': False, 'connecting': False,
                        'current_channel': None, 'sock': None,
                    })
                if current_channel:
                    overlay.add_system_message(
                        t("ov_disconnected", ch=current_channel), '#FFAA00')
                    log_to_gui(t("log_disconnected", ch=current_channel), "INFO")
                current_channel = None
                reconnect_count = 0
                continue
            if cmd.startswith("CONNECT:"):
                new_channel = cmd[8:]
                if sock:
                    close_sock(sock)
                    sock = None
                current_channel = new_channel
                reconnect_count = 0
                buffer          = ""
                with connection_lock:
                    connection_state.update({
                        'connecting': True, 'connected': False,
                        'current_channel': current_channel,
                        'last_activity': time.time(),
                    })
                overlay.clear()
                overlay.add_system_message(
                    t("ov_connecting", ch=current_channel), '#FFFF00')
                continue
        except queue.Empty:
            pass

        if current_channel is None:
            time.sleep(0.3)
            continue

        if sock is None:
            if reconnect_count >= twitch_config["max_reconnects"]:
                overlay.add_system_message(t("ov_too_many_recon"), '#FF4444')
                log_to_gui(t("log_max_reconnects"), "ERROR")
                with connection_lock:
                    connection_state['connecting'] = False
                    connection_state['connected']  = False
                current_channel = None
                continue
            wait = max(0, 3 - (time.time() - last_reconnect))
            if wait > 0:
                time.sleep(wait)
            try:
                sock = setup_irc_connection(current_channel)
                last_reconnect  = time.time()
                reconnect_count += 1
                stats["reconnects"] += 1
                buffer = ""
                with connection_lock:
                    connection_state.update({
                        'connecting': False, 'connected': True,
                        'sock': sock, 'last_activity': time.time(),
                    })
                overlay.add_system_message(
                    t("ov_connected", ch=current_channel), '#00FF00')
            except Exception as e:
                log_to_gui(t("log_conn_failed", e=e), "ERROR")
                overlay.add_system_message(t("ov_conn_error", e=e), '#FF4444')
                last_reconnect = time.time()
                time.sleep(2)
                continue

        try:
            sock.settimeout(1)
            try:
                data = sock.recv(4096).decode("utf-8", errors="replace")
            except socket.timeout:
                continue
            finally:
                try: sock.settimeout(None)
                except Exception: pass

            if not data:
                raise ConnectionError("Server closed connection")

            buffer += data
            while "\r\n" in buffer:
                line, buffer = buffer.split("\r\n", 1)
                line = line.strip()
                if not line:
                    continue
                if line.startswith("PING"):
                    sock.send(b"PONG :tmi.twitch.tv\r\n")
                    stats["irc_pings"] += 1
                    with connection_lock:
                        connection_state['last_activity'] = time.time()
                    continue
                username, message, color, tags = parse_irc_message(line)
                if username and message:
                    username = sanitize_username(username)
                    color    = sanitize_color(color)

                    emotes_raw_str = tags.get("emotes", "")

                    if emotes_raw_str:
                        emotes_raw_str = limit_emotes(emotes_raw_str, message)

                    has_emotes = bool(emotes_raw_str)
                    if has_emotes:
                        message = sanitize_message(message, preserve_positions=True)
                    else:
                        message = sanitize_message(message, preserve_positions=False)

                    if not message or not username:
                        continue
                    # ─────────────────────────────────────────────────────

                    badges     = []
                    badge_icon = None
                    if tags.get("badges", "").startswith("broadcaster"):
                        badges.append("STREAMER"); badge_icon = "🎬"
                    elif tags.get("mod") == "1":
                        badges.append("MOD");      badge_icon = "🔧"
                    elif tags.get("vip") == "1":
                        badges.append("VIP");      badge_icon = "💎"
                    elif tags.get("subscriber") == "1":
                        badges.append("SUB");      badge_icon = "⭐"

                    update_stats(username, message, tags)
                    log_chat_to_gui(username, message, badges)

                    with connection_lock:
                        connection_state['last_activity'] = time.time()

                    if emotes_raw_str:
                        emotes_parsed = parse_emotes_tag(emotes_raw_str, message)
                        for _, _, eid in emotes_parsed:
                            safe_eid = sanitize_emote_id(eid)
                            if safe_eid and not os.path.exists(get_emote_path(safe_eid)):
                                threading.Thread(
                                    target=download_emote, args=(safe_eid,),
                                    daemon=True
                                ).start()

                    overlay.add_chat_message(username, message,
                        name_color=color,
                        msg_color='#FFFFFF', badge=badge_icon,
                        emotes_raw=emotes_raw_str)

            if time.time() - last_stats_save > 60:
                save_stats_snapshot()
                last_stats_save = time.time()

        except (ConnectionError, OSError) as e:
            log_to_gui(t("log_conn_lost", e=e), "WARN")
            if current_channel:
                overlay.add_system_message(t("ov_reconnecting"), '#FFFF00')
            close_sock(sock)
            sock = None
            with connection_lock:
                connection_state['connected']  = False
                connection_state['connecting'] = bool(current_channel)
            time.sleep(2)
        except Exception as e:
            log_to_gui(t("log_error", e=e), "ERROR")
            stats["errors"] += 1
            close_sock(sock)
            sock = None
            with connection_lock:
                connection_state['connected'] = False
            time.sleep(2)

    close_sock(sock)
    with connection_lock:
        connection_state['connected']  = False
        connection_state['connecting'] = False


def validate_channel_name(name):
    if not name:
        return False, t("err_empty")
    name = name.lower().lstrip("#").strip()
    if len(name) < 3:   return False, t("err_short")
    if len(name) > 25:  return False, t("err_long")
    if not re.match(r"^[a-z0-9_]+$", name): return False, t("err_chars")
    return True, name


def _heartbeat_loop():
    while not should_stop.is_set():
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass
        for _ in range(HEARTBEAT_INTERVAL * 10):
            if should_stop.is_set():
                break
            time.sleep(0.1)
    try:
        os.remove(HEARTBEAT_FILE)
    except Exception:
        pass


def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("channel", nargs="?", default=None)
    parser.add_argument("--help", "-h", action="store_true")
    parser.add_argument("--test", "-t", action="store_true")
    parser.add_argument("--supervisor-pid", type=int, default=None)
    return parser.parse_args()


def _watch_supervisor(supervisor_pid: int):
    while not should_stop.is_set():
        time.sleep(5)
        try:
            os.kill(supervisor_pid, 0)
        except OSError:
            log_to_gui("Supervisor gone → exiting", "WARN")
            should_stop.set()
            break


def main():
    global system_log_file

    args = parse_args()
    if args.help:
        print("Run start.pyw to launch with supervisor.")
        return
    if args.test:
        twitch_config["test_mode"] = True

    load_alerts_config()
    initial_state = load_app_state()
    set_language(initial_state.get('language', 'en'))

    overlay_cfg = load_overlay_config()
    overlay     = GhostOverlay(overlay_cfg)

    log_to_gui(t("log_started"), "OK")
    if args.supervisor_pid:
        log_to_gui(f"Supervised by PID={args.supervisor_pid} | F8 = full restart", "OK")
    else:
        log_to_gui("No supervisor. Run start.pyw for F8 restart support.", "WARN")
    log_to_gui(t("log_overlay_created"), "OK")

    control_panel          = ControlPanel(overlay)
    tray                   = TrayManager(overlay, control_panel)
    control_panel.tray_ref = tray
    tray.start()
    log_to_gui(t("log_tray_created"), "OK")

    overlay.root.after(200, control_panel.open)

    threading.Thread(target=chat_loop, args=(overlay,),
                     name="ChatLoop", daemon=True).start()
    log_to_gui(t("log_irc_ready"), "OK")

    threading.Thread(target=_heartbeat_loop,
                     name="Heartbeat", daemon=True).start()

    if args.supervisor_pid:
        threading.Thread(target=_watch_supervisor,
                         args=(args.supervisor_pid,),
                         name="SupervisorWatcher", daemon=True).start()

    if args.channel:
        ok, result = validate_channel_name(args.channel)
        if ok:
            state = load_app_state()
            state['last_channel'] = result
            save_app_state(state)
            overlay.root.after(800, lambda: chat_command.put(f"CONNECT:{result}"))

    try:
        overlay.run()
    except KeyboardInterrupt:
        pass
    finally:
        should_stop.set()
        chat_command.put("STOP")
        if not twitch_config["test_mode"]:
            save_stats_snapshot()
        if system_log_file:
            try: system_log_file.close()
            except Exception: pass
        sys.exit(0)


def run_overlay():
    global system_log_file

    args = parse_args()
    if args.test:
        twitch_config["test_mode"] = True

    load_alerts_config()
    initial_state = load_app_state()
    
    saved_lang = initial_state.get('language', 'en')
    set_language(saved_lang)
    
    if not os.path.exists(APP_STATE_FILE):
        save_app_state(DEFAULT_APP_STATE)

    overlay_cfg = load_overlay_config()
    overlay = GhostOverlay(overlay_cfg)

    log_to_gui(t("log_started"), "OK")
    log_to_gui(t("log_overlay_created"), "OK")

    control_panel = ControlPanel(overlay)
    tray = TrayManager(overlay, control_panel)
    control_panel.tray_ref = tray
    tray.start()
    log_to_gui(t("log_tray_created"), "OK")

    overlay.root.after(200, control_panel.open)

    threading.Thread(target=chat_loop, args=(overlay,), name="ChatLoop", daemon=True).start()
    log_to_gui(t("log_irc_ready"), "OK")

    if args.channel:
        ok, result = validate_channel_name(args.channel)
        if ok:
            state = load_app_state()
            state['last_channel'] = result
            save_app_state(state)
            overlay.root.after(800, lambda: chat_command.put(f"CONNECT:{result}"))

    try:
        overlay.run()
    except KeyboardInterrupt:
        pass
    finally:
        should_stop.set()
        chat_command.put("STOP")
        if not twitch_config.get("test_mode", False):
            save_stats_snapshot()
        
        try:
            if (control_panel.window and 
                control_panel.window.winfo_exists() and 
                control_panel.channel_entry):
                channel = control_panel.channel_entry.get().strip()
                if channel:
                    state = load_app_state()
                    state['last_channel'] = channel
                    save_app_state(state)
        except Exception:
            pass
            
        log_to_gui("Overlay закрыт", "INFO")


if __name__ == "__main__":
    run_overlay()