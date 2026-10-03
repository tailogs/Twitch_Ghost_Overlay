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
import traceback
import concurrent.futures
from datetime import datetime
from collections import defaultdict, OrderedDict
import tkinter as tk
from tkinter import ttk, font as tkfont, filedialog, messagebox
import ctypes
from ctypes import wintypes
import urllib.request
import io
import string
import struct
from collections import deque

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
APP_VERSION = "1.5.1"
APP_AUTHOR = "Tailogs"
APP_YEAR = "2026"
APP_DESCRIPTION = "Overlay for Twitch chat with filters and highlights"

# ==================== КОНСТАНТЫ ====================
HEARTBEAT_FILE = "heartbeat.tmp"
OVERLAY_CONFIG_FILE = "overlay_config.json"
APP_STATE_FILE = "app_state.json"
ALERTS_CONFIG_FILE = "alerts_config.json"
FILTERS_CONFIG_FILE = "filters_config.json"
EMOTE_CACHE_DIR = "emote_cache"
LOGS_DIR = "chat_logs"
CRASH_LOG_FILE = "crash_log.txt"
CRASH_LOG_OLD = "crash_log.old.txt"

MAX_EMOTE_CACHE_ENTRIES = 400
MAX_EMOTE_PIL_CACHE_ENTRIES = 200
MAX_ALERT_IMAGE_CACHE = 50
MAX_USER_COLORS = 5000
MAX_TRANSLATE_CACHE = 2000
MAX_ALERT_LAST_FIRED = 500
MAX_STATS_USERS = 50000
MAX_IRC_LINE_LEN = 64 * 1024
MAX_IRC_BUFFER = 256 * 1024
MAX_ANIMATED_FRAMES = 60
MAX_ALERT_FRAMES = 60

IRC_IDLE_TIMEOUT = 420
STABLE_RESET_SEC = 600
MAIN_THREAD_STUCK_WARN = 20.0
WATCHDOG_CHECK_EVERY = 10.0
ALERT_EMOTE_DISK_TTL = 30 * 86400
CRASH_LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_QUEUE_MAX = 20000

EMOTE_DL_WORKERS = 8
EMOTE_RETRY_MAX = 30
EMOTE_RETRY_DELAY = 300

# Популярные Twitch-боты (для автофильтра)
KNOWN_BOTS = [
    "nightbot", "streamelements", "streamlabs", "moobot", "fossabot",
    "wizebot", "sery_bot", "soundalerts", "stay_hydrated_bot",
    "commanderroot", "logviewer", "kofistreambot", "pretzelrocks",
    "creatisbot", "botrixoficial", "own3d", "tangiabot", "slanderbot",
]

_translate_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="Translate"
)

_emote_lock = threading.RLock()
_emote_images = {}
_emote_frames = {}
_emote_delays = {}
_emote_is_animated = {}
_emote_lru = OrderedDict()
_emote_pil_cache = OrderedDict()
_emote_pil_pending = set()
_emote_pil_lock = threading.RLock()
_emote_download_queue = queue.Queue()
_emote_download_queued = set()
_emote_download_inflight = set()
_emote_download_lock = threading.RLock()
_emote_download_workers_started = False

HEARTBEAT_INTERVAL = 5

_seen_message_ids = OrderedDict()
_seen_lock = threading.Lock()
MAX_SEEN_IDS = 1000

_recent_user_msgs = OrderedDict()
_recent_user_msgs_lock = threading.RLock()
_RECENT_PER_USER = 5
_RECENT_USERS_LIMIT = 2000
_RECENT_MSG_TTL = 300

_recent_chat_tail = deque(maxlen=50)
_recent_chat_tail_lock = threading.RLock()

DEFAULT_OVERLAY_CONFIG = {
    "x": 50, "y": 50, "width": 550, "height": 450,
    "opacity": 0.78, "font_size": 13, "font_family": "Consolas",
    "text_color": "#FFFFFF", "max_messages": 80,
    "bg_color": "#0a0a0a",
    "bg_enabled": True,
    "translation_color": "#44DDFF",
    "emote_size": 22,
    "show_timestamps": False,
}

DEFAULT_APP_STATE = {
    "last_channel": "",
    "language": "en",
    "show_events": True,
    "auto_translate": True,
    "censor_enabled": True,
}

DEFAULT_FILTERS_CONFIG = {
    "ignored_users": [],
    "auto_filter_bots": True,
    "highlight_keywords": [],
    "highlight_color": "#FFFF00",
    "highlight_enabled": True,
}

DEFAULT_ALERTS_CONFIG = {
    "alerts": [],
    "cooldown": 10,
    "enabled": True,
}

_alerts_config = DEFAULT_ALERTS_CONFIG.copy()
_alert_last_fired = OrderedDict()
_alert_image_cache = OrderedDict()
_alert_lock = threading.Lock()

_filters_config = DEFAULT_FILTERS_CONFIG.copy()
_filters_lock = threading.RLock()

_main_thread_heartbeat = [time.time()]

_mod_burst_lock = threading.RLock()
_mod_burst_events = deque(maxlen=20)
_BURST_WINDOW = 15.0
_BURST_THRESHOLD = 3
_BURST_COOLDOWN = 8.0
_last_burst_summary = [0.0]

_SYSTEM_STYLES = {
    'info':      ('»',  None,     None),
    'event':     ('★',  '#88AAFF', None),
    'connect':   ('✓',  '#00FF88', None),
    'warn':      ('⚠',  '#FFCC44', None),
    'error':     ('✗',  '#FF4444', None),
    'delete':    ('🗑',  '#FF7777', None),
    'ban':       ('🚫', '#FF5555', None),
    'timeout':   ('⏱',  '#FF8800', None),
    'clear':     ('🧹', '#FFAA00', None),
    'burst':     ('🌊', '#FF6600', None),
    'alert':     ('🔔', '#FFD700', None),
    'whisper':   ('💬', '#FF88CC', None),
    'raid':      ('⚔',  '#FF8800', '#1e0d00'),
    'sub':       ('⭐',  '#00FFAA', '#001e0d'),
    'giftsub':   ('🎁',  '#FFCC44', '#1e1800'),
    'bits':      ('💎',  '#9146FF', '#10001e'),
    'reward':    ('🎁',  '#FFD700', '#1e1800'),
    'highlight': ('✨',  '#FFFF44', '#1e1e00'),
    'announce':  ('📢',  '#44DDFF', '#00151e'),
    'firstmsg':  ('👋',  '#FF88CC', '#1e0015'),
}

_SYSTEM_ACCENT_STYLES = frozenset([
    'delete', 'ban', 'timeout', 'clear', 'burst',
    'event', 'connect', 'warn', 'error', 'whisper',
])

_SYSTEM_FRAMED_STYLES = frozenset([
    'raid', 'sub', 'giftsub', 'bits', 'reward', 'highlight', 'announce', 'firstmsg',
])


def _is_moderation_burst():
    now = time.time()
    with _mod_burst_lock:
        while _mod_burst_events and now - _mod_burst_events[0][0] > _BURST_WINDOW:
            _mod_burst_events.popleft()
        is_burst = len(_mod_burst_events) >= _BURST_THRESHOLD
        if now - _last_burst_summary[0] < _BURST_COOLDOWN:
            is_burst = True
    return is_burst


def _mod_burst_count():
    with _mod_burst_lock:
        now = time.time()
        while _mod_burst_events and now - _mod_burst_events[0][0] > _BURST_WINDOW:
            _mod_burst_events.popleft()
        return len(_mod_burst_events)


def _register_mod_event(login):
    with _mod_burst_lock:
        _mod_burst_events.append((time.time(), login))


def _fmt_duration(seconds_str):
    try:
        s = int(seconds_str)
    except (ValueError, TypeError):
        return str(seconds_str)
    if s < 60:
        return f"{s} сек"
    if s < 3600:
        m = s // 60
        rs = s % 60
        return f"{m} мин {rs} сек" if rs else f"{m} мин"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h} ч {m} мин" if m else f"{h} ч"


def _summarize_deleted_messages(login, msgs, max_show=3):
    if not msgs:
        return 0, []
    collapsed = []
    for mid, txt, ts in msgs:
        if collapsed and collapsed[-1][0] == txt:
            collapsed[-1][1] += 1
            collapsed[-1][2].append(mid)
        else:
            collapsed.append([txt, 1, [mid]])
    total_unique = len(collapsed)
    total_msgs = sum(c[1] for c in collapsed)
    lines = []
    shown = 0
    for txt, count, ids in collapsed[:max_show]:
        suffix = f"  ×{count}" if count > 1 else ""
        short = txt if len(txt) <= 120 else txt[:120] + '…'
        lines.append((f"{login}: {short}{suffix}", ids))
        shown += 1
    hidden_unique = total_unique - shown
    if hidden_unique > 0:
        lines.append((f"… и ещё {hidden_unique} сообщ. от {login}", []))
    return total_msgs, lines


class BoundedCache(OrderedDict):
    def __init__(self, maxsize=100, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._maxsize = maxsize
        self._lock = threading.RLock()

    def __setitem__(self, key, value):
        with self._lock:
            if key in self:
                self.move_to_end(key)
            super().__setitem__(key, value)
            while len(self) > self._maxsize:
                self.popitem(last=False)

    def __getitem__(self, key):
        with self._lock:
            value = super().__getitem__(key)
            self.move_to_end(key)
            return value

    def get_safe(self, key, default=None):
        with self._lock:
            if key in self:
                return self.__getitem__(key)
            return default

    def set_safe(self, key, value):
        with self._lock:
            self.__setitem__(key, value)

    def clear(self):
        with self._lock:
            super().clear()


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
        "tab_alerts": "  🔔  Alerts  ",
        "tab_filters": "  🎯  Filters  ",
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
        "settings_auto_translate": "Auto-translate all messages",
        "slider_x": "Position X:", "slider_y": "Position Y:",
        "slider_w": "Width:", "slider_h": "Height:",
        "slider_opacity": "Opacity:", "slider_font": "Font size:",
        "slider_max_msg": "Max messages:",
        "btn_save": "💾 Save", "btn_saved": "✓ Saved!",
        "btn_reset": "↺ Reset to defaults",
        "stats_title": "📊  Session statistics",
        "stats_channel": "Channel:", "stats_duration": "Duration:",
        "stats_messages": "Total messages:", "stats_users": "Unique users:",
        "stats_mods": "Moderators:", "stats_subs": "Subscribers:",
        "stats_vips": "VIPs:", "stats_reconnects": "Reconnects:",
        "stats_errors": "Errors:", "stats_pings": "IRC pings:",
        "tray_open": "🖥  Open program", "tray_quit": "❌  Quit",
        "err_empty": "Empty name", "err_short": "Too short",
        "err_long": "Too long", "err_chars": "Only latin letters, digits and _",
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
        "lang_en": "🇬🇧 English", "lang_ru": "🇷🇺 Russian",
        "alerts_title": "🔔  Keyword Alerts",
        "alerts_subtitle": "When a keyword appears in chat, an image pops up on the overlay.",
        "alerts_enable": "Enable alerts",
        "alerts_cooldown": "Cooldown (sec):",
        "alerts_keywords": "Keywords:", "alerts_keywords_hint": " (comma separated)",
        "alerts_image": "Image file:", "alerts_browse": "📂 Browse",
        "alerts_label": "Label:", "alerts_duration": "Duration (ms):",
        "alerts_add": "➕ Add / Update", "alerts_delete": "🗑 Delete selected",
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
        "settings_text_color": "Text color",
        "settings_bg_color": "Message background color",
        "settings_show_events": "Show events (raids, subs, gifts...)",
        "settings_censor": "Enable profanity filter",
        "settings_font_family": "Font family:",
        "settings_show_timestamps": "Show timestamps [HH:MM]",
        "filters_title": "🎯  Chat Filters",
        "filters_subtitle": "Hide unwanted users, filter bots, highlight important words.",
        "filters_bots_section": "🤖  Bot filter",
        "filters_bots_enable": "Auto-hide known Twitch bots (Nightbot, StreamElements, etc.)",
        "filters_ignored_section": "🚫  Ignored users",
        "filters_ignored_hint": "Messages from these users will not appear on the overlay.",
        "filters_ignored_placeholder": "Username (without @)",
        "filters_ignored_add": "➕ Add",
        "filters_ignored_remove": "🗑 Remove selected",
        "filters_ignored_empty": "The ignore list is empty",
        "filters_ignored_added": "User added to ignore list: {user}",
        "filters_ignored_removed": "User removed from ignore list",
        "filters_ignored_exists": "This user is already in the list",
        "filters_highlight_section": "⭐  Keyword highlighting",
        "filters_highlight_enable": "Enable highlighting",
        "filters_highlight_color": "Highlight color:",
        "filters_highlight_keywords": "Keywords (comma separated):",
        "filters_highlight_hint": "Messages containing these words will be highlighted.",
        "filters_save": "💾 Save filters",
        "filters_saved": "Filters saved",
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
        "tab_alerts": "  🔔  Алерты  ",
        "tab_filters": "  🎯  Фильтры  ",
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
        "settings_auto_translate": "Автоперевод всех сообщений",
        "slider_x": "Позиция X:", "slider_y": "Позиция Y:",
        "slider_w": "Ширина:", "slider_h": "Высота:",
        "slider_opacity": "Прозрачность:", "slider_font": "Размер шрифта:",
        "slider_max_msg": "Макс. сообщений:",
        "btn_save": "💾 Сохранить", "btn_saved": "✓ Сохранено!",
        "btn_reset": "↺ Сброс к умолчанию",
        "stats_title": "📊  Статистика сессии",
        "stats_channel": "Канал:", "stats_duration": "Длительность:",
        "stats_messages": "Сообщений всего:", "stats_users": "Уникальных юзеров:",
        "stats_mods": "Модераторов:", "stats_subs": "Подписчиков:",
        "stats_vips": "VIP:", "stats_reconnects": "Переподключений:",
        "stats_errors": "Ошибок:", "stats_pings": "IRC PING:",
        "tray_open": "🖥  Открыть программу", "tray_quit": "❌  Выход",
        "err_empty": "Имя пустое", "err_short": "Слишком короткое",
        "err_long": "Слишком длинное", "err_chars": "Только латиница, цифры и _",
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
        "lang_en": "🇬🇧 English", "lang_ru": "🇷🇺 Русский",
        "alerts_title": "🔔  Алерты по ключевым словам",
        "alerts_subtitle": "Когда ключевое слово появляется в чате, на оверлее появляется изображение.",
        "alerts_enable": "Включить алерты",
        "alerts_cooldown": "Задержка (сек):",
        "alerts_keywords": "Ключевые слова:", "alerts_keywords_hint": " (через запятую)",
        "alerts_image": "Файл изображения:", "alerts_browse": "📂 Выбрать",
        "alerts_label": "Метка:", "alerts_duration": "Длительность (мс):",
        "alerts_add": "➕ Добавить / Обновить", "alerts_delete": "🗑 Удалить выбранное",
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
        "settings_text_color": "Цвет текста",
        "settings_bg_color": "Цвет фона сообщений",
        "settings_show_events": "Показывать события (рейды, сабы, гифты...)",
        "settings_censor": "Включить цензуру мата",
        "settings_font_family": "Шрифт:",
        "settings_show_timestamps": "Показывать метки времени [ЧЧ:ММ]",
        "filters_title": "🎯  Фильтры чата",
        "filters_subtitle": "Скрывайте нежелательных юзеров, фильтруйте ботов, подсвечивайте важные слова.",
        "filters_bots_section": "🤖  Фильтр ботов",
        "filters_bots_enable": "Скрывать известных ботов Twitch (Nightbot, StreamElements и др.)",
        "filters_ignored_section": "🚫  Игнорируемые пользователи",
        "filters_ignored_hint": "Сообщения от этих пользователей не будут появляться на оверлее.",
        "filters_ignored_placeholder": "Имя пользователя (без @)",
        "filters_ignored_add": "➕ Добавить",
        "filters_ignored_remove": "🗑 Удалить выбранное",
        "filters_ignored_empty": "Список игнорируемых пуст",
        "filters_ignored_added": "Пользователь добавлен в игнор: {user}",
        "filters_ignored_removed": "Пользователь удалён из игнора",
        "filters_ignored_exists": "Этот пользователь уже в списке",
        "filters_highlight_section": "⭐  Подсветка ключевых слов",
        "filters_highlight_enable": "Включить подсветку",
        "filters_highlight_color": "Цвет подсветки:",
        "filters_highlight_keywords": "Ключевые слова (через запятую):",
        "filters_highlight_hint": "Сообщения с этими словами будут подсвечены.",
        "filters_save": "💾 Сохранить фильтры",
        "filters_saved": "Фильтры сохранены",
    },
}

_current_lang = "en"


def t(key, **kwargs):
    try:
        lang = TRANSLATIONS.get(_current_lang, TRANSLATIONS["en"])
        s = lang.get(key, TRANSLATIONS["en"].get(key, key))
        if kwargs:
            try:
                return s.format(**kwargs)
            except Exception:
                return s
        return s
    except Exception:
        return str(key)


def set_language(lang):
    global _current_lang
    try:
        if lang in TRANSLATIONS:
            _current_lang = lang
    except Exception:
        pass


def load_overlay_config():
    try:
        if os.path.exists(OVERLAY_CONFIG_FILE):
            with open(OVERLAY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                if not isinstance(cfg, dict):
                    return DEFAULT_OVERLAY_CONFIG.copy()
                for k, v in DEFAULT_OVERLAY_CONFIG.items():
                    if k not in cfg:
                        cfg[k] = v
                cfg['x'] = int(cfg.get('x', 50))
                cfg['y'] = int(cfg.get('y', 50))
                cfg['width'] = max(100, int(cfg.get('width', 550)))
                cfg['height'] = max(100, int(cfg.get('height', 450)))
                cfg['opacity'] = max(0.05, min(1.0, float(cfg.get('opacity', 0.78))))
                cfg['font_size'] = max(6, min(72, int(cfg.get('font_size', 13))))
                cfg['max_messages'] = max(10, min(500, int(cfg.get('max_messages', 80))))
                cfg['emote_size'] = max(14, min(48, int(cfg.get('emote_size', 22))))
                return cfg
    except Exception as e:
        try:
            log_to_gui(f"Config load error: {e}", "WARN")
        except Exception:
            pass
    return DEFAULT_OVERLAY_CONFIG.copy()


def save_overlay_config(cfg):
    try:
        with open(OVERLAY_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_filters_config():
    global _filters_config
    try:
        if os.path.exists(FILTERS_CONFIG_FILE):
            with open(FILTERS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = DEFAULT_FILTERS_CONFIG.copy()
                    merged.update(data)
                    _filters_config = merged
                    return _filters_config
    except Exception:
        pass
    _filters_config = DEFAULT_FILTERS_CONFIG.copy()
    return _filters_config.copy()


def save_filters_config(cfg):
    global _filters_config
    _filters_config = cfg
    try:
        with open(FILTERS_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def is_user_ignored(login: str) -> bool:
    """Проверяет, в игнор-листе ли пользователь."""
    try:
        if not login:
            return False
        login_l = login.lower().strip()
        with _filters_lock:
            ignored = _filters_config.get('ignored_users', []) or []
            for u in ignored:
                if u and u.lower().strip() == login_l:
                    return True
            # Автофильтр ботов
            if _filters_config.get('auto_filter_bots', True):
                for bot in KNOWN_BOTS:
                    if login_l == bot or login_l.endswith('bot') and bot in login_l:
                        return True
        return False
    except Exception:
        return False


def message_has_highlight(message: str) -> bool:
    """Проверяет, содержит ли сообщение ключевое слово для подсветки."""
    try:
        if not message:
            return False
        with _filters_lock:
            if not _filters_config.get('highlight_enabled', True):
                return False
            keywords = _filters_config.get('highlight_keywords', []) or []
            if not keywords:
                return False
            msg_l = message.lower()
            for kw in keywords:
                if kw and kw.lower().strip() in msg_l:
                    return True
        return False
    except Exception:
        return False


def load_app_state():
    try:
        if os.path.exists(APP_STATE_FILE):
            with open(APP_STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                if not isinstance(state, dict):
                    return DEFAULT_APP_STATE.copy()
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
ANON_NICK = "justinfan" + str(random.randint(10000, 99999))

DEFAULT_COLORS = [
    "#FF6699", "#00FFAA", "#FFAA00", "#66CCFF",
    "#FF66CC", "#AAFF66", "#FF8855", "#88AAFF",
    "#FFCC44", "#AA88FF", "#44FFCC", "#FF6644",
]

HASH_SALT = os.urandom(16).hex()

twitch_config = {
    "channel": None, "test_mode": False,
    "log_system": True, "log_stats": True, "max_reconnects": 50,
    "show_events": True,
    "auto_translate": True,
    "censor_enabled": True,
}

connection_state = {
    "connected": False, "connecting": False,
    "current_channel": None, "sock": None,
    "last_activity": time.time(),
    "got_first_roomstate": False,
}
connection_lock = threading.RLock()

chat_command = queue.Queue(maxsize=1000)
user_colors = BoundedCache(maxsize=MAX_USER_COLORS)
system_log_file = None
should_stop = threading.Event()
log_queue = queue.Queue(maxsize=LOG_QUEUE_MAX)

stats = {
    "session_start": time.time(),
    "session_start_iso": datetime.now().isoformat(),
    "channel": None,
    "total_messages": 0,
    "filtered_messages": 0,
    "unique_users_hashed": set(),
    "messages_per_minute": defaultdict(int),
    "users_by_role": {
        "moderators": set(), "subscribers": set(),
        "vips": set(), "broadcaster": set(),
    },
    "errors": 0, "reconnects": 0, "irc_pings": 0,
    "events_count": 0,
}

_translate_cache = BoundedCache(maxsize=MAX_TRANSLATE_CACHE)
_translate_lock = threading.RLock()


def load_alerts_config():
    global _alerts_config
    try:
        if os.path.exists(ALERTS_CONFIG_FILE):
            with open(ALERTS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
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


def check_message_for_alerts(message: str):
    try:
        if not _alerts_config.get('enabled', True):
            return None
        if not message:
            return None
        msg_lower = message.lower()
        cooldown = _alerts_config.get('cooldown', 10)
        now = time.time()
        for alert in _alerts_config.get('alerts', []):
            if not isinstance(alert, dict):
                continue
            for kw in alert.get('keywords', []):
                if not kw:
                    continue
                kw_l = kw.lower()
                if kw_l in msg_lower:
                    last = _alert_last_fired.get(kw_l, 0)
                    if now - last >= cooldown:
                        with _alert_lock:
                            _alert_last_fired[kw_l] = now
                            while len(_alert_last_fired) > MAX_ALERT_LAST_FIRED:
                                _alert_last_fired.popitem(last=False)
                        return alert
    except Exception:
        pass
    return None


def fetch_alert_image(url: str):
    if not url:
        return None
    try:
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
            while len(_alert_image_cache) > MAX_ALERT_IMAGE_CACHE:
                _alert_image_cache.popitem(last=False)
        return data
    except Exception:
        return None


def _is_mostly_english(text: str) -> bool:
    try:
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
        cyrillic_chars = sum(1 for c in text if '\u0400' <= c <= '\u04FF' or c in 'ёЁ')
        total_alpha = latin_chars + cyrillic_chars
        if total_alpha == 0:
            return False
        return (latin_chars / total_alpha) > 0.75 and latin_chars >= 3
    except Exception:
        return False


def _google_translate_free(text, dest='ru'):
    try:
        if not text or len(text) > 300:
            return None
        urls = []
        def _url_replacer(match):
            urls.append(match.group(0))
            return f" [URL_{len(urls)-1}] "
        url_pattern = re.compile(
            r'(?i)\b(?:https?://|ftp://|www\.)[^\s]+'
            r'|(?i)\b[a-z0-9.-]+\.(?:com|ru|net|org|io|gg|tv|me|co|uk|de|fr|jp|cn|xyz|site|online|club|info|biz|live|stream|watch|bit\.ly|t\.co|goo\.gl|tinyurl)(?:/[^\s]*)?'
        )
        text_with_placeholders = url_pattern.sub(_url_replacer, text)
        safe_text = re.sub(r'[^\w\s\.,!?;:\'"()\[\]{}\-–—_№]', ' ', text_with_placeholders, flags=re.UNICODE)
        safe_text = safe_text[:300].strip()
        if not safe_text:
            return None
        import urllib.parse
        encoded = urllib.parse.quote(safe_text)
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
        for i, orig_url in enumerate(urls):
            result = re.sub(r'\[\s*URL\s*_\s*' + str(i) + r'\s*\]', orig_url, result)
        result = remove_forbidden_chars(result)
        result = re.sub(r'[ \t]{2,}', ' ', result).strip()
        return result if result else None
    except Exception:
        return None


def translate_if_needed(text: str):
    try:
        if not text or len(text) < 4:
            return text, None
        if text.lstrip().startswith('!'):
            return text, None
        if _MENTION_PATTERN.search(text):
            return text, None
        if _count_words(text) < 2:
            return text, None
        cache_key = text.lower().strip()
        cached = _translate_cache.get_safe(cache_key)
        if cached is not None:
            return text, cached
        translated = _google_translate_free(text, dest=_current_lang)
        if translated and translated.lower().strip() != text.lower().strip():
            _translate_cache.set_safe(cache_key, translated)
            return text, translated
        return text, None
    except Exception:
        return text, None


def translate_async(text, callback):
    def _do():
        try:
            original, translated = translate_if_needed(text)
            if callback:
                try:
                    callback(original, translated)
                except Exception:
                    pass
        except Exception:
            pass
    try:
        _translate_pool.submit(_do)
    except Exception:
        pass


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


def process_chat_commands(message):
    try:
        msg_lower = message.lower().strip()
        if '!8ball' in msg_lower:
            answer = random.choice(
                COMMAND_8BALL_ANSWERS_RU if _current_lang == 'ru' else COMMAND_8BALL_ANSWERS_EN
            )
            return message, f"🎱 {answer}"
        match = re.search(r'!roll(?:\s+(\d+))?', msg_lower)
        if match:
            try:
                max_val = int(match.group(1)) if match.group(1) else 100
                max_val = min(max_val, 1000000)
                result = random.randint(1, max(1, max_val))
                return message, f"🎲 {result}/{max_val}"
            except Exception:
                return message, f"🎲 {random.randint(1, 100)}/100"
        if '!coin' in msg_lower or '!flip' in msg_lower:
            result = random.choice(
                ["Орёл 🦅", "Решка 👑"] if _current_lang == 'ru' else ["Heads 🦅", "Tails 👑"]
            )
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
                return message, f"👉 {random.choice(options)}"
        match = re.search(r'!rate\s+(.+)', message, re.IGNORECASE)
        if match:
            thing = match.group(1).strip()
            if thing:
                score = int(hashlib.md5(thing.lower().encode()).hexdigest()[:8], 16) % 101
                bar_filled = score // 10
                bar = '█' * bar_filled + '░' * (10 - bar_filled)
                return message, f"📊 {thing}: {score}/100 [{bar}]"
        match = re.search(r'!hug\s+@?(\S+)', message, re.IGNORECASE)
        if match:
            target = match.group(1)
            txt = f"🤗 обнимает {target}!" if _current_lang == 'ru' else f"🤗 hugs {target}!"
            return message, txt
        match = re.search(r'!love\s+@?(\S+)', message, re.IGNORECASE)
        if match:
            target = match.group(1)
            score = int(hashlib.md5(target.lower().encode()).hexdigest()[:8], 16) % 101
            return message, f"💕 {target}: {score}% love"
        return message, None
    except Exception:
        return message, None


_RU_PROFANITY_ROOTS = [
    r'[хx][уy][ёеeийяю]', r'[хx][уy][йяию]', r'[пp][иieё][зz3][дd]',
    r'[бb6][лl][яыаеёию][дdтt]', r'[бb6][лl][яь]', r'[еe][бb6][аaуыоёлнт]',
    r'[ёе][бb6](?:[аaуыоёлнтиь])', r'[сsc][уy][чкк][аоиьея]', r'[сsc][рr][аa][нт]',
    r'[мm][уy][дd][аоиьея]', r'[дd][еe][рr][ьъ][мm]', r'[жж][оo][пp][аоуые]',
    r'[гg][аa][нn][дd][оo][нn]', r'[зz3][аa][лl][уy][пp]', r'[пp][иieё][дd][аa][рr]',
    r'[пp][еe][дd][иieё][кk]', r'[шш][лl][юy][хx]', r'[шш][аa][лl][аa][вв]',
    r'[дd][рr][оo][чч]', r'[тt][рr][аa][хx]', r'[нn][аa][хx][уy]',
]

_EN_PROFANITY_ROOTS = [
    r'f+[uü]+c+k+', r'f+[uü]+k+', r's+h+[i1]+t+', r'b+[i1]+t+c+h+',
    r'a+s+s+h+[o0]+l+e+', r'c+[uü]+n+t+', r'd+[i1]+c+k+', r'c+[o0]+c+k+',
    r'p+[uü]+s+s+[yie]+', r'w+h+[o0]+r+e+', r'n+[i1]+g+g+', r'f+a+g+',
    r'd+a+m+n+', r'b+[o0]+l+l+[o0]+c+k+', r'w+a+n+k+', r't+w+a+t+', r'p+r+[i1]+c+k+',
]

_profanity_pattern = None
_profanity_lock = threading.RLock()

_MAX_MSG_LEN = 500
_MAX_USERNAME_LEN = 25
_MAX_EMOTES_COUNT = 50
_MAX_WORD_LEN = 60
_MAX_REPEAT_RUN = 8

_DANGEROUS_UNICODE_RANGES = [
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2066, 0x2069),
    (0xFFF0, 0xFFFF), (0xE0000, 0xE007F), (0xFE00, 0xFE0F),
]

_FORBIDDEN_CHARS = frozenset([
    '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
    '\x08', '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12',
    '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a',
    '\x1b', '\x1c', '\x1d', '\x1e', '\x1f', '\x7f',
    '\u200b', '\u200c', '\u200d', '\u200e', '\u200f',
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
    '\u2066', '\u2067', '\u2068', '\u2069',
    '\ufeff', '\u034f', '\u00ad',
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
_MENTION_PATTERN = re.compile(r'@[A-Za-z0-9_]{1,25}(?![A-Za-z0-9_])', re.UNICODE)
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)


def _count_words(text: str) -> int:
    try:
        if not text:
            return 0
        return len(_WORD_RE.findall(text))
    except Exception:
        return 0


def _is_dangerous_codepoint(cp: int) -> bool:
    for start, end in _DANGEROUS_UNICODE_RANGES:
        if start <= cp <= end:
            return True
    return False


def sanitize_username(username: str) -> str:
    try:
        if not username or not isinstance(username, str):
            return "unknown"
        clean = re.sub(r'[^a-zA-Z0-9_]', '', username)
        clean = clean[:_MAX_USERNAME_LEN]
        return clean if clean else "unknown"
    except Exception:
        return "unknown"


def sanitize_color(color: str) -> str:
    try:
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
    except Exception:
        return '#9146FF'


def mask_url(text: str) -> str:
    try:
        def _replace_url(match):
            url = match.group(0)
            domain_match = re.search(r'(?:https?://|ftp://|//)?([^/\s?#]+)', url, re.IGNORECASE)
            if domain_match:
                domain = domain_match.group(1)
                domain = re.sub(r'^www\.', '', domain)
                if len(domain) > 30:
                    domain = domain[:27] + '...'
                return f'[🔗 {domain}]'
            return '[🔗 ссылка]'
        return _URL_PATTERN.sub(_replace_url, text)
    except Exception:
        return text


def mask_ip(text: str) -> str:
    try:
        return _IP_PATTERN.sub('[IP скрыт]', text)
    except Exception:
        return text


def remove_forbidden_chars(text: str) -> str:
    try:
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
    except Exception:
        return text


def collapse_repeats(text: str) -> str:
    try:
        def _replace_repeat(match):
            char = match.group(1)
            count = len(match.group(0))
            return f'{char}×{count}'
        return _REPEAT_PATTERN.sub(_replace_repeat, text)
    except Exception:
        return text


def truncate_words(text: str) -> str:
    try:
        words = text.split(' ')
        result = []
        for word in words:
            if len(word) > _MAX_WORD_LEN:
                word = word[:_MAX_WORD_LEN] + '…'
            result.append(word)
        return ' '.join(result)
    except Exception:
        return text


def limit_emotes(emotes_raw: str, message: str) -> str:
    try:
        if not emotes_raw:
            return ""
        msg_len = len(message)
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
                    end = int(parts[1])
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
        return ""


def sanitize_message(text: str, preserve_positions: bool = False) -> str:
    try:
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
            text = re.sub(r'[ \t]{2,}', ' ', text)
            text = text.strip()
            text = mask_ip(text)
            text = collapse_repeats(text)
            text = truncate_words(text)
        if len(text) > _MAX_MSG_LEN:
            text = text[:_MAX_MSG_LEN - 1] + '…'
        return text
    except Exception:
        return ''


def sanitize_emote_id(emote_id: str):
    try:
        if not emote_id or not isinstance(emote_id, str):
            return None
        emote_id = emote_id.strip()
        if re.match(r'^[a-zA-Z0-9_]{1,64}$', emote_id):
            return emote_id
        return None
    except Exception:
        return None


def _build_profanity_pattern():
    global _profanity_pattern
    with _profanity_lock:
        try:
            all_roots = _RU_PROFANITY_ROOTS + _EN_PROFANITY_ROOTS
            combined = '|'.join(f'(?:{r})' for r in all_roots)
            _profanity_pattern = re.compile(
                r'(?<![a-zA-Zа-яА-ЯёЁ])(' + combined + r')[a-zA-Zа-яА-ЯёЁ]*',
                re.IGNORECASE | re.UNICODE
            )
        except Exception:
            _profanity_pattern = None


def censor_profanity(text):
    try:
        if _profanity_pattern is None:
            _build_profanity_pattern()
        if _profanity_pattern is None:
            return text, []
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
    except Exception:
        return text, []


def _censor_word(word):
    try:
        if len(word) <= 1:
            return word
        blur_chars = ['░', '▒', '▓', '█', '◼', '●', '◆']
        result = word[0]
        for i in range(1, len(word)):
            result += random.choice(blur_chars)
        return result
    except Exception:
        return word


def process_message_pipeline(username, message, has_emotes=False,
                             is_only_emotes=False,
                             is_reply=False, reply_to=""):
    try:
        if has_emotes or not twitch_config.get('censor_enabled', True):
            censored_msg = message
            censored_ranges = []
        else:
            censored_msg, censored_ranges = censor_profanity(message)
        cmd_msg, command_response = process_chat_commands(censored_msg)
        stripped = cmd_msg.strip()
        needs_translation = (
            twitch_config.get('auto_translate', True)
            and len(stripped) >= 2
            and not stripped.startswith('!')
            and not stripped.startswith('/')
            and not _MENTION_PATTERN.search(stripped)
            and _count_words(stripped) >= 2
            and not is_reply
            and not reply_to
            and not is_only_emotes
        )
        return {
            'message': cmd_msg,
            'command_response': command_response,
            'censored_ranges': censored_ranges,
            'needs_translation': needs_translation,
        }
    except Exception:
        return {
            'message': message,
            'command_response': None,
            'censored_ranges': [],
            'needs_translation': False,
        }


def parse_irc_line(line: str) -> dict:
    result = {'type': 'other', 'tags': {}, 'prefix': '', 'command': '',
              'params': [], 'trailing': '', 'raw': line}
    try:
        if not line:
            return result
        if len(line) > MAX_IRC_LINE_LEN:
            line = line[:MAX_IRC_LINE_LEN]
            result['raw'] = line
        tags = {}
        rest = line
        if rest.startswith('@'):
            space = rest.find(' ')
            if space == -1:
                return result
            for tag in rest[1:space].split(';'):
                if '=' in tag:
                    k, v = tag.split('=', 1)
                    tags[k] = v
                elif tag:
                    tags[tag] = ''
            rest = rest[space + 1:]
        prefix = ''
        if rest.startswith(':'):
            space = rest.find(' ')
            if space == -1:
                return result
            prefix = rest[1:space]
            rest = rest[space + 1:]
        parts = rest.split(' ', 1)
        command = parts[0].upper() if parts else ''
        params_raw = parts[1] if len(parts) > 1 else ''
        trailing = ''
        if ' :' in params_raw:
            params_part, trailing = params_raw.split(' :', 1)
            params = params_part.split() if params_part else []
        elif params_raw.startswith(':'):
            params = []
            trailing = params_raw[1:]
        else:
            params = params_raw.split() if params_raw else []
        result['tags'] = tags
        result['prefix'] = prefix
        result['command'] = command
        result['params'] = params
        result['trailing'] = trailing
        result['type'] = _classify_command(command)
        return result
    except Exception:
        return result


def _classify_command(command: str) -> str:
    if command.isdigit():
        return 'numeric'
    return {
        'PRIVMSG': 'privmsg', 'USERNOTICE': 'usernotice',
        'CLEARCHAT': 'clearchat', 'CLEARMSG': 'clearmsg',
        'ROOMSTATE': 'roomstate', 'NOTICE': 'notice',
        'WHISPER': 'whisper', 'JOIN': 'join', 'PART': 'part',
        'PING': 'ping', 'PONG': 'pong', 'CAP': 'cap',
        'RECONNECT': 'reconnect', 'GLOBALUSERSTATE': 'globaluserstate',
        'USERSTATE': 'userstate', 'HOSTTARGET': 'hosttarget',
    }.get(command, 'other')


def _build_usernotice_text(msg_id: str, tags: dict, trailing: str) -> str:
    try:
        disp = tags.get('display-name') or tags.get('login', '')
        if msg_id == 'raid':
            src = tags.get('msg-param-displayName', '?')
            count = tags.get('msg-param-viewerCount', '?')
            return f"Рейд: {count} зрителей от {src}!"
        if msg_id == 'unraid':
            return f"Рейд отменён: {disp}"
        if msg_id == 'sub':
            months = tags.get('msg-param-cumulative-months', '1')
            plan = tags.get('msg-param-sub-plan', '')
            return f"{disp} оформил подписку на {months} мес. ({plan})"
        if msg_id == 'resub':
            months = tags.get('msg-param-cumulative-months', '?')
            streak = tags.get('msg-param-streak-months', '0')
            return f"{disp} продлил подписку ({months} мес., серия {streak})"
        if msg_id == 'subgift':
            recip = tags.get('msg-param-recipient-display-name', '?')
            return f"{disp} подарил подписку {recip}!"
        if msg_id == 'submysterygift':
            count = tags.get('msg-param-mass-gift-count', '?')
            return f"{disp} подарил {count} подписок сообществу!"
        if msg_id == 'anonsubgift':
            recip = tags.get('msg-param-recipient-display-name', '?')
            return f"Аноним подарил подписку {recip}"
        if msg_id == 'anonsubmysterygift':
            count = tags.get('msg-param-mass-gift-count', '?')
            return f"Аноним подарил {count} подписок сообществу!"
        if msg_id == 'giftpaidupgrade':
            sender = tags.get('msg-param-sender-login', '?')
            return f"{disp} апгрейд подарка от {sender}"
        if msg_id == 'primepaidupgrade':
            return f"{disp} апгрейд Prime → платная подписка"
        if msg_id == 'bitsbadgetier':
            thr = tags.get('msg-param-threshold', '?')
            return f"{disp} получил Bits-бейдж за {thr} битсов!"
        if msg_id == 'announcement':
            return trailing or "Анонс"
        if msg_id == 'viewermilestone':
            cat = tags.get('msg-param-category', '')
            val = tags.get('msg-param-value', '')
            return f"{disp} достиг вехи: {cat} = {val}"
        if msg_id == 'ritual':
            ritual = tags.get('msg-param-ritual-name', '')
            return f"{disp} выполнил ритуал: {ritual}"
        if msg_id == 'rewardgift':
            return f"{disp} получил награду за просмотр"
        if msg_id == 'communitypayforward':
            return f"{disp} оплатил подписку вперёд"
        if msg_id == 'standardpayforward':
            return f"{disp} оплатил подписку вперёд"
        if msg_id == 'charitydonation':
            return trailing or f"{disp}: благотворительный донат"
        return trailing or f"Событие: {msg_id}"
    except Exception:
        return trailing or f"Событие: {msg_id}"


def _usernotice_style(msg_id: str):
    mapping = {
        'raid':             ('⚔',  '#FF8800', 'raid'),
        'unraid':           ('🚪', '#888888', 'event'),
        'sub':              ('⭐', '#00FFAA', 'sub'),
        'resub':            ('⭐', '#00FFAA', 'sub'),
        'subgift':          ('🎁', '#FFCC44', 'giftsub'),
        'submysterygift':   ('🎁', '#FFCC44', 'giftsub'),
        'anonsubgift':      ('🎁', '#AAAAAA', 'giftsub'),
        'anonsubmysterygift': ('🎁', '#AAAAAA', 'giftsub'),
        'giftpaidupgrade':  ('⬆', '#88AAFF', 'sub'),
        'primepaidupgrade': ('⬆', '#88AAFF', 'sub'),
        'bitsbadgetier':    ('💎', '#9146FF', 'bits'),
        'announcement':     ('📢', '#44DDFF', 'announce'),
        'ritual':           ('🔮', '#AA88FF', 'event'),
        'viewermilestone':  ('🏆', '#FFD700', 'event'),
        'rewardgift':       ('🎁', '#FFCC44', 'giftsub'),
        'communitypayforward': ('💝', '#FF88CC', 'sub'),
        'standardpayforward':  ('💝', '#FF88CC', 'sub'),
        'charitydonation':  ('❤', '#FF5555', 'event'),
    }
    return mapping.get(msg_id, ('🔔', '#CCCCCC', 'event'))


def handle_usernotice(overlay, parsed: dict):
    try:
        if not twitch_config.get("show_events", True):
            return
        tags = parsed.get('tags', {})
        msg_id = tags.get('msg-id', '')
        system_msg = tags.get('system-msg', '')
        text = system_msg.replace('\\s', ' ') if system_msg else ''
        if not text:
            text = _build_usernotice_text(msg_id, tags, parsed.get('trailing', ''))
        if not text:
            return
        icon, color, style = _usernotice_style(msg_id)
        overlay.add_system_message(f"{icon} {text}", color, style=style)
        stats['events_count'] = stats.get('events_count', 0) + 1
        log_to_gui(f"[USERNOTICE] {msg_id}: {text}", "INFO")
    except Exception as e:
        log_to_gui(f"handle_usernotice error: {e}", "ERROR")


def handle_clearchat(overlay, parsed: dict):
    try:
        if not twitch_config.get("show_events", True):
            return
        tags = parsed.get('tags', {})
        login = (tags.get('login') or '').lower()
        duration = tags.get('ban-duration', '')
        reason = tags.get('ban-reason', '') or ''
        if login:
            _register_mod_event(login)
            burst = _is_moderation_burst()
            burst_count = _mod_burst_count()
            if duration:
                dur_str = _fmt_duration(duration)
                head = f"@{login} — таймаут {dur_str}"
                style = 'timeout'
                color = _SYSTEM_STYLES['timeout'][1]
            else:
                head = f"@{login} — бан"
                style = 'ban'
                color = _SYSTEM_STYLES['ban'][1]
            if reason and not burst:
                reason_short = sanitize_message(reason)
                if len(reason_short) > 120:
                    reason_short = reason_short[:120] + '…'
                if reason_short:
                    head = f"{head} · {reason_short}"
            overlay.add_system_message(head, color, style=style)
            if burst:
                with _mod_burst_lock:
                    now = time.time()
                    if now - _last_burst_summary[0] > _BURST_COOLDOWN:
                        _last_burst_summary[0] = now
                        overlay.add_system_message(
                            f"Массовая модерация · {burst_count} событий за {int(_BURST_WINDOW)}с — детали скрыты",
                            _SYSTEM_STYLES['burst'][1], style='burst')
                with _recent_user_msgs_lock:
                    _recent_user_msgs.pop(login, None)
                return
            with _recent_user_msgs_lock:
                dq = _recent_user_msgs.pop(login, None)
            if dq:
                now = time.time()
                recent = [(mid, txt, ts) for (mid, txt, ts) in dq
                          if now - ts <= _RECENT_MSG_TTL]
                if recent:
                    total, lines = _summarize_deleted_messages(login, recent, max_show=3)
                    for line, ids in lines:
                        overlay.add_system_message(line, '#FFAAAA', style='delete')
                        for mid in ids:
                            if mid:
                                try:
                                    overlay.mark_message_deleted(mid)
                                except Exception:
                                    pass
            return
        _register_mod_event('__clear__')
        burst = _is_moderation_burst()
        burst_count = _mod_burst_count()
        with _recent_chat_tail_lock:
            tail = list(_recent_chat_tail)
            _recent_chat_tail.clear()
        if burst:
            overlay.add_system_message(
                f"Чат очищен · массовая модерация ({burst_count} событий)",
                _SYSTEM_STYLES['burst'][1], style='burst')
            return
        overlay.add_system_message("Чат очищен модератором", _SYSTEM_STYLES['clear'][1], style='clear')
        now = time.time()
        by_user = OrderedDict()
        for u, txt, ts in tail:
            if now - ts > _RECENT_MSG_TTL:
                continue
            by_user.setdefault(u, []).append((None, txt, ts))
        shown_users = 0
        max_users = 5
        for u, msgs in by_user.items():
            if shown_users >= max_users:
                remaining = len(by_user) - shown_users
                if remaining > 0:
                    overlay.add_system_message(
                        f"… и ещё {remaining} участников в очищенном хвосте",
                        '#FFAAAA', style='delete')
                break
            _, lines = _summarize_deleted_messages(u, msgs, max_show=2)
            for line, _ in lines:
                overlay.add_system_message(line, '#FFAAAA', style='delete')
            shown_users += 1
    except Exception as e:
        log_to_gui(f"handle_clearchat error: {e}", "ERROR")


def handle_clearmsg(overlay, parsed: dict):
    try:
        if not twitch_config.get("show_events", True):
            return
        tags = parsed.get('tags', {})
        login = tags.get('login', '') or '?'
        target_id = tags.get('target-msg-id', '')
        deleted_text = parsed.get('trailing', '') or ''
        deleted_text = sanitize_message(deleted_text) if deleted_text else ''
        if len(deleted_text) > 200:
            deleted_text = deleted_text[:200] + '…'
        _register_mod_event(login or '__clearmsg__')
        burst = _is_moderation_burst()
        burst_count = _mod_burst_count()
        if target_id:
            try:
                overlay.mark_message_deleted(target_id)
            except Exception:
                pass
        if burst:
            with _mod_burst_lock:
                now = time.time()
                if now - _last_burst_summary[0] > _BURST_COOLDOWN:
                    _last_burst_summary[0] = now
                    overlay.add_system_message(
                        f"Массовая модерация · {burst_count} событий за {int(_BURST_WINDOW)}с — детали скрыты",
                        _SYSTEM_STYLES['burst'][1], style='burst')
            log_to_gui(f"[CLEARMSG] {login}: <burst> (id={target_id})", "INFO")
            return
        if deleted_text:
            overlay.add_system_message(
                f"@{login}: {deleted_text}",
                _SYSTEM_STYLES['delete'][1], style='delete')
        else:
            overlay.add_system_message(
                f"Сообщение от @{login} удалено",
                _SYSTEM_STYLES['delete'][1], style='delete')
        log_to_gui(f"[CLEARMSG] {login}: {deleted_text or '<пусто>'} (id={target_id})", "INFO")
    except Exception as e:
        log_to_gui(f"handle_clearmsg error: {e}", "ERROR")


def handle_roomstate(overlay, parsed: dict):
    try:
        if not twitch_config.get("show_events", True):
            return
        tags = parsed.get('tags', {})
        with connection_lock:
            if not connection_state.get('got_first_roomstate'):
                connection_state['got_first_roomstate'] = True
                return
        changes = []
        if 'slow' in tags:
            v = tags['slow']
            changes.append(f"slow={v}s" if v not in ('0', '') else "slow выкл")
        if 'subs-only' in tags:
            changes.append("subs-only вкл" if tags['subs-only'] == '1' else "subs-only выкл")
        if 'emote-only' in tags:
            changes.append("emote-only вкл" if tags['emote-only'] == '1' else "emote-only выкл")
        if 'followers-only' in tags:
            v = tags['followers-only']
            if v == '-1':
                changes.append("followers-only выкл")
            else:
                changes.append(f"followers-only {v} мин")
        if 'r9k' in tags:
            changes.append("r9k вкл" if tags['r9k'] == '1' else "r9k выкл")
        if 'unique-chat' in tags:
            changes.append("unique-chat вкл" if tags['unique-chat'] == '1' else "unique-chat выкл")
        if changes:
            overlay.add_system_message(f"Режим чата: {', '.join(changes)}", '#88AAFF', style='info')
    except Exception as e:
        log_to_gui(f"handle_roomstate error: {e}", "ERROR")


def handle_notice(overlay, parsed: dict):
    try:
        if not twitch_config.get("show_events", True):
            return
        text = parsed.get('trailing', '')
        if text and 'authentication' not in text.lower():
            overlay.add_system_message(text, '#AAAAAA', style='info')
    except Exception as e:
        log_to_gui(f"handle_notice error: {e}", "ERROR")


def handle_whisper(overlay, parsed: dict):
    try:
        prefix = parsed.get('prefix', '')
        user = prefix.split('!')[0] if '!' in prefix else prefix
        text = parsed.get('trailing', '')
        if user and text:
            overlay.add_system_message(
                f"{user}: {text}",
                _SYSTEM_STYLES['whisper'][1], style='whisper')
    except Exception as e:
        log_to_gui(f"handle_whisper error: {e}", "ERROR")


def handle_privmsg(overlay, parsed: dict):
    try:
        tags = parsed.get('tags', {})
        msg_id = tags.get('id')
        if msg_id:
            with _seen_lock:
                if msg_id in _seen_message_ids:
                    return
                _seen_message_ids[msg_id] = True
                while len(_seen_message_ids) > MAX_SEEN_IDS:
                    _seen_message_ids.popitem(last=False)
        message = parsed.get('trailing', '')
        prefix = parsed.get('prefix', '')
        username = prefix.split('!')[0] if '!' in prefix else prefix
        login = (tags.get('login') or username or '').lower()
        # === ФИЛЬТР: игнор-лист и автофильтр ботов ===
        if is_user_ignored(login):
            stats['filtered_messages'] = stats.get('filtered_messages', 0) + 1
            return
        display_name = tags.get('display-name') or username
        display_name = sanitize_username(display_name)
        color = tags.get('color') or get_color_for_user(username)
        color = sanitize_color(color)
        custom_reward_id = tags.get('custom-reward-id', '') or ''
        msg_id_meta = tags.get('msg-id', '') or ''
        is_highlight_twitch = (msg_id_meta == 'highlighted-message')
        is_reward = bool(custom_reward_id)
        reply_parent_login = tags.get('reply-parent-user-login', '') or ''
        reply_parent_msg_id = tags.get('reply-parent-msg-id', '') or ''
        is_reply = bool(reply_parent_login or reply_parent_msg_id)
        badges = []
        badge_icon = None
        badges_raw = tags.get('badges', '')
        if badges_raw.startswith('broadcaster'):
            badges.append('STREAMER')
            badge_icon = "🎬"
        elif tags.get('mod') == "1":
            badges.append("MOD")
            badge_icon = "🔧"
        elif tags.get('vip') == "1":
            badges.append("VIP")
            badge_icon = "💎"
        elif tags.get('subscriber') == "1":
            badges.append("SUB")
            badge_icon = "⭐"
        emotes_raw_str = tags.get('emotes', '')
        if emotes_raw_str:
            emotes_raw_str = limit_emotes(emotes_raw_str, message)
            message = sanitize_message(message, preserve_positions=True)
        else:
            message = sanitize_message(message, preserve_positions=False)
        if is_reward or is_highlight_twitch:
            if not message:
                message = "🎁 [награда активирована]"
            else:
                prefix_icon = "✨" if is_highlight_twitch else "🎁"
                message = f"{prefix_icon} {message}"
            if is_reward:
                overlay.add_system_message(
                    f"{display_name} активировал награду", None, style='reward')
            elif is_highlight_twitch:
                overlay.add_system_message(
                    f"{display_name} подсветил сообщение", None, style='highlight')
        if not message or not display_name:
            return
        # === ПРОВЕРКА KEYWORD HIGHLIGHT ===
        is_kw_highlight = message_has_highlight(message)
        now_ts = time.time()
        try:
            text_for_cache = message
            if len(text_for_cache) > 300:
                text_for_cache = text_for_cache[:300] + '…'
            with _recent_user_msgs_lock:
                if login:
                    if login in _recent_user_msgs:
                        dq = _recent_user_msgs[login]
                        _recent_user_msgs.move_to_end(login)
                    else:
                        dq = deque(maxlen=_RECENT_PER_USER)
                        _recent_user_msgs[login] = dq
                        while len(_recent_user_msgs) > _RECENT_USERS_LIMIT:
                            _recent_user_msgs.popitem(last=False)
                    while dq and now_ts - dq[0][2] > _RECENT_MSG_TTL:
                        dq.popleft()
                    dq.append((msg_id, text_for_cache, now_ts))
            with _recent_chat_tail_lock:
                _recent_chat_tail.append((login or display_name, text_for_cache, now_ts))
        except Exception:
            pass
        update_stats(username, message, tags)
        log_chat_to_gui(display_name, message, badges)
        with connection_lock:
            connection_state['last_activity'] = time.time()
        if emotes_raw_str:
            emotes_parsed = parse_emotes_tag(emotes_raw_str, message)
            for _, _, eid in emotes_parsed:
                safe_eid = sanitize_emote_id(eid)
                if safe_eid:
                    preload_emote_async(safe_eid)
        overlay.add_chat_message(
            display_name, message,
            name_color=color,
            msg_color=None,
            badge=badge_icon,
            emotes_raw=emotes_raw_str,
            is_reply=is_reply,
            reply_to=reply_parent_login,
            msg_id=msg_id,
            is_highlighted=is_kw_highlight,
            timestamp=now_ts,
        )
    except Exception as e:
        log_to_gui(f"handle_privmsg error: {e}", "ERROR")


class GhostOverlay:
    def __init__(self, overlay_cfg):
        self.cfg = overlay_cfg
        self.root = tk.Tk()
        self.running = True
        self.visible = True
        self.settings_mode = False
        self._message_queue = []
        self._queue_lock = threading.RLock()
        self.message_blocks = []
        self.message_index_by_id = {}
        self._rendering_items = []
        self._cached_hwnd = None
        self._anim_scheduled = False
        self.root.title("Twitch Ghost Overlay")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', self.cfg['opacity'])
        self.root.configure(bg='black')
        try:
            self.root.attributes('-transparentcolor', 'black')
        except Exception:
            pass
        self._apply_geometry()
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.text_font = tkfont.Font(
            family=self.cfg['font_family'],
            size=self.cfg['font_size'], weight='normal')
        self.name_font = tkfont.Font(
            family=self.cfg['font_family'],
            size=max(9, self.cfg['font_size'] - 2), weight='bold')
        self.special_font = tkfont.Font(
            family=self.cfg['font_family'],
            size=self.cfg['font_size'], weight='bold')
        self.padding = 12
        self.line_spacing = self.cfg['font_size'] + 8
        self.name_line_height = max(9, self.cfg['font_size'] - 2) + 8
        self.msg_block_spacing = 10
        self.name_to_msg_gap = 3
        self.settings_border_ids = []
        self._animated_items = {}
        self._animation_running = True
        self._active_alert_img_ref = None
        self._active_alert_frames_ref = None
        self._anim_job = None
        try:
            self.root.protocol("WM_DELETE_WINDOW", self.close)
        except Exception:
            pass
        self.root.after(50, self._make_click_through)
        self.root.after(200, self._make_click_through)
        self.root.after(500, self._keep_topmost_loop)
        self.root.after(33, self._process_queue)

    def _touch_main_heartbeat(self):
        _main_thread_heartbeat[0] = time.time()

    def _get_bg_color_with_alpha(self):
        return self.cfg.get('bg_color', '#0a0a0a')

    def _apply_geometry(self):
        try:
            w, h = self.cfg['width'], self.cfg['height']
            x, y = self.cfg['x'], self.cfg['y']
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._cached_hwnd = None
        except Exception:
            pass

    def _get_hwnd(self):
        try:
            if self._cached_hwnd:
                return self._cached_hwnd
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd:
                self._cached_hwnd = hwnd
            return hwnd
        except Exception:
            return 0

    def _make_click_through(self):
        if not WIN32_OK:
            return
        try:
            hwnd = self._get_hwnd()
            if not hwnd:
                return
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                ex_style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
                | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE)
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)
        except Exception as e:
            log_to_gui(f"Click-through error: {e}", "ERROR")

    def _keep_topmost_loop(self):
        if not self.running:
            return
        if WIN32_OK:
            try:
                hwnd = self._get_hwnd()
                if hwnd:
                    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                    need = (win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
                            | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE)
                    if (ex_style & need) != need:
                        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style | need)
                    win32gui.SetWindowPos(
                        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            except Exception:
                pass
        if self.running:
            try:
                self.root.after(1000, self._keep_topmost_loop)
            except Exception:
                pass

    def set_settings_mode(self, enabled):
        try:
            self.settings_mode = enabled
            self._redraw_settings_border()
        except Exception:
            pass

    def _redraw_settings_border(self):
        try:
            for item_id in self.settings_border_ids:
                try:
                    self.canvas.delete(item_id)
                except Exception:
                    pass
            self.settings_border_ids = []
            if not self.settings_mode:
                return
            w, h = self.cfg['width'], self.cfg['height']
            ids = []
            ids.append(self.canvas.create_rectangle(1, 1, w-1, h-1,
                outline='#FF3366', width=2, tags='settings_border'))
            ids.append(self.canvas.create_rectangle(4, 4, w-4, h-4,
                outline='#FFAA00', width=1, tags='settings_border'))
            cs, cc, cw = 18, '#00FFFF', 3
            for line_coords in [
                (0,0,cs,0),(0,0,0,cs),(w,0,w-cs,0),(w,0,w,cs),
                (0,h,cs,h),(0,h,0,h-cs),(w,h,w-cs,h),(w,h,w,h-cs),
            ]:
                ids.append(self.canvas.create_line(*line_coords, fill=cc, width=cw, tags='settings_border'))
            ids.append(self.canvas.create_text(
                w//2, h-14,
                text=f"  {w} × {h}  @  ({self.cfg['x']}, {self.cfg['y']})  ",
                font=('Segoe UI', 9, 'bold'), fill='#FFFF00', tags='settings_border'))
            self.settings_border_ids = ids
            for item_id in ids:
                try:
                    self.canvas.tag_raise(item_id)
                except Exception:
                    pass
        except Exception:
            pass

    def _schedule_anim_tick(self):
        if self._anim_scheduled or not self.running or not self._animation_running:
            return
        self._anim_scheduled = True
        try:
            self.root.after(33, self._animate_emotes_loop)
        except Exception:
            self._anim_scheduled = False

    def _animate_emotes_loop(self):
        if not self.running or not self._animation_running:
            self._anim_scheduled = False
            return
        try:
            if not self._animated_items:
                self._anim_scheduled = False
                return
            now = time.perf_counter() * 1000.0
            items_to_remove = []
            for item_id, info in list(self._animated_items.items()):
                try:
                    if now < info.get('next_frame_at', 0):
                        continue
                    emote_id = info['emote_id']
                    with _emote_lock:
                        frames = _emote_frames.get(emote_id)
                        delays = _emote_delays.get(emote_id)
                    if not frames or not delays:
                        items_to_remove.append(item_id)
                        continue
                    idx = (info['frame_idx'] + 1) % len(frames)
                    info['frame_idx'] = idx
                    try:
                        self.canvas.itemconfig(item_id, image=frames[idx])
                    except tk.TclError:
                        items_to_remove.append(item_id)
                        continue
                    delay = delays[idx] if idx < len(delays) else 100
                    if delay < 20:
                        delay = 100
                    info['next_frame_at'] = now + delay
                except Exception:
                    items_to_remove.append(item_id)
            for item_id in items_to_remove:
                self._animated_items.pop(item_id, None)
        except Exception:
            pass
        if self.running and self._animated_items:
            try:
                self.root.after(33, self._animate_emotes_loop)
            except Exception:
                self._anim_scheduled = False
        else:
            self._anim_scheduled = False

    def _register_animated_item(self, canvas_item_id, emote_id):
        try:
            if _emote_is_animated.get(emote_id, False):
                if len(self._animated_items) > 1500:
                    log_to_gui(f"Animated items overflow: {len(self._animated_items)}", "WARN")
                now = time.perf_counter() * 1000.0
                with _emote_lock:
                    delays = _emote_delays.get(emote_id) or [100]
                self._animated_items[canvas_item_id] = {
                    'emote_id': emote_id, 'frame_idx': 0,
                    'next_frame_at': now + (delays[0] if delays else 100),
                }
                self._schedule_anim_tick()
        except Exception:
            pass

    def _wrap_to_lines(self, text, max_width, font):
        try:
            text = re.sub(r'\s+', ' ', text).strip()
            if not text:
                return [""]
            words = text.split(' ')
            lines = []
            current_line = ""
            i = 0
            while i < len(words):
                word = words[i]
                try:
                    word_w = font.measure(word)
                except Exception:
                    word_w = len(word) * 8
                if word_w > max_width:
                    if current_line:
                        lines.append(current_line)
                        current_line = ""
                    chunk = ""
                    for ch in word:
                        test = chunk + ch
                        try:
                            tw = font.measure(test)
                        except Exception:
                            tw = len(test) * 8
                        if tw <= max_width:
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
                try:
                    tlw = font.measure(test_line)
                except Exception:
                    tlw = len(test_line) * 8
                if tlw <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
                i += 1
            if current_line:
                lines.append(current_line)
            return lines if lines else [""]
        except Exception:
            return [text]

    def _make_space(self, needed_height):
        try:
            canvas_h = self.canvas.winfo_height()
            if canvas_h < 10:
                canvas_h = self.cfg['height']
            bottom_limit = canvas_h - self.padding
            current_bottom = self._get_current_bottom()
            if current_bottom + needed_height <= bottom_limit:
                return
            deficit = (current_bottom + needed_height) - bottom_limit
            removed_height = 0
            blocks_to_remove = []
            for block in self.message_blocks:
                if removed_height >= deficit:
                    break
                blocks_to_remove.append(block)
                removed_height += block['height']
            for block in blocks_to_remove:
                mid = block.get('msg_id')
                if mid:
                    self.message_index_by_id.pop(mid, None)
                for item_id in block['items']:
                    self._animated_items.pop(item_id, None)
                    try:
                        self.canvas.delete(item_id)
                    except Exception:
                        pass
            self.message_blocks = self.message_blocks[len(blocks_to_remove):]
            if removed_height > 0:
                try:
                    self.canvas.move('msg', 0, -removed_height)
                except Exception:
                    pass
                for block in self.message_blocks:
                    block['start_y'] -= removed_height
            max_msg = self.cfg.get('max_messages', 80)
            if len(self.message_blocks) > max_msg:
                extra = self.message_blocks[:len(self.message_blocks) - max_msg]
                extra_h = sum(b['height'] for b in extra)
                for block in extra:
                    mid = block.get('msg_id')
                    if mid:
                        self.message_index_by_id.pop(mid, None)
                    for item_id in block['items']:
                        self._animated_items.pop(item_id, None)
                        try:
                            self.canvas.delete(item_id)
                        except Exception:
                            pass
                self.message_blocks = self.message_blocks[len(extra):]
                if extra_h > 0:
                    try:
                        self.canvas.move('msg', 0, -extra_h)
                    except Exception:
                        pass
                    for block in self.message_blocks:
                        block['start_y'] -= extra_h
        except Exception:
            pass

    def _get_current_bottom(self):
        try:
            if not self.message_blocks:
                return self.padding
            last = self.message_blocks[-1]
            return last['start_y'] + last['height']
        except Exception:
            return self.padding

    def _draw_outlined_text(self, x, y, text, font, color, items_collector):
        try:
            tid = self.canvas.create_text(
                x, y, text=text, font=font,
                fill=color, anchor='nw', tags='msg')
            items_collector.append(tid)
            return tid
        except Exception:
            return None

    def _draw_name_header(self, x, y, badge_icon, username, name_color, items_collector,
                          timestamp_ts=None):
        try:
            cur_x = x
            # Метка времени (опционально)
            if self.cfg.get('show_timestamps') and timestamp_ts:
                try:
                    ts_str = datetime.fromtimestamp(timestamp_ts).strftime('%H:%M')
                except Exception:
                    ts_str = ""
                if ts_str:
                    ts_id = self.canvas.create_text(
                        cur_x, y + 2, text=ts_str, font=self.name_font,
                        fill='#777777', anchor='nw', tags='msg')
                    items_collector.append(ts_id)
                    try:
                        cur_x += self.name_font.measure(ts_str) + 8
                    except Exception:
                        cur_x += 42
            if badge_icon:
                icon_id = self.canvas.create_text(
                    cur_x, y, text=badge_icon, font=self.name_font,
                    fill='#FFCC44', anchor='nw', tags='msg')
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
                fill=name_color, outline=name_color, tags='msg'))
            items_collector.append(self.canvas.create_text(
                cur_x + pad_x, y + pad_y, text=username, font=self.name_font,
                fill=text_on_pill, anchor='nw', tags='msg'))
            return pill_h, cur_x + name_w + pad_x*2
        except Exception:
            return self.name_line_height, x

    def add_chat_message(self, username, message,
                         name_color='#9146FF', msg_color=None, badge=None,
                         emotes_raw="", is_reply=False, reply_to="",
                         msg_id=None, is_highlighted=False, timestamp=None):
        try:
            if msg_color is None:
                msg_color = self.cfg.get('text_color', '#FFFFFF')
            is_only_emotes = False
            if emotes_raw:
                emotes_list = parse_emotes_tag(emotes_raw, message)
                if emotes_list:
                    msg_chars = list(message)
                    for start, end, _ in emotes_list:
                        for i in range(start, min(end, len(msg_chars))):
                            msg_chars[i] = ' '
                    if not ''.join(msg_chars).strip():
                        is_only_emotes = True
            alert = check_message_for_alerts(message)
            if alert:
                try:
                    self.root.after(0, lambda a=alert: self.trigger_alert(a))
                except Exception:
                    pass
            has_emotes = bool(emotes_raw)
            result = process_message_pipeline(
                username, message,
                has_emotes=has_emotes,
                is_only_emotes=is_only_emotes,
                is_reply=is_reply,
                reply_to=reply_to,
            )
            processed_msg = result['message']
            command_response = result['command_response']
            censored_ranges = result['censored_ranges']
            needs_translation = result['needs_translation']
            with self._queue_lock:
                if len(self._message_queue) > 500:
                    self._message_queue = self._message_queue[-400:]
                self._message_queue.append(
                    ('chat', username, processed_msg, name_color, msg_color, badge,
                     emotes_raw, command_response, censored_ranges, msg_id,
                     is_highlighted, timestamp)
                )
            if needs_translation:
                def on_translated(original, translated):
                    try:
                        if translated:
                            with self._queue_lock:
                                if len(self._message_queue) > 500:
                                    return
                                self._message_queue.append(
                                    ('translation', username, original, translated, name_color))
                    except Exception:
                        pass
                translate_async(message, on_translated)
        except Exception as e:
            log_to_gui(f"add_chat_message error: {e}", "ERROR")

    def add_system_message(self, message, color='#AAAAAA', style='info'):
        try:
            style = style or 'info'
            spec = _SYSTEM_STYLES.get(style, _SYSTEM_STYLES['info'])
            icon = spec[0] if len(spec) > 0 else '»'
            style_color = spec[1] if len(spec) > 1 else None
            tint = spec[2] if len(spec) > 2 else None
            effective_color = style_color if style_color else color
            with self._queue_lock:
                if len(self._message_queue) > 500:
                    self._message_queue = self._message_queue[-400:]
                self._message_queue.append(
                    ('system', None, message, effective_color, style, icon, tint))
        except Exception:
            pass

    def clear(self):
        try:
            with self._queue_lock:
                self._message_queue.append(('_clear',))
        except Exception:
            pass

    def mark_message_deleted(self, msg_id):
        try:
            if not msg_id:
                return
            with self._queue_lock:
                self._message_queue.append(('_delete', msg_id))
        except Exception:
            pass

    def _do_mark_deleted(self, msg_id):
        try:
            block = self.message_index_by_id.get(msg_id)
            if not block:
                return
            bg_id = block.get('bg_id')
            if bg_id:
                try:
                    self.canvas.itemconfig(bg_id, fill='#141414')
                except Exception:
                    pass
            for item_id in list(block.get('items', [])):
                if item_id == bg_id:
                    continue
                try:
                    t = self.canvas.type(item_id)
                except Exception:
                    continue
                if t == 'text':
                    try:
                        self.canvas.itemconfig(item_id, fill='#666666')
                    except Exception:
                        pass
                    try:
                        bbox = self.canvas.bbox(item_id)
                        if bbox:
                            x1, y1, x2, y2 = bbox
                            if x2 > x1 and y2 > y1:
                                line_id = self.canvas.create_line(
                                    x1, (y1 + y2) // 2, x2, (y1 + y2) // 2,
                                    fill='#FF5555', width=1, tags='msg')
                                block['items'].append(line_id)
                    except Exception:
                        pass
            self.message_index_by_id.pop(msg_id, None)
        except Exception as e:
            log_to_gui(f"_do_mark_deleted error: {e}", "ERROR")

    def trigger_alert(self, alert_cfg: dict):
        try:
            if not PIL_OK:
                return
            duration = alert_cfg.get('duration', 4000)
            label = alert_cfg.get('label', '🔥')
            url = alert_cfg.get('image_url', '')

            def _fetch_and_prepare():
                data = fetch_alert_image(url) if url else None
                pil_bundle = None
                if data:
                    try:
                        img_io = io.BytesIO(data)
                        pil_img = Image.open(img_io)
                        is_anim = getattr(pil_img, 'is_animated', False)
                        n_frames = getattr(pil_img, 'n_frames', 1)
                        max_img_w = int(self.cfg['width'] * 0.9)
                        max_img_h = int(self.cfg['height'] * 0.55)
                        ow, oh = getattr(pil_img, 'size', (100, 100))
                        scale = min(max_img_w / max(ow, 1), max_img_h / max(oh, 1), 1.0)
                        target = (max(1, int(ow * scale)), max(1, int(oh * scale)))
                        frames_pil = []
                        delays = []
                        if is_anim and n_frames > 1:
                            n = min(n_frames, MAX_ALERT_FRAMES)
                            for i in range(n):
                                try:
                                    pil_img.seek(i)
                                    f = pil_img.copy().convert('RGBA').resize(target, Image.BILINEAR)
                                    frames_pil.append(f)
                                    d = pil_img.info.get('duration', 80)
                                    if not isinstance(d, int) or d <= 0:
                                        d = 80
                                    delays.append(max(20, min(d, 500)))
                                except Exception:
                                    break
                        else:
                            f = pil_img.convert('RGBA').resize(target, Image.BILINEAR)
                            frames_pil.append(f)
                            delays.append(4000)
                        if frames_pil:
                            pil_bundle = (frames_pil, delays, target)
                    except Exception as e:
                        log_to_gui(f"Alert PIL prep error: {e}", "WARN")
                try:
                    self.root.after(0, lambda: _do_alert(pil_bundle))
                except Exception:
                    pass

            def _do_alert(pil_bundle):
                if not self.running:
                    return
                try:
                    w = self.cfg['width']
                    h = self.cfg['height']
                    pad = self.padding
                    items = []
                    alert_photo = [None]
                    anim_frames = [None]
                    anim_delays = [None]
                    img_w, img_h = 0, 0
                    if pil_bundle:
                        frames_pil, delays, target = pil_bundle
                        img_w, img_h = target
                        try:
                            frames = []
                            for f in frames_pil:
                                try:
                                    frames.append(ImageTk.PhotoImage(f, master=self.root))
                                except Exception:
                                    frames.append(None)
                            frames = [f for f in frames if f is not None]
                            if frames:
                                alert_photo[0] = frames[0]
                                if len(frames) > 1:
                                    anim_frames[0] = frames
                                    anim_delays[0] = delays[:len(frames)]
                                self._active_alert_img_ref = frames[0]
                                self._active_alert_frames_ref = (
                                    anim_frames[0] if len(frames) > 1 else None)
                        except Exception as e:
                            log_to_gui(f"Alert PhotoImage error: {e}", "WARN")
                    label_font = tkfont.Font(family='Segoe UI', size=16, weight='bold')
                    label_h = 28
                    img_block_h = img_h + 8 if img_h else 0
                    block_h = label_h + img_block_h + pad * 2
                    canvas_h = self.canvas.winfo_height()
                    if canvas_h < 10:
                        canvas_h = h
                    start_y = canvas_h
                    target_y = canvas_h - block_h - pad
                    cx = w // 2
                    bg_item = self.canvas.create_rectangle(
                        pad, start_y, w - pad, start_y + block_h,
                        fill='#111111', outline='#9146FF', width=2, tags='alert')
                    items.append(bg_item)
                    lbl_shadow = self.canvas.create_text(
                        cx + 1, start_y + label_h // 2 + 1,
                        text=label, font=label_font,
                        fill='#000000', anchor='center', tags='alert')
                    lbl_main = self.canvas.create_text(
                        cx, start_y + label_h // 2,
                        text=label, font=label_font,
                        fill='#FFD700', anchor='center', tags='alert')
                    items += [lbl_shadow, lbl_main]
                    img_item = None
                    if alert_photo[0]:
                        img_y = start_y + label_h + img_h // 2 + 4
                        img_item = self.canvas.create_image(
                            cx, img_y, image=alert_photo[0],
                            anchor='center', tags='alert')
                        items.append(img_item)
                    anim_state = {'idx': 0, 'job': None, 'running': True}
                    if anim_frames[0] and anim_delays[0] and img_item:
                        def _next_anim_frame():
                            if not self.running or not anim_state['running']:
                                return
                            try:
                                anim_state['idx'] = (anim_state['idx'] + 1) % len(anim_frames[0])
                                self.canvas.itemconfig(img_item, image=anim_frames[0][anim_state['idx']])
                                d = anim_delays[0][anim_state['idx']]
                                anim_state['job'] = self.root.after(d, _next_anim_frame)
                            except Exception:
                                return
                        anim_state['job'] = self.root.after(anim_delays[0][0], _next_anim_frame)
                    border_colors = ['#9146FF', '#FF4488', '#FF8800', '#FFFF00',
                                     '#00FF88', '#00AAFF', '#9146FF']
                    pulse_state = {'phase': 0, 'job': None}

                    def _pulse():
                        if not self.running:
                            return
                        try:
                            pulse_state['phase'] = (pulse_state['phase'] + 1) % len(border_colors)
                            self.canvas.itemconfig(bg_item, outline=border_colors[pulse_state['phase']])
                            pulse_state['job'] = self.root.after(150, _pulse)
                        except Exception:
                            return
                    pulse_state['job'] = self.root.after(150, _pulse)
                    for item in items:
                        try:
                            self.canvas.tag_raise(item)
                        except Exception:
                            pass
                    SLIDE_STEPS = 12
                    SLIDE_MS = 18
                    dy = (target_y - start_y) / SLIDE_STEPS
                    step_state = {'step': 0}

                    def _slide_in():
                        if not self.running:
                            return
                        step_state['step'] += 1
                        try:
                            self.canvas.move('alert', 0, dy)
                        except Exception:
                            return
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
                        out_step = [0]
                        out_total = SLIDE_STEPS
                        out_dy = (start_y - target_y) / out_total

                        def _slide_out():
                            if not self.running:
                                try:
                                    self.canvas.delete('alert')
                                except Exception:
                                    pass
                                return
                            out_step[0] += 1
                            try:
                                self.canvas.move('alert', 0, out_dy)
                            except Exception:
                                return
                            if out_step[0] < out_total:
                                self.root.after(SLIDE_MS, _slide_out)
                            else:
                                try:
                                    self.canvas.delete('alert')
                                except Exception:
                                    pass
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
                except Exception as e:
                    log_to_gui(f"_do_alert inner error: {e}", "ERROR")

            threading.Thread(target=_fetch_and_prepare,
                             daemon=True, name="AlertPrep").start()
        except Exception as e:
            log_to_gui(f"trigger_alert error: {e}", "ERROR")

    def _process_queue(self):
        if not self.running:
            return
        try:
            self._touch_main_heartbeat()
            with self._queue_lock:
                messages = self._message_queue[:]
                self._message_queue.clear()
            qsize = len(messages)
            if qsize > 100:
                batch_size = 16
            elif qsize > 30:
                batch_size = 8
            else:
                batch_size = 4
            batch = messages[:batch_size]
            remaining = messages[batch_size:]
            if remaining:
                with self._queue_lock:
                    self._message_queue = remaining + self._message_queue
            for msg in batch:
                self._rendering_items = []
                try:
                    if msg[0] == '_clear':
                        self._do_clear()
                    elif msg[0] == '_delete':
                        self._do_mark_deleted(msg[1])
                    elif msg[0] == 'translation':
                        self._render_translation(msg)
                    else:
                        self._render_message(msg)
                except Exception as e:
                    for iid in self._rendering_items:
                        try:
                            self._animated_items.pop(iid, None)
                            self.canvas.delete(iid)
                        except Exception:
                            pass
                    log_to_gui(f"Overlay render error: {e}", "ERROR")
                finally:
                    self._rendering_items = []
            if self.settings_mode and not self.settings_border_ids:
                self._redraw_settings_border()
        except Exception as e:
            log_to_gui(f"_process_queue error: {e}", "ERROR")
        if self.running:
            try:
                delay = 20 if remaining else 40
                self.root.after(delay, self._process_queue)
            except Exception:
                pass

    def _do_clear(self):
        try:
            self.canvas.delete('msg')
            self.message_blocks = []
            self._animated_items = {}
            self.message_index_by_id = {}
        except Exception:
            pass

    def _render_message(self, msg):
        try:
            msg_type = msg[0]
            max_width = self.cfg['width'] - (self.padding * 2)
            items = self._rendering_items
            if msg_type == 'system':
                padded = msg + (None,) * (7 - len(msg))
                _, _, message, color, style, icon, tint = padded[:7]
                style = style or 'info'
                icon = icon if icon is not None else '»'
                prefix = f"{icon} " if icon else ""
                display_text = prefix + message
                has_accent = style in _SYSTEM_ACCENT_STYLES
                has_frame = style in _SYSTEM_FRAMED_STYLES
                bar_w = 3
                left_pad = self.padding
                if has_accent:
                    left_pad += bar_w + 6
                if has_frame:
                    left_pad += 6
                text_x = left_pad
                inner_max = self.cfg['width'] - self.padding - text_x - (6 if has_frame else 0)
                sys_font = self.special_font if has_frame else self.text_font
                lines = self._wrap_to_lines(display_text, inner_max, sys_font)
                total_h = len(lines) * self.line_spacing + self.msg_block_spacing
                self._make_space(total_h)
                start_y = self._get_current_bottom()
                y = start_y
                bg_id = None
                if has_frame and tint:
                    try:
                        bg_id = self.canvas.create_rectangle(
                            self.padding, start_y,
                            self.cfg['width'] - self.padding, start_y + total_h,
                            fill=tint, outline=color, width=2, tags='msg')
                        items.append(bg_id)
                        inner_id = self.canvas.create_rectangle(
                            self.padding + 3, start_y + 3,
                            self.cfg['width'] - self.padding - 3, start_y + total_h - 3,
                            fill='', outline=color, width=1, tags='msg')
                        items.append(inner_id)
                    except Exception:
                        pass
                else:
                    if self.cfg.get('bg_enabled', True):
                        bg_id = self.canvas.create_rectangle(
                            self.padding, start_y,
                            self.cfg['width'] - self.padding, start_y + total_h,
                            fill=self._get_bg_color_with_alpha(), outline='', tags='msg')
                        items.append(bg_id)
                if has_accent and not has_frame:
                    try:
                        bar_id = self.canvas.create_rectangle(
                            self.padding, start_y + 1,
                            self.padding + bar_w, start_y + total_h - 1,
                            fill=color, outline='', tags='msg')
                        items.append(bar_id)
                    except Exception:
                        pass
                if has_frame:
                    try:
                        bar_id = self.canvas.create_rectangle(
                            self.padding + 1, start_y + 1,
                            self.padding + 5, start_y + total_h - 1,
                            fill=color, outline='', tags='msg')
                        items.append(bar_id)
                    except Exception:
                        pass
                for line in lines:
                    self._draw_outlined_text(text_x, y, line, sys_font, color, items)
                    y += self.line_spacing
                self.message_blocks.append({
                    'start_y': start_y, 'height': total_h,
                    'items': items, 'bg_id': bg_id,
                })
                return
            if msg_type == 'chat':
                padded = msg + (None,) * (12 - len(msg))
                _, username, message, name_color, msg_color, badge = padded[:6]
                emotes_raw = padded[6] or ""
                command_response = padded[7]
                censored_ranges = padded[8] or []
                msg_id = padded[9]
                is_highlighted = bool(padded[10])
                timestamp = padded[11]
                emotes_list = parse_emotes_tag(emotes_raw, message)
                if emotes_list:
                    self._render_chat_with_emotes(
                        username, message, name_color, msg_color, badge,
                        emotes_list, max_width, items,
                        command_response=command_response,
                        censored_ranges=censored_ranges,
                        msg_id=msg_id,
                        is_highlighted=is_highlighted,
                        timestamp=timestamp,
                    )
                else:
                    self._render_chat_text(
                        username, message, name_color, msg_color, badge,
                        max_width, items,
                        command_response=command_response,
                        censored_ranges=censored_ranges,
                        msg_id=msg_id,
                        is_highlighted=is_highlighted,
                        timestamp=timestamp,
                    )
                if msg_id and self.message_blocks:
                    self.message_blocks[-1]['msg_id'] = msg_id
                    self.message_index_by_id[msg_id] = self.message_blocks[-1]
        except Exception as e:
            log_to_gui(f"_render_message error: {e}", "ERROR")
            raise

    def _render_chat_text(self, username, message, name_color, msg_color,
                          badge, max_width, items,
                          command_response=None, censored_ranges=None,
                          msg_id=None, is_highlighted=False, timestamp=None):
        try:
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
            # Подсветка: рисуем рамку вокруг сообщения
            if is_highlighted:
                try:
                    with _filters_lock:
                        hl_color = _filters_config.get('highlight_color', '#FFFF00')
                    hl_id = self.canvas.create_rectangle(
                        self.padding - 2, start_y,
                        self.cfg['width'] - self.padding + 2, start_y + total_h,
                        fill='', outline=hl_color, width=2, tags='msg')
                    items.append(hl_id)
                except Exception:
                    pass
            if self.cfg.get('bg_enabled', True):
                bg_id = self.canvas.create_rectangle(
                    self.padding, start_y,
                    self.cfg['width'] - self.padding, start_y + total_h,
                    fill=self._get_bg_color_with_alpha(), outline='', tags='msg')
                items.append(bg_id)
            self._draw_name_header(self.padding, y, badge, username, name_color, items,
                                    timestamp_ts=timestamp)
            y += header_h + NAME_TO_MSG_GAP
            # Цвет текста: подсветка меняет цвет на configured
            text_render_color = msg_color
            if is_highlighted:
                try:
                    with _filters_lock:
                        text_render_color = _filters_config.get('highlight_color', '#FFFF00')
                except Exception:
                    text_render_color = '#FFFF00'
            if censored_ranges:
                self._draw_text_with_censorship(
                    self.padding + 4, y, message, text_render_color, items, censored_ranges)
                y += len(msg_lines) * self.line_spacing
            else:
                for line in msg_lines:
                    self._draw_outlined_text(
                        self.padding + 4, y, line, self.text_font, text_render_color, items)
                    y += self.line_spacing
            if cmd_lines:
                for line in cmd_lines:
                    self._draw_outlined_text(
                        self.padding + 8, y, line, self.text_font, '#FFCC44', items)
                    y += self.line_spacing
            self.message_blocks.append({
                'start_y': start_y, 'height': total_h,
                'items': items, 'bg_id': bg_id, 'msg_id': msg_id,
            })
        except Exception as e:
            log_to_gui(f"_render_chat_text error: {e}", "ERROR")
            raise

    def _draw_text_with_censorship(self, x, y, text, base_color, items, censored_ranges):
        try:
            max_width = self.cfg['width'] - (self.padding * 2)
            lines = self._wrap_to_lines(text, max_width, self.text_font)
            char_offset = 0
            for line in lines:
                line_start = text.find(line, char_offset)
                if line_start == -1:
                    line_start = char_offset
                segments = self._split_line_by_censorship(line, line_start, censored_ranges)
                cur_x = x
                for seg_text, is_censored in segments:
                    if not seg_text:
                        continue
                    color = '#666666' if is_censored else base_color
                    self._draw_outlined_text(cur_x, y, seg_text, self.text_font, color, items)
                    cur_x += self.text_font.measure(seg_text)
                char_offset = line_start + len(line)
                y += self.line_spacing
        except Exception:
            pass

    def _split_line_by_censorship(self, line, line_start_in_text, censored_ranges):
        try:
            if not censored_ranges:
                return [(line, False)]
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
        except Exception:
            return [(line, False)]

    def _render_translation(self, msg):
        try:
            _, username, original, translated, name_color = msg[:5]
            max_width = self.cfg['width'] - (self.padding * 2)
            items = self._rendering_items
            trans_text = f"↳ {translated}"
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
                    fill=self._get_bg_color_with_alpha(), outline='', tags='msg')
                items.append(bg_id)
            for line in lines:
                translation_color = self.cfg.get('translation_color', '#44DDFF')
                self._draw_outlined_text(
                    self.padding + 16, y, line, self.text_font, translation_color, items)
                y += self.line_spacing
            self.message_blocks.append({
                'start_y': start_y, 'height': total_h,
                'items': items, 'bg_id': bg_id,
            })
        except Exception as e:
            log_to_gui(f"_render_translation error: {e}", "ERROR")
            raise

    def _render_chat_with_emotes(self, username, message, name_color, msg_color,
                                  badge, emotes_list, max_width, items,
                                  command_response=None, censored_ranges=None,
                                  msg_id=None, is_highlighted=False, timestamp=None):
        try:
            parts = split_message_with_emotes(message, emotes_list)
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
                                try:
                                    current_line_w += self.text_font.measure(' ')
                                except Exception:
                                    pass
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
                        try:
                            w = self.text_font.measure(word_display)
                        except Exception:
                            w = len(word_display) * 8
                        if current_line_w + w > max_width - indent and current_line:
                            lines_content.append(current_line)
                            current_line = []
                            current_line_w = 0
                            word_display = word
                            try:
                                w = self.text_font.measure(word_display)
                            except Exception:
                                w = len(word_display) * 8
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
                        try:
                            w = self.text_font.measure(fallback)
                        except Exception:
                            w = len(fallback) * 8
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
            bg_id = None
            # Подсветка
            text_render_color = msg_color
            if is_highlighted:
                try:
                    with _filters_lock:
                        hl_color = _filters_config.get('highlight_color', '#FFFF00')
                    text_render_color = hl_color
                    hl_id = self.canvas.create_rectangle(
                        self.padding - 2, start_y,
                        self.cfg['width'] - self.padding + 2, start_y + total_h,
                        fill='', outline=hl_color, width=2, tags='msg')
                    items.append(hl_id)
                except Exception:
                    pass
            if self.cfg.get('bg_enabled', True):
                bg_id = self.canvas.create_rectangle(
                    self.padding, start_y,
                    self.cfg['width'] - self.padding, start_y + total_h,
                    fill=self._get_bg_color_with_alpha(), outline='', tags='msg')
                items.append(bg_id)
            self._draw_name_header(self.padding, y, badge, username, name_color, items,
                                    timestamp_ts=timestamp)
            y += header_h + NAME_TO_MSG_GAP
            for line_idx, line_parts in enumerate(lines_content):
                x = self.padding + indent
                line_h = line_heights[line_idx]
                try:
                    text_baseline_y = y + (line_h - self.text_font.metrics('linespace')) // 2
                except Exception:
                    text_baseline_y = y
                for lpi, lp in enumerate(line_parts):
                    if lp[0] == 'text':
                        text_str = lp[1]
                        if text_str:
                            self._draw_outlined_text(
                                x, text_baseline_y, text_str,
                                self.text_font, text_render_color, items)
                            try:
                                x += self.text_font.measure(text_str)
                            except Exception:
                                x += len(text_str) * 8
                    elif lp[0] == 'emote':
                        eid = lp[1]
                        photo = emote_photos.get(eid)
                        if photo:
                            if lpi > 0:
                                x += EMOTE_PAD_LEFT
                            emote_y = y + (line_h - EMOTE_H) // 2
                            img_id = self.canvas.create_image(
                                x, emote_y, image=photo, anchor='nw', tags='msg')
                            items.append(img_id)
                            self._register_animated_item(img_id, eid)
                            x += EMOTE_SIZE + EMOTE_PAD_RIGHT
                y += line_h
            if command_response:
                cmd_lines = self._wrap_to_lines(command_response, max_width, self.text_font)
                for line in cmd_lines:
                    self._draw_outlined_text(
                        self.padding + 8, y, line, self.text_font, '#FFCC44', items)
                    y += self.line_spacing
                total_h += len(cmd_lines) * self.line_spacing
            block = {
                'start_y': start_y, 'height': total_h,
                'items': items, 'bg_id': bg_id, 'msg_id': msg_id,
            }
            if missing_emotes:
                block['_pending_emotes'] = True
                self.message_blocks.append(block)
                self._schedule_emote_retry_block(
                    block, username, message, name_color, msg_color, badge,
                    emotes_list, command_response, censored_ranges, msg_id,
                    retry_count=0, is_highlighted=is_highlighted, timestamp=timestamp)
            else:
                self.message_blocks.append(block)
        except Exception as e:
            log_to_gui(f"_render_chat_with_emotes error: {e}", "ERROR")
            raise

    def _schedule_emote_retry_block(self, block, username, message, name_color,
                                     msg_color, badge, emotes_list,
                                     command_response, censored_ranges,
                                     msg_id, retry_count=0,
                                     is_highlighted=False, timestamp=None):
        if retry_count >= EMOTE_RETRY_MAX:
            return
        if not self.running:
            return

        def _check():
            if not self.running:
                return
            try:
                if block not in self.message_blocks:
                    return
            except Exception:
                return
            try:
                all_ready = True
                for _, _, eid in emotes_list:
                    if get_emote_photo(eid, self.root) is None:
                        all_ready = False
                        break
                if all_ready:
                    self._replace_emote_block(
                        block, username, message, name_color, msg_color, badge,
                        emotes_list, command_response, censored_ranges, msg_id,
                        is_highlighted=is_highlighted, timestamp=timestamp)
                else:
                    self.root.after(
                        EMOTE_RETRY_DELAY,
                        lambda: self._schedule_emote_retry_block(
                            block, username, message, name_color, msg_color, badge,
                            emotes_list, command_response, censored_ranges, msg_id,
                            retry_count + 1,
                            is_highlighted=is_highlighted, timestamp=timestamp))
            except Exception:
                pass
        try:
            self.root.after(EMOTE_RETRY_DELAY, _check)
        except Exception:
            pass

    def _replace_emote_block(self, block, username, message, name_color,
                              msg_color, badge, emotes_list,
                              command_response, censored_ranges, msg_id,
                              is_highlighted=False, timestamp=None):
        try:
            if block not in self.message_blocks:
                return
            idx = self.message_blocks.index(block)
            old_start_y = block['start_y']
            for iid in list(block.get('items', [])):
                self._animated_items.pop(iid, None)
                try:
                    self.canvas.delete(iid)
                except Exception:
                    pass
            old_mid = block.get('msg_id')
            self.message_blocks.pop(idx)
            if old_mid:
                self.message_index_by_id.pop(old_mid, None)
            self._render_chat_with_emotes_at(
                old_start_y, username, message, name_color, msg_color, badge,
                emotes_list, self._rendering_items,
                command_response=command_response,
                censored_ranges=censored_ranges,
                msg_id=msg_id,
                is_highlighted=is_highlighted,
                timestamp=timestamp)
            if msg_id:
                for b in reversed(self.message_blocks):
                    if b.get('msg_id') == msg_id:
                        self.message_index_by_id[msg_id] = b
                        break
        except Exception as e:
            log_to_gui(f"_replace_emote_block error: {e}", "ERROR")

    def _render_chat_with_emotes_at(self, start_y, username, message, name_color,
                                     msg_color, badge, emotes_list, items,
                                     command_response=None, censored_ranges=None,
                                     msg_id=None, is_highlighted=False, timestamp=None):
        try:
            EMOTE_SIZE = 22
            EMOTE_W = EMOTE_SIZE + 6
            EMOTE_H = EMOTE_SIZE
            EMOTE_PAD_LEFT = 3
            EMOTE_PAD_RIGHT = 3
            indent = 4
            NAME_TO_MSG_GAP = max(self.name_to_msg_gap, 6)
            max_width = self.cfg['width'] - (self.padding * 2)
            parts = split_message_with_emotes(message, emotes_list)
            emote_photos = {}
            for part in parts:
                if part[0] == 'emote':
                    eid = part[1]
                    if eid not in emote_photos:
                        emote_photos[eid] = get_emote_photo(eid, self.root)
            lines_content = []
            current_line = []
            current_line_w = 0
            for part in parts:
                if part[0] == 'text':
                    text = part[1]
                    if not text:
                        continue
                    words = text.split(' ')
                    for wi, word in enumerate(words):
                        if not word:
                            if current_line:
                                try:
                                    current_line_w += self.text_font.measure(' ')
                                except Exception:
                                    pass
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
                        try:
                            w = self.text_font.measure(word_display)
                        except Exception:
                            w = len(word_display) * 8
                        if current_line_w + w > max_width - indent and current_line:
                            lines_content.append(current_line)
                            current_line = []
                            current_line_w = 0
                            word_display = word
                            try:
                                w = self.text_font.measure(word_display)
                            except Exception:
                                w = len(word_display) * 8
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
                        try:
                            w = self.text_font.measure(fallback)
                        except Exception:
                            w = len(fallback) * 8
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
            y = start_y
            bg_id = None
            text_render_color = msg_color
            if is_highlighted:
                try:
                    with _filters_lock:
                        hl_color = _filters_config.get('highlight_color', '#FFFF00')
                    text_render_color = hl_color
                    hl_id = self.canvas.create_rectangle(
                        self.padding - 2, start_y,
                        self.cfg['width'] - self.padding + 2, start_y + total_h,
                        fill='', outline=hl_color, width=2, tags='msg')
                    items.append(hl_id)
                except Exception:
                    pass
            if self.cfg.get('bg_enabled', True):
                bg_id = self.canvas.create_rectangle(
                    self.padding, start_y,
                    self.cfg['width'] - self.padding, start_y + total_h,
                    fill=self._get_bg_color_with_alpha(), outline='', tags='msg')
                items.append(bg_id)
            self._draw_name_header(self.padding, y, badge, username, name_color, items,
                                    timestamp_ts=timestamp)
            y += header_h + NAME_TO_MSG_GAP
            for line_idx, line_parts in enumerate(lines_content):
                x = self.padding + indent
                line_h = line_heights[line_idx]
                try:
                    text_baseline_y = y + (line_h - self.text_font.metrics('linespace')) // 2
                except Exception:
                    text_baseline_y = y
                for lpi, lp in enumerate(line_parts):
                    if lp[0] == 'text':
                        text_str = lp[1]
                        if text_str:
                            self._draw_outlined_text(
                                x, text_baseline_y, text_str,
                                self.text_font, text_render_color, items)
                            try:
                                x += self.text_font.measure(text_str)
                            except Exception:
                                x += len(text_str) * 8
                    elif lp[0] == 'emote':
                        eid = lp[1]
                        photo = emote_photos.get(eid)
                        if photo:
                            if lpi > 0:
                                x += EMOTE_PAD_LEFT
                            emote_y = y + (line_h - EMOTE_H) // 2
                            img_id = self.canvas.create_image(
                                x, emote_y, image=photo, anchor='nw', tags='msg')
                            items.append(img_id)
                            self._register_animated_item(img_id, eid)
                            x += EMOTE_SIZE + EMOTE_PAD_RIGHT
                y += line_h
            if command_response:
                cmd_lines = self._wrap_to_lines(command_response, max_width, self.text_font)
                for line in cmd_lines:
                    self._draw_outlined_text(
                        self.padding + 8, y, line, self.text_font, '#FFCC44', items)
                    y += self.line_spacing
                total_h += len(cmd_lines) * self.line_spacing
            new_block = {
                'start_y': start_y, 'height': total_h,
                'items': items, 'bg_id': bg_id, 'msg_id': msg_id,
            }
            self.message_blocks.append(new_block)
            return new_block
        except Exception as e:
            log_to_gui(f"_render_chat_with_emotes_at error: {e}", "ERROR")
            return None

    def update_config(self, new_cfg):
        try:
            old_w = self.cfg['width']
            old_h = self.cfg['height']
            old_bg = self.cfg.get('bg_color')
            old_text_color = self.cfg.get('text_color')
            old_trans = self.cfg.get('translation_color')
            old_enabled = self.cfg.get('bg_enabled', True)
            old_font = self.cfg.get('font_family')
            old_ts = self.cfg.get('show_timestamps', False)
            self.cfg.update(new_cfg)
            self._apply_geometry()
            self.root.attributes('-alpha', self.cfg['opacity'])
            if (self.text_font.cget('size') != self.cfg['font_size']
                    or self.text_font.cget('family') != self.cfg['font_family']):
                self.text_font.configure(size=self.cfg['font_size'], family=self.cfg['font_family'])
                self.name_font.configure(
                    size=max(9, self.cfg['font_size'] - 2), family=self.cfg['font_family'])
                try:
                    self.special_font.configure(
                        size=self.cfg['font_size'], family=self.cfg['font_family'])
                except Exception:
                    pass
                self.line_spacing = self.cfg['font_size'] + 8
                self.name_line_height = max(9, self.cfg['font_size'] - 2) + 8
            if (self.cfg.get('bg_color') != old_bg or
                self.cfg.get('text_color') != old_text_color or
                self.cfg.get('bg_enabled', True) != old_enabled or
                self.cfg.get('translation_color') != old_trans or
                self.cfg.get('font_family') != old_font or
                self.cfg.get('show_timestamps', False) != old_ts or
                old_w != self.cfg['width'] or old_h != self.cfg['height']):
                self._do_clear()
            if self.settings_mode:
                self._redraw_settings_border()
            self.root.after(100, self._make_click_through)
        except Exception as e:
            log_to_gui(f"update_config error: {e}", "ERROR")

    def show(self):
        try:
            self.visible = True
            self.root.deiconify()
            self.root.after(50, self._make_click_through)
        except Exception:
            pass

    def hide(self):
        try:
            self.visible = False
            self.root.withdraw()
        except Exception:
            pass

    def close(self):
        try:
            self.running = False
            self._animation_running = False
            self._animated_items = {}
            should_stop.set()
            try:
                self.root.quit()
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass
        except Exception:
            pass

    def run(self):
        try:
            self.root.mainloop()
        except Exception as e:
            log_to_gui(f"mainloop error: {e}", "ERROR")


class ControlPanel:
    WIN_W = 1050  # Увеличено
    WIN_H = 750   # Увеличено

    def __init__(self, overlay, tray_ref=None):
        self.overlay = overlay
        self.tray_ref = tray_ref
        self.window = None
        self.log_text = None
        self.sliders = {}
        self.is_open = False
        self.max_log_lines = 500
        self.app_state = load_app_state()
        self._slider_debounce = {}
        self.channel_entry = None
        self.connect_btn = None
        self.disconnect_btn = None
        self.status_label = None
        self.current_channel_label = None
        self.brand_label = None
        self._status_poll_id = None
        self._notebook = None
        self._log_poll_id = None
        self._stats_poll_id = None
        self._ignored_listbox = None
        self._ignore_entry = None
        self._hl_kw_entry = None
        self._hl_color_var = None
        self._hl_status_label = None  # Новый лейбл статуса

    def _color_setting(self, parent, label_text, key):
        try:
            frame = tk.Frame(parent, bg='#1e1e1e')
            frame.pack(fill=tk.X, pady=4)
            tk.Label(frame, text=label_text, font=('Segoe UI', 10),
                     bg='#1e1e1e', fg='#aaaaaa', width=22, anchor='w').pack(side=tk.LEFT)
            var = tk.StringVar(value=self.overlay.cfg.get(key, '#000000'))
            entry = tk.Entry(frame, textvariable=var, width=10,
                             bg='#0d0d0d', fg='white', relief='flat',
                             font=('Consolas', 10))
            entry.pack(side=tk.LEFT, padx=(5, 5))

            def pick_color():
                try:
                    from tkinter import colorchooser
                    color = colorchooser.askcolor(title="Choose color", initialcolor=var.get())
                    if color and color[1]:
                        var.set(color[1])
                        self.overlay.cfg[key] = color[1]
                        self.overlay.update_config(self.overlay.cfg)
                        self.overlay._do_clear()
                except Exception:
                    pass
            btn = tk.Button(frame, text="🎨", command=pick_color,
                            bg='#3a3a3a', fg='white', relief='flat',
                            padx=6, pady=2, cursor='hand2')
            btn.pack(side=tk.LEFT)

            def on_color_change(*args):
                try:
                    val = var.get().strip()
                    if re.match(r'^#[0-9a-fA-F]{6}$', val):
                        self.overlay.cfg[key] = val
                        self.overlay.update_config(self.overlay.cfg)
                        self.overlay._do_clear()
                except Exception:
                    pass
            var.trace('w', on_color_change)
        except Exception:
            pass

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
        try:
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
                f"{self.WIN_W}x{self.WIN_H}+{(sw-self.WIN_W)//2}+{(sh-self.WIN_H)//2}")
            self.window.minsize(850, 600)
            self._build_all()
            self.is_open = True
            self._poll_logs()
            self._poll_stats()
            self._poll_status()
            self.window.bind('<Destroy>', lambda e: self._save_on_close())
        except Exception as e:
            log_to_gui(f"ControlPanel.open error: {e}", "ERROR")

    def _show_about(self):
        try:
            about_window = tk.Toplevel(self.window)
            about_window.title(t("about_title"))
            about_window.configure(bg='#1e1e1e')
            about_window.geometry("420x280")
            about_window.resizable(False, False)
            about_window.transient(self.window)
            try:
                about_window.grab_set()
            except Exception:
                pass
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
        except Exception:
            pass

    def _build_all(self):
        try:
            style = ttk.Style()
            try:
                style.theme_use('clam')
            except Exception:
                pass
            style.configure('TNotebook', background='#1e1e1e', borderwidth=0)
            style.configure('TNotebook.Tab', background='#2a2a2a', foreground='#cccccc',
                            padding=[32, 10], font=('Segoe UI', 10))
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
                ("tab_logs", self._build_log_tab),
                ("tab_settings", self._build_settings_tab),
                ("tab_filters", self._build_filters_tab),
                ("tab_stats", self._build_stats_tab),
                ("tab_alerts", self._build_alerts_tab),
            ]:
                frame = tk.Frame(self._notebook, bg='#1e1e1e')
                self._notebook.add(frame, text=t(tab_key))
                builder(frame)

            def on_tab_change(event):
                try:
                    idx = self._notebook.index(self._notebook.select())
                    # индекс 2 = вкладка настроек (для показа рамок)
                    self.overlay.set_settings_mode(idx == 2)
                except Exception:
                    pass
            self._notebook.bind('<<NotebookTabChanged>>', on_tab_change)
        except Exception as e:
            log_to_gui(f"_build_all error: {e}", "ERROR")

    def _rebuild_ui(self):
        try:
            if not self.window:
                return
            try:
                self.window.unbind_all("<MouseWheel>")
            except Exception:
                pass
            for widget in self.window.winfo_children():
                widget.destroy()
            self.window.title(t("app_title"))
            self._build_all()
            if self.tray_ref:
                self.tray_ref.rebuild_menu()
            if hasattr(self, '_notebook') and self._notebook:
                self._notebook.select(0)
                self.overlay.set_settings_mode(False)
        except Exception:
            pass

    def _build_status_bar(self):
        try:
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
            tk.Label(inner, text=f"  |  {t('about_developer', author=APP_AUTHOR)}",
                font=('Segoe UI', 9), bg='#0d0d0d', fg='#666666').pack(side=tk.LEFT, padx=(8, 0))
            self.status_label = tk.Label(inner, text=t("status_disconnected"),
                font=('Segoe UI', 10, 'bold'), bg='#0d0d0d', fg='#888888')
            self.status_label.pack(side=tk.RIGHT)
            self.current_channel_label = tk.Label(inner, text="",
                font=('Consolas', 10, 'bold'), bg='#0d0d0d', fg='#9146FF')
            self.current_channel_label.pack(side=tk.RIGHT, padx=(0, 10))
        except Exception:
            pass

    def _build_connection_tab(self, parent):
        try:
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
            self.channel_entry.bind('<Control-v>', self._paste_channel)
            self.channel_entry.bind('<Control-V>', self._paste_channel)
            self.channel_entry.bind('<Shift-Insert>', self._paste_channel)
            self.channel_entry.bind('<Control-a>', self._select_all_channel)
            self.channel_entry.bind('<Control-A>', self._select_all_channel)
            self.channel_entry.bind('<Control-c>', self._copy_channel)
            self.channel_entry.bind('<Control-C>', self._copy_channel)
            self.channel_entry.bind('<Control-x>', self._cut_channel)
            self.channel_entry.bind('<Control-X>', self._cut_channel)
            self._channel_menu = tk.Menu(self.channel_entry, tearoff=0,
                bg='#2a2a2a', fg='white',
                activebackground='#9146FF', activeforeground='white')
            self._channel_menu.add_command(label="📋  Вставить", command=self._paste_channel)
            self._channel_menu.add_command(label="📄  Копировать", command=self._copy_channel)
            self._channel_menu.add_command(label="✂  Вырезать", command=self._cut_channel)
            self._channel_menu.add_separator()
            self._channel_menu.add_command(label="🧹  Очистить", command=self._clear_channel)
            self._channel_menu.add_command(label="✅  Подключиться", command=self._on_connect_click)
            self.channel_entry.bind('<Button-3>', self._show_channel_menu)
            self._paste_btn = tk.Button(entry_frame, text="📋 Вставить",
                command=self._paste_channel,
                bg='#3a3a3a', fg='white', font=('Segoe UI', 9),
                relief='flat', padx=10, pady=4, cursor='hand2',
                activebackground='#9146FF', activeforeground='white')
            self._paste_btn.pack(side=tk.RIGHT, padx=(0, 6))
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
        except Exception:
            pass

    def _on_connect_click(self):
        try:
            raw = self.channel_entry.get().strip()
            ok, val = validate_channel_name(raw)
            if not ok:
                self.conn_error_label.config(text=f"✗ {val}")
                return
            self.conn_error_label.config(text="")
            self.app_state['last_channel'] = val
            save_app_state(self.app_state)
            try:
                chat_command.put_nowait(f"CONNECT:{val}")
            except queue.Full:
                pass
            log_to_gui(t("log_connect_request", ch=val), "INFO")
        except Exception:
            pass

    _CHANNEL_URL_RE = re.compile(
        r'(?:https?://)?(?:www\.)?(?:twitch\.tv|m\.twitch\.tv)/'
        r'([A-Za-z0-9_]{3,25})', re.IGNORECASE)
    _CHANNEL_CLEAN_RE = re.compile(r'[^a-zA-Z0-9_]')

    def _clean_channel_input(self, raw: str) -> str:
        try:
            if not raw:
                return ""
            s = raw.strip()
            m = self._CHANNEL_URL_RE.search(s)
            if m:
                s = m.group(1)
            s = s.lstrip('@#/').strip()
            s = s.split()[0] if s.split() else s
            s = self._CHANNEL_CLEAN_RE.sub('', s)
            s = s[:25].lower()
            return s
        except Exception:
            return ""

    def _paste_channel(self, event=None):
        try:
            raw = self.window.clipboard_get()
        except tk.TclError:
            return "break"
        except Exception:
            return "break"
        clean = self._clean_channel_input(raw)
        try:
            self.channel_entry.delete(0, tk.END)
            self.channel_entry.insert(0, clean)
            self.channel_entry.icursor(tk.END)
            self.channel_entry.focus_set()
            if hasattr(self, 'conn_error_label'):
                self.conn_error_label.config(text="")
        except Exception:
            pass
        return "break"

    def _copy_channel(self, event=None):
        try:
            sel = self.channel_entry.selection_get()
            self.window.clipboard_clear()
            self.window.clipboard_append(sel)
        except tk.TclError:
            try:
                val = self.channel_entry.get()
                if val:
                    self.window.clipboard_clear()
                    self.window.clipboard_append(val)
            except Exception:
                pass
        return "break"

    def _cut_channel(self, event=None):
        try:
            self._copy_channel()
            self.channel_entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        return "break"

    def _select_all_channel(self, event=None):
        try:
            self.channel_entry.select_range(0, tk.END)
            self.channel_entry.icursor(tk.END)
        except Exception:
            pass
        return "break"

    def _clear_channel(self):
        try:
            self.channel_entry.delete(0, tk.END)
            self.channel_entry.focus_set()
        except Exception:
            pass

    def _show_channel_menu(self, event):
        try:
            self._channel_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._channel_menu.grab_release()
            except Exception:
                pass

    def _on_disconnect_click(self):
        try:
            chat_command.put_nowait("DISCONNECT")
            log_to_gui(t("log_disconnect_request"), "INFO")
        except Exception:
            pass

    def _poll_status(self):
        if not self.is_open or self.window is None:
            return
        try:
            with connection_lock:
                connected = connection_state['connected']
                connecting = connection_state['connecting']
                current = connection_state['current_channel']
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
        try:
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
            self.log_text.tag_config('time', foreground='#666666')
            self.log_text.tag_config('INFO', foreground='#5599FF')
            self.log_text.tag_config('OK', foreground='#55FF77')
            self.log_text.tag_config('WARN', foreground='#FFCC44')
            self.log_text.tag_config('ERROR', foreground='#FF5555')
            self.log_text.tag_config('CHAT', foreground='#d0d0d0')
            self.log_text.tag_config('user', foreground='#9146FF',
                                              font=('Consolas', 10, 'bold'))
            self.log_text.tag_config('badge', foreground='#FFCC44',
                                              font=('Consolas', 9, 'bold'))
            self.log_text.bind('<Control-c>', lambda e: self._copy_log_selection())
            self.log_text.bind('<Control-C>', lambda e: self._copy_log_selection())
            self.log_text.bind('<Control-Insert>', lambda e: self._copy_log_selection())
            self.log_text.bind('<Control-a>', self._select_all_log)
            self.log_text.bind('<Control-A>', self._select_all_log)
            self._log_menu = tk.Menu(self.log_text, tearoff=0, bg='#2a2a2a', fg='white',
                                      activebackground='#9146FF', activeforeground='white')
            self._log_menu.add_command(label="Копировать", command=self._copy_log_selection)
            self._log_menu.add_command(label="Выделить всё", command=self._select_all_log)
            self._log_menu.add_separator()
            self._log_menu.add_command(label="Очистить", command=self._clear_log)
            self.log_text.bind('<Button-3>', self._show_log_menu)
        except Exception:
            pass

    def _build_settings_tab(self, parent):
        try:
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
            self._section_title(main, t("section_position"))
            self._slider(main, t("slider_x"), 'x', 0, sw - 100)
            self._slider(main, t("slider_y"), 'y', 0, sh - 100)
            self._slider(main, t("slider_w"), 'width', 200, 1600)
            self._slider(main, t("slider_h"), 'height', 100, 1000)
            self._section_title(main, t("section_appearance"))
            self._slider(main, t("slider_opacity"), 'opacity', 0.1, 1.0, is_float=True)
            self._slider(main, t("slider_font"), 'font_size', 8, 32)
            self._slider(main, t("slider_max_msg"), 'max_messages', 20, 300)
            self._slider(main, "Размер эмодзи:", 'emote_size', 14, 48)

            # Выбор шрифта
            font_frame = tk.Frame(main, bg='#1e1e1e')
            font_frame.pack(fill=tk.X, pady=4)
            tk.Label(font_frame, text=t("settings_font_family"),
                     font=('Segoe UI', 10), bg='#1e1e1e', fg='#aaaaaa',
                     width=22, anchor='w').pack(side=tk.LEFT)
            try:
                available_fonts = sorted(set(tkfont.families()))
            except Exception:
                available_fonts = ["Consolas", "Courier New", "Arial", "Segoe UI"]
            font_var = tk.StringVar(value=self.overlay.cfg.get('font_family', 'Consolas'))
            font_combo = ttk.Combobox(font_frame, textvariable=font_var,
                                       values=available_fonts, state='readonly',
                                       font=('Segoe UI', 9), width=30)
            font_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)

            def on_font_change(event=None):
                try:
                    new_font = font_var.get()
                    if new_font and new_font != self.overlay.cfg.get('font_family'):
                        self.overlay.cfg['font_family'] = new_font
                        self.overlay.update_config(self.overlay.cfg)
                except Exception:
                    pass
            font_combo.bind('<<ComboboxSelected>>', on_font_change)

            self._color_setting(main, t("settings_text_color") + ":", "text_color")
            self._color_setting(main, t("settings_bg_color") + ":", "bg_color")

            bg_enabled_var = tk.BooleanVar(value=self.overlay.cfg.get('bg_enabled', True))
            def on_bg_toggle():
                try:
                    self.overlay.cfg['bg_enabled'] = bg_enabled_var.get()
                    self.overlay.update_config(self.overlay.cfg)
                except Exception:
                    pass
            tk.Checkbutton(main, text=t("settings_show_bg"),
                            variable=bg_enabled_var, command=on_bg_toggle,
                            bg='#1e1e1e', fg='white', selectcolor='#9146FF',
                            activebackground='#1e1e1e', activeforeground='white',
                            font=('Segoe UI', 10)).pack(anchor='w', pady=4)

            ts_var = tk.BooleanVar(value=self.overlay.cfg.get('show_timestamps', False))
            def on_ts_toggle():
                try:
                    self.overlay.cfg['show_timestamps'] = ts_var.get()
                    self.overlay.update_config(self.overlay.cfg)
                except Exception:
                    pass
            tk.Checkbutton(main, text=t("settings_show_timestamps"),
                            variable=ts_var, command=on_ts_toggle,
                            bg='#1e1e1e', fg='white', selectcolor='#9146FF',
                            activebackground='#1e1e1e', activeforeground='white',
                            font=('Segoe UI', 10)).pack(anchor='w', pady=4)

            events_var = tk.BooleanVar(value=self.app_state.get('show_events', True))
            def on_events_toggle():
                try:
                    self.app_state['show_events'] = events_var.get()
                    twitch_config['show_events'] = events_var.get()
                    save_app_state(self.app_state)
                except Exception:
                    pass
            tk.Checkbutton(main, text=t("settings_show_events"),
                            variable=events_var, command=on_events_toggle,
                            bg='#1e1e1e', fg='white', selectcolor='#9146FF',
                            activebackground='#1e1e1e', activeforeground='white',
                            font=('Segoe UI', 10)).pack(anchor='w', pady=4)

            translate_var = tk.BooleanVar(value=self.app_state.get('auto_translate', True))
            def on_translate_toggle():
                try:
                    self.app_state['auto_translate'] = translate_var.get()
                    twitch_config['auto_translate'] = translate_var.get()
                    save_app_state(self.app_state)
                    log_to_gui(f"Автоперевод: {'вкл' if translate_var.get() else 'выкл'}", "INFO")
                except Exception:
                    pass
            tk.Checkbutton(main, text=t("settings_auto_translate"),
                            variable=translate_var, command=on_translate_toggle,
                            bg='#1e1e1e', fg='white', selectcolor='#9146FF',
                            activebackground='#1e1e1e', activeforeground='white',
                            font=('Segoe UI', 10)).pack(anchor='w', pady=4)

            censor_var = tk.BooleanVar(value=self.app_state.get('censor_enabled', True))
            def on_censor_toggle():
                try:
                    self.app_state['censor_enabled'] = censor_var.get()
                    twitch_config['censor_enabled'] = censor_var.get()
                    save_app_state(self.app_state)
                    log_to_gui(f"Цензура: {'вкл' if censor_var.get() else 'выкл'}", "INFO")
                except Exception:
                    pass
            tk.Checkbutton(main, text=t("settings_censor"),
                            variable=censor_var, command=on_censor_toggle,
                            bg='#1e1e1e', fg='white', selectcolor='#9146FF',
                            activebackground='#1e1e1e', activeforeground='white',
                            font=('Segoe UI', 10)).pack(anchor='w', pady=4)

            self._section_title(main, t("section_language"))
            self._build_language_selector(main)
            self._section_title(main, "🎨 " + t("settings_translation_color"))
            self._color_setting(main, t("settings_translation_color") + ":", "translation_color")

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

            def _on_wheel(e):
                try:
                    canvas.yview_scroll(int(-1*(e.delta/120)), "units")
                except Exception:
                    pass
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
            canvas.bind_all("<MouseWheel>", _on_wheel)
        except Exception:
            pass

    def _build_filters_tab(self, parent):
        """Вкладка фильтров с прокруткой (как в Настройках)."""
        try:
            # === Оборачиваем содержимое в прокручиваемый canvas ===
            canvas = tk.Canvas(parent, bg='#1e1e1e', highlightthickness=0)
            scrollbar = tk.Scrollbar(parent, orient='vertical', command=canvas.yview)
            scrollable = tk.Frame(canvas, bg='#1e1e1e')
            scrollable.bind("<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable, anchor='nw')
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Весь контент теперь внутри scrollable, а не parent
            outer = tk.Frame(scrollable, bg='#1e1e1e', padx=20, pady=16)
            outer.pack(fill=tk.BOTH, expand=True)
            tk.Label(outer, text=t("filters_title"), font=('Segoe UI', 14, 'bold'),
                     bg='#1e1e1e', fg='#9146FF').pack(anchor='w', pady=(0, 4))
            tk.Label(outer, text=t("filters_subtitle"), font=('Segoe UI', 9),
                     bg='#1e1e1e', fg='#888888').pack(anchor='w', pady=(0, 12))

            # === Фильтр ботов ===
            bots_frame = tk.Frame(outer, bg='#252525', padx=12, pady=10)
            bots_frame.pack(fill=tk.X, pady=(0, 10))
            tk.Label(bots_frame, text=t("filters_bots_section"),
                     font=('Segoe UI', 11, 'bold'), bg='#252525', fg='#FFCC44').pack(anchor='w', pady=(0, 6))
            self._auto_bots_var = tk.BooleanVar(
                value=_filters_config.get('auto_filter_bots', True))
            def on_bots_toggle():
                try:
                    cfg = _filters_config.copy()
                    cfg['auto_filter_bots'] = self._auto_bots_var.get()
                    save_filters_config(cfg)
                    log_to_gui(
                        f"Автофильтр ботов: {'вкл' if self._auto_bots_var.get() else 'выкл'}",
                        "OK")
                except Exception:
                    pass
            tk.Checkbutton(bots_frame, text=t("filters_bots_enable"),
                            variable=self._auto_bots_var, command=on_bots_toggle,
                            bg='#252525', fg='white', selectcolor='#9146FF',
                            activebackground='#252525', activeforeground='white',
                            font=('Segoe UI', 10)).pack(anchor='w')

            # === Игнор-лист ===
            ig_frame = tk.Frame(outer, bg='#252525', padx=12, pady=10)
            ig_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            tk.Label(ig_frame, text=t("filters_ignored_section"),
                     font=('Segoe UI', 11, 'bold'), bg='#252525', fg='#FF7777').pack(anchor='w')
            tk.Label(ig_frame, text=t("filters_ignored_hint"),
                     font=('Segoe UI', 9), bg='#252525', fg='#888888').pack(anchor='w', pady=(2, 6))

            add_row = tk.Frame(ig_frame, bg='#252525')
            add_row.pack(fill=tk.X, pady=(0, 6))
            self._ignore_entry = tk.Entry(add_row, bg='#0d0d0d', fg='white',
                                           insertbackground='white', relief='flat',
                                           font=('Consolas', 11))
            self._ignore_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 6))
            self._ignore_entry.bind('<Return>', lambda e: self._filters_ignore_add())
            tk.Button(add_row, text=t("filters_ignored_add"), command=self._filters_ignore_add,
                      bg='#2d5a27', fg='white', font=('Segoe UI', 9, 'bold'),
                      relief='flat', padx=14, pady=6, cursor='hand2').pack(side=tk.LEFT)

            list_frame = tk.Frame(ig_frame, bg='#252525')
            list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
            list_scroll = tk.Scrollbar(list_frame)
            list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self._ignored_listbox = tk.Listbox(list_frame,
                bg='#0d0d0d', fg='#d0d0d0', selectbackground='#9146FF',
                font=('Consolas', 10), relief='flat', bd=0,
                yscrollcommand=list_scroll.set, height=10)
            self._ignored_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            list_scroll.config(command=self._ignored_listbox.yview)
            tk.Button(ig_frame, text=t("filters_ignored_remove"),
                      command=self._filters_ignore_remove,
                      bg='#6a1a1a', fg='white', font=('Segoe UI', 9),
                      relief='flat', padx=14, pady=5, cursor='hand2').pack(anchor='w')

            # === Подсветка ===
            hl_frame = tk.Frame(outer, bg='#252525', padx=12, pady=10)
            hl_frame.pack(fill=tk.X, pady=(0, 10))
            tk.Label(hl_frame, text=t("filters_highlight_section"),
                     font=('Segoe UI', 11, 'bold'), bg='#252525', fg='#FFFF44').pack(anchor='w')

            hl_top = tk.Frame(hl_frame, bg='#252525')
            hl_top.pack(fill=tk.X, pady=(6, 4))
            self._hl_enabled_var = tk.BooleanVar(
                value=_filters_config.get('highlight_enabled', True))
            def on_hl_toggle():
                try:
                    cfg = _filters_config.copy()
                    cfg['highlight_enabled'] = self._hl_enabled_var.get()
                    save_filters_config(cfg)
                except Exception:
                    pass
            tk.Checkbutton(hl_top, text=t("filters_highlight_enable"),
                            variable=self._hl_enabled_var, command=on_hl_toggle,
                            bg='#252525', fg='white', selectcolor='#9146FF',
                            activebackground='#252525', activeforeground='white',
                            font=('Segoe UI', 10)).pack(side=tk.LEFT)

            tk.Label(hl_top, text=t("filters_highlight_color"),
                     bg='#252525', fg='#aaaaaa', font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=(20, 4))
            self._hl_color_var = tk.StringVar(value=_filters_config.get('highlight_color', '#FFFF00'))
            hl_color_entry = tk.Entry(hl_top, textvariable=self._hl_color_var, width=10,
                                       bg='#0d0d0d', fg='white', insertbackground='white',
                                       relief='flat', font=('Consolas', 10))
            hl_color_entry.pack(side=tk.LEFT)
            def pick_hl_color():
                try:
                    from tkinter import colorchooser
                    color = colorchooser.askcolor(
                        title="Highlight color", initialcolor=self._hl_color_var.get())
                    if color and color[1]:
                        self._hl_color_var.set(color[1])
                        self._on_hl_color_change()
                except Exception:
                    pass
            def _on_hl_color_change(*args):
                try:
                    val = self._hl_color_var.get().strip()
                    if re.match(r'^#[0-9a-fA-F]{6}$', val):
                        cfg = _filters_config.copy()
                        cfg['highlight_color'] = val
                        save_filters_config(cfg)
                        self.overlay._do_clear()
                except Exception:
                    pass
            self._hl_color_var.trace('w', _on_hl_color_change)
            tk.Button(hl_top, text="🎨", command=pick_hl_color,
                      bg='#3a3a3a', fg='white', relief='flat',
                      padx=6, pady=2, cursor='hand2').pack(side=tk.LEFT, padx=(4, 0))

            kw_row = tk.Frame(hl_frame, bg='#252525')
            kw_row.pack(fill=tk.X, pady=(8, 2))
            tk.Label(kw_row, text=t("filters_highlight_keywords"),
                     bg='#252525', fg='#aaaaaa', font=('Segoe UI', 9)).pack(side=tk.LEFT)

            entry_container = tk.Frame(kw_row, bg='#252525')
            entry_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

            self._hl_kw_entry = tk.Entry(entry_container, bg='#0d0d0d', fg='white',
                                          insertbackground='white', relief='flat',
                                          font=('Consolas', 10))
            self._hl_kw_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
            self._hl_kw_entry.bind('<Return>', lambda e: self._filters_hl_save())
            self._hl_kw_entry.bind('<FocusOut>', lambda e: self._filters_hl_save())

            tk.Button(entry_container, text="💾", command=self._filters_hl_save,
                      bg='#2d5a27', fg='white', font=('Segoe UI', 10),
                      relief='flat', padx=10, pady=2, cursor='hand2').pack(side=tk.RIGHT, padx=(4, 0))

            self._hl_status_label = tk.Label(hl_frame, text="", bg='#252525', fg='#00FFAA',
                                              font=('Segoe UI', 8), anchor='w')
            self._hl_status_label.pack(fill=tk.X, pady=(2, 0))
            tk.Label(hl_frame, text=t("filters_highlight_hint"),
                     bg='#252525', fg='#666666', font=('Segoe UI', 8)).pack(anchor='w', pady=(2, 0))

            tk.Button(outer, text=t("filters_save"), command=self._filters_save_all,
                      bg='#2d5a27', fg='white', font=('Segoe UI', 10, 'bold'),
                      relief='flat', padx=20, pady=8, cursor='hand2').pack(pady=(10, 0))

            self._refresh_ignored_list()
            self._refresh_hl_kw()

            # === Прокрутка колёсиком мыши ===
            def _on_wheel(e):
                try:
                    canvas.yview_scroll(int(-1*(e.delta/120)), "units")
                except Exception:
                    pass
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
            canvas.bind_all("<MouseWheel>", _on_wheel)
        except Exception as e:
            log_to_gui(f"_build_filters_tab error: {e}", "ERROR")

    def _refresh_ignored_list(self):
        try:
            if not self._ignored_listbox:
                return
            self._ignored_listbox.delete(0, tk.END)
            with _filters_lock:
                users = _filters_config.get('ignored_users', []) or []
            if not users:
                self._ignored_listbox.insert(tk.END, "(" + t("filters_ignored_empty") + ")")
                self._ignored_listbox.itemconfig(0, fg='#666666')
            else:
                for u in users:
                    self._ignored_listbox.insert(tk.END, f"  {u}")
        except Exception:
            pass

    def _refresh_hl_kw(self):
        try:
            if not self._hl_kw_entry:
                return
            with _filters_lock:
                kws = _filters_config.get('highlight_keywords', []) or []
            self._hl_kw_entry.delete(0, tk.END)
            self._hl_kw_entry.insert(0, ', '.join(kws))
            if hasattr(self, '_hl_status_label') and self._hl_status_label:
                if kws:
                    self._hl_status_label.config(text=f"✅ Активно слов: {len(kws)}", fg='#00FFAA')
                else:
                    self._hl_status_label.config(text="⚠️ Список слов пуст", fg='#FFCC44')
        except Exception:
            pass

    def _filters_ignore_add(self):
        try:
            raw = self._ignore_entry.get().strip().lower().lstrip('@')
            if not raw:
                return
            raw = re.sub(r'[^a-zA-Z0-9_]', '', raw)
            if not raw:
                return
            with _filters_lock:
                users = list(_filters_config.get('ignored_users', []) or [])
                if raw in users:
                    log_to_gui(t("filters_ignored_exists"), "WARN")
                    return
                users.append(raw)
            cfg = _filters_config.copy()
            cfg['ignored_users'] = users
            save_filters_config(cfg)
            self._ignore_entry.delete(0, tk.END)
            self._refresh_ignored_list()
            log_to_gui(t("filters_ignored_added", user=raw), "OK")
        except Exception:
            pass

    def _filters_ignore_remove(self):
        try:
            sel = self._ignored_listbox.curselection()
            if not sel:
                return
            with _filters_lock:
                users = list(_filters_config.get('ignored_users', []) or [])
            idx = sel[0]
            if 0 <= idx < len(users):
                users.pop(idx)
                cfg = _filters_config.copy()
                cfg['ignored_users'] = users
                save_filters_config(cfg)
                self._refresh_ignored_list()
                log_to_gui(t("filters_ignored_removed"), "OK")
        except Exception:
            pass

    def _filters_hl_save(self):
        try:
            if not self._hl_kw_entry:
                return
            raw = self._hl_kw_entry.get().strip()
            kws = [k.strip() for k in raw.split(',') if k.strip()]
            cfg = _filters_config.copy()
            cfg['highlight_keywords'] = kws
            save_filters_config(cfg)
            # Обновляем статус
            if hasattr(self, '_hl_status_label') and self._hl_status_label:
                if kws:
                    self._hl_status_label.config(text=f"✅ Сохранено! Активно слов: {len(kws)}", fg='#00FFAA')
                else:
                    self._hl_status_label.config(text="⚠️ Сохранено, но список пуст", fg='#FFCC44')
            log_to_gui(f"Ключевые слова подсветки обновлены: {len(kws)} шт.", "OK")
        except Exception:
            pass

    def _filters_save_all(self):
        try:
            self._filters_hl_save()
            cfg = _filters_config.copy()
            cfg['auto_filter_bots'] = self._auto_bots_var.get() if hasattr(self, '_auto_bots_var') else True
            cfg['highlight_enabled'] = self._hl_enabled_var.get() if hasattr(self, '_hl_enabled_var') else True
            if hasattr(self, '_hl_color_var'):
                c = self._hl_color_var.get().strip()
                if re.match(r'^#[0-9a-fA-F]{6}$', c):
                    cfg['highlight_color'] = c
            save_filters_config(cfg)
            log_to_gui(t("filters_saved"), "OK")
        except Exception:
            pass

    def _build_language_selector(self, parent):
        try:
            frame = tk.Frame(parent, bg='#1e1e1e')
            frame.pack(fill=tk.X, pady=4)
            current = self.app_state.get('language', 'en')

            def make_btn(code, label):
                is_active = (current == code)
                return tk.Button(frame, text=label,
                    command=lambda: self._change_language(code),
                    bg='#9146FF' if is_active else '#3a3a3a', fg='white',
                    font=('Segoe UI', 10, 'bold' if is_active else 'normal'),
                    relief='flat', padx=20, pady=8, cursor='hand2',
                    activebackground='#7a36d6', activeforeground='white')

            make_btn('en', t("lang_en")).pack(side=tk.LEFT, padx=(0, 8))
            make_btn('ru', t("lang_ru")).pack(side=tk.LEFT)
        except Exception:
            pass

    def _change_language(self, lang):
        try:
            if lang == self.app_state.get('language'):
                return
            self.app_state['language'] = lang
            save_app_state(self.app_state)
            set_language(lang)
            _build_profanity_pattern()
            log_to_gui(t("log_lang_changed"), "OK")
            self._rebuild_ui()
        except Exception:
            pass

    def _build_stats_tab(self, parent):
        try:
            main = tk.Frame(parent, bg='#1e1e1e', padx=24, pady=18)
            main.pack(fill=tk.BOTH, expand=True)
            tk.Label(main, text=t("stats_title"), font=('Segoe UI', 14, 'bold'),
                     bg='#1e1e1e', fg='#9146FF').pack(pady=(0, 16), anchor='w')
            self.stats_labels = {}
            rows = [
                ('channel', t("stats_channel")),
                ('duration', t("stats_duration")),
                ('messages', t("stats_messages")),
                ('filtered', "Отфильтровано:"),
                ('users', t("stats_users")),
                ('mods', t("stats_mods")),
                ('subs', t("stats_subs")),
                ('vips', t("stats_vips")),
                ('reconnects', t("stats_reconnects")),
                ('errors', t("stats_errors")),
                ('pings', t("stats_pings")),
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
        except Exception:
            pass

    def _section_title(self, parent, text):
        try:
            tk.Label(parent, text=text, font=('Segoe UI', 11, 'bold'),
                     bg='#1e1e1e', fg='#9146FF', anchor='w').pack(fill=tk.X, pady=(10, 6))
        except Exception:
            pass

    def _slider(self, parent, label_text, key, min_val, max_val, is_float=False):
        try:
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
                try:
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
                except Exception:
                    pass
            slider.configure(command=on_slide)
            self.sliders[key] = slider
        except Exception:
            pass

    def _save(self):
        try:
            save_overlay_config(self.overlay.cfg)
            orig = self.save_btn['text']
            self.save_btn.config(text=t("btn_saved"), bg='#1e7a1e')
            self.window.after(1200, lambda: self.save_btn.config(text=orig, bg='#2d5a27'))
            log_to_gui(t("log_settings_saved"), "OK")
        except Exception:
            pass

    def _reset(self):
        try:
            new_cfg = DEFAULT_OVERLAY_CONFIG.copy()
            self.overlay.update_config(new_cfg)
            for key, slider in self.sliders.items():
                if key in new_cfg:
                    slider.set(new_cfg[key])
            self._rebuild_ui()
            log_to_gui(t("log_settings_reset"), "INFO")
        except Exception:
            pass

    def _clear_log(self):
        try:
            if self.log_text:
                self.log_text.config(state='normal')
                self.log_text.delete('1.0', tk.END)
                self.log_text.config(state='disabled')
        except Exception:
            pass

    def _copy_log_selection(self, event=None):
        try:
            sel = self.log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.window.clipboard_clear()
            self.window.clipboard_append(sel)
        except tk.TclError:
            pass
        return "break"

    def _select_all_log(self, event=None):
        try:
            self.log_text.tag_add(tk.SEL, "1.0", tk.END)
            self.log_text.mark_set(tk.INSERT, "1.0")
            self.log_text.see(tk.INSERT)
        except Exception:
            pass
        return "break"

    def _show_log_menu(self, event):
        try:
            self._log_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._log_menu.grab_release()
            except Exception:
                pass

    def _poll_logs(self):
        if not self.is_open or self.window is None:
            return
        try:
            count = 0
            while count < 150:
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
            self._log_poll_id = self.window.after(100, self._poll_logs)
        except Exception:
            pass

    def _append_log(self, item):
        try:
            if not self.log_text:
                return
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
                'channel': f"#{current_channel}" if current_channel != '—' else '—',
                'duration': f"{h:02d}:{m:02d}:{s:02d}",
                'messages': str(stats['total_messages']),
                'filtered': str(stats.get('filtered_messages', 0)),
                'users': str(len(stats['unique_users_hashed'])),
                'mods': str(len(stats['users_by_role']['moderators'])),
                'subs': str(len(stats['users_by_role']['subscribers'])),
                'vips': str(len(stats['users_by_role']['vips'])),
                'reconnects': str(stats['reconnects']),
                'errors': str(stats['errors']),
                'pings': str(stats['irc_pings']),
            }
            for k, v in updates.items():
                if k in self.stats_labels:
                    self.stats_labels[k].config(text=v)
            self._stats_poll_id = self.window.after(1000, self._poll_stats)
        except Exception:
            pass

    def _on_close(self):
        try:
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
            for pid in (self._status_poll_id, self._log_poll_id, self._stats_poll_id):
                if pid:
                    try:
                        self.window.after_cancel(pid)
                    except Exception:
                        pass
            try:
                if self.window:
                    self.window.destroy()
            except Exception:
                pass
            self.window = None
        except Exception:
            pass

    def _build_alerts_tab(self, parent):
        try:
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
        except Exception:
            pass

    def _refresh_alerts_list(self):
        try:
            if not hasattr(self, '_alerts_listbox'):
                return
            self._alerts_listbox.delete(0, tk.END)
            for alert in _alerts_config.get('alerts', []):
                kws = ', '.join(alert.get('keywords', []))
                lbl = alert.get('label', '')
                dur = alert.get('duration', 4000)
                self._alerts_listbox.insert(tk.END, f"{lbl}  [{kws}]  {dur}ms")
        except Exception:
            pass

    def _on_alert_select(self, event=None):
        try:
            sel = self._alerts_listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            alert = _alerts_config.get('alerts', [])[idx]
            self._alert_kw_var.set(', '.join(alert.get('keywords', [])))
            self._alert_url_var.set(alert.get('image_url', ''))
            self._alert_label_var.set(alert.get('label', '🔥'))
            self._alert_dur_var.set(str(alert.get('duration', 4000)))
        except Exception:
            pass

    def _alert_add_or_update(self):
        try:
            kws_raw = self._alert_kw_var.get().strip()
            url = self._alert_url_var.get().strip()
            label = self._alert_label_var.get().strip() or '🔥'
            try:
                duration = int(self._alert_dur_var.get().strip())
                duration = max(500, min(30000, duration))
            except Exception:
                duration = 4000
            if not kws_raw:
                return
            keywords = [k.strip() for k in kws_raw.split(',') if k.strip()]
            if not keywords:
                return
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
        except Exception:
            pass

    def _alert_delete(self):
        try:
            sel = self._alerts_listbox.curselection()
            if not sel:
                return
            global _alerts_config
            cfg = _alerts_config.copy()
            alerts = cfg.get('alerts', [])
            idx = sel[0]
            if 0 <= idx < len(alerts):
                del alerts[idx]
            cfg['alerts'] = alerts
            save_alerts_config(cfg)
            self._refresh_alerts_list()
            log_to_gui(t("alerts_deleted"), "INFO")
        except Exception:
            pass

    def _alert_test(self):
        try:
            url = self._alert_url_var.get().strip()
            label = self._alert_label_var.get().strip() or '🔥'
            try:
                duration = int(self._alert_dur_var.get().strip())
            except Exception:
                duration = 4000
            test_alert = {'image_url': url, 'label': label, 'duration': duration, 'keywords': []}
            self.overlay.trigger_alert(test_alert)
            log_to_gui(t("alerts_test_fired", label=label), "INFO")
        except Exception:
            pass

    def _save_alerts_global(self):
        try:
            cfg = _alerts_config.copy()
            cfg['enabled'] = self._alerts_enabled_var.get()
            try:
                cfg['cooldown'] = max(0, int(self._cooldown_var.get()))
            except Exception:
                pass
            save_alerts_config(cfg)
        except Exception:
            pass

    def _browse_alert_image(self):
        try:
            filepath = filedialog.askopenfilename(
                title="Select alert image",
                filetypes=[
                    ("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                    ("GIF animations", "*.gif"),
                    ("All files", "*.*"),
                ])
            if filepath:
                self._alert_url_var.set(filepath)
        except Exception:
            pass


class TrayManager:
    def __init__(self, overlay, control_panel):
        self.overlay = overlay
        self.control_panel = control_panel
        self.icon = None

    def _create_icon_image(self):
        try:
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
        except Exception:
            return Image.new('RGBA', (64, 64), (145, 70, 255, 255))

    def _open_panel(self, icon=None, item=None):
        try:
            self.overlay.root.after_idle(self.control_panel.open)
        except Exception:
            pass

    def _quit(self, icon=None, item=None):
        try:
            try:
                if (self.control_panel.window and
                    self.control_panel.window.winfo_exists() and
                    self.control_panel.channel_entry):
                    channel = self.control_panel.channel_entry.get().strip()
                    if channel:
                        state = load_app_state()
                        state['last_channel'] = channel
                        save_app_state(state)
            except Exception:
                pass
            should_stop.set()
            try:
                chat_command.put_nowait("STOP")
            except Exception:
                pass
            if self.icon:
                try:
                    self.icon.stop()
                except Exception:
                    pass
            self.overlay.close()
        except Exception:
            pass

    def _build_menu(self):
        try:
            return pystray.Menu(
                pystray.MenuItem(t("tray_open"), self._open_panel, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(f"ℹ️ {t('about_title')}", self._show_about),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(f"{APP_NAME} v{APP_VERSION}", None, enabled=False),
                pystray.MenuItem(t("tray_quit"), self._quit),
            )
        except Exception:
            return None

    def _show_about(self, icon=None, item=None):
        try:
            if self.overlay.root:
                self.overlay.root.after_idle(self.control_panel._show_about)
        except Exception:
            pass

    def rebuild_menu(self):
        try:
            if self.icon:
                self.icon.menu = self._build_menu()
                self.icon.update_menu()
        except Exception:
            pass

    def start(self):
        if not TRAY_OK or not PIL_OK:
            return
        try:
            self.icon = pystray.Icon(
                "TwitchOverlay", self._create_icon_image(),
                "Twitch Ghost Overlay", self._build_menu())
            threading.Thread(target=self._run_icon, daemon=True).start()
        except Exception as e:
            log_to_gui(f"Tray start error: {e}", "WARN")

    def _run_icon(self):
        try:
            if self.icon:
                self.icon.run()
        except Exception:
            pass


def log_to_gui(message, level="INFO"):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            log_queue.put_nowait(('system', timestamp, level, message))
        except queue.Full:
            pass
        if system_log_file:
            try:
                system_log_file.write(f"[{timestamp}] [{level}] {message}\n")
                system_log_file.flush()
            except Exception:
                pass
    except Exception:
        pass


def log_chat_to_gui(username, message, badges):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            log_queue.put_nowait(('chat', timestamp, username, badges, message))
        except queue.Full:
            pass
    except Exception:
        pass


def hash_user(username):
    try:
        return hashlib.sha256((HASH_SALT + username.lower()).encode()).hexdigest()[:12]
    except Exception:
        return "unknown"


def get_color_for_user(username):
    try:
        cached = user_colors.get_safe(username)
        if cached:
            return cached
        idx = sum(ord(c) for c in username) % len(DEFAULT_COLORS)
        color = DEFAULT_COLORS[idx]
        user_colors.set_safe(username, color)
        return color
    except Exception:
        return '#9146FF'


def save_stats_snapshot():
    if not twitch_config["log_stats"] or twitch_config["test_mode"]:
        return
    try:
        channel = connection_state.get('current_channel') or 'unknown'
        os.makedirs(LOGS_DIR, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        filename = os.path.join(LOGS_DIR, f"{channel}_{today}_stats.json")
        duration = time.time() - stats["session_start"]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "channel": channel,
                "session_start": stats["session_start_iso"],
                "session_end": datetime.now().isoformat(),
                "duration_seconds": int(duration),
                "total_messages": stats["total_messages"],
                "filtered_messages": stats.get("filtered_messages", 0),
                "unique_users_count": len(stats["unique_users_hashed"]),
                "events_count": stats.get("events_count", 0),
                "errors": stats["errors"],
                "reconnects": stats["reconnects"],
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def parse_emotes_tag(emotes_str, message_text):
    try:
        if not emotes_str:
            return []
        result = []
        for emote_block in emotes_str.split("/"):
            if ":" not in emote_block:
                continue
            emote_id, positions = emote_block.split(":", 1)
            if not re.match(r'^[a-zA-Z0-9_]{1,64}$', emote_id):
                continue
            for pos in positions.split(","):
                if "-" not in pos:
                    continue
                start_s, end_s = pos.split("-", 1)
                try:
                    start = int(start_s)
                    end = int(end_s) + 1
                except (ValueError, OverflowError):
                    continue
                if start < 0 or end <= start:
                    continue
                result.append((start, end, emote_id))
        result.sort(key=lambda x: x[0])
        return result
    except Exception:
        return []


def _find_emote_path(emote_id):
    gif_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.gif")
    png_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.png")
    if os.path.exists(gif_path):
        return gif_path
    if os.path.exists(png_path):
        return png_path
    return None


def _extract_pil_frames(path, size=22):
    try:
        pil_img = Image.open(path)
        is_animated = getattr(pil_img, 'is_animated', False)
        n_frames = getattr(pil_img, 'n_frames', 1)
        if is_animated and n_frames > 1:
            frames = []
            delays = []
            n_frames = min(n_frames, MAX_ANIMATED_FRAMES)
            for i in range(n_frames):
                try:
                    pil_img.seek(i)
                    frame = pil_img.copy().convert('RGBA').resize(
                        (size, size), Image.BILINEAR)
                    frames.append(frame)
                    d = pil_img.info.get('duration', 100)
                    if not isinstance(d, int) or d <= 0:
                        d = 100
                    delays.append(max(20, min(d, 500)))
                except Exception:
                    break
            if not frames:
                return None
            return (frames, delays, True)
        else:
            frame = pil_img.convert('RGBA').resize((size, size), Image.BILINEAR)
            return ([frame], [4000], False)
    except Exception as e:
        try:
            log_to_gui(f"[EMOTE] PIL extract error {os.path.basename(path)}: {e}", "ERROR")
        except Exception:
            pass
        return None


def _ensure_pil_cached(emote_id, path):
    try:
        with _emote_pil_lock:
            if emote_id in _emote_pil_cache:
                _emote_pil_cache.move_to_end(emote_id)
                return
            if emote_id in _emote_pil_pending:
                return
            _emote_pil_pending.add(emote_id)
        result = _extract_pil_frames(path)
        if result is None:
            with _emote_pil_lock:
                _emote_pil_cache[emote_id] = None
                _emote_pil_cache.move_to_end(emote_id)
                while len(_emote_pil_cache) > MAX_EMOTE_PIL_CACHE_ENTRIES:
                    _emote_pil_cache.popitem(last=False)
        else:
            with _emote_pil_lock:
                _emote_pil_cache[emote_id] = result
                _emote_pil_cache.move_to_end(emote_id)
                while len(_emote_pil_cache) > MAX_EMOTE_PIL_CACHE_ENTRIES:
                    _emote_pil_cache.popitem(last=False)
    except Exception:
        pass
    finally:
        with _emote_pil_lock:
            _emote_pil_pending.discard(emote_id)


def _emote_download_worker():
    while not should_stop.is_set():
        try:
            eid = _emote_download_queue.get(timeout=2.0)
        except queue.Empty:
            continue
        try:
            with _emote_download_lock:
                _emote_download_queued.discard(eid)
                _emote_download_inflight.add(eid)
            try:
                path = _find_emote_path(eid)
                if not path:
                    path = download_emote(eid)
                if path:
                    _ensure_pil_cached(eid, path)
            finally:
                with _emote_download_lock:
                    _emote_download_inflight.discard(eid)
        except Exception:
            pass
        finally:
            try:
                _emote_download_queue.task_done()
            except Exception:
                pass


def _ensure_emote_download_workers():
    global _emote_download_workers_started
    if _emote_download_workers_started:
        return
    _emote_download_workers_started = True
    for i in range(EMOTE_DL_WORKERS):
        try:
            threading.Thread(
                target=_emote_download_worker,
                daemon=True, name=f"EmoteDL-{i}").start()
        except Exception:
            pass


def preload_emote_async(emote_id):
    try:
        _ensure_emote_download_workers()
        with _emote_lock:
            if _emote_images.get(emote_id) is not None:
                _emote_lru[emote_id] = time.time()
                _emote_lru.move_to_end(emote_id)
                return
        with _emote_pil_lock:
            if emote_id in _emote_pil_cache:
                _emote_pil_cache.move_to_end(emote_id)
                return
            if emote_id in _emote_pil_pending:
                return
        with _emote_download_lock:
            if emote_id in _emote_download_queued or emote_id in _emote_download_inflight:
                return
            _emote_download_queued.add(emote_id)
        try:
            _emote_download_queue.put_nowait(emote_id)
        except Exception:
            with _emote_download_lock:
                _emote_download_queued.discard(emote_id)
    except Exception:
        pass


def _evict_emote_cache():
    try:
        with _emote_lock:
            while len(_emote_images) > MAX_EMOTE_CACHE_ENTRIES:
                if not _emote_lru:
                    break
                old_id, _ = _emote_lru.popitem(last=False)
                _emote_images.pop(old_id, None)
                _emote_frames.pop(old_id, None)
                _emote_delays.pop(old_id, None)
                _emote_is_animated.pop(old_id, None)
            while len(_emote_images) > MAX_EMOTE_CACHE_ENTRIES:
                _emote_images.popitem(last=False)
    except Exception:
        pass


def get_emote_photo(emote_id, root):
    try:
        with _emote_lock:
            if emote_id in _emote_images:
                img = _emote_images[emote_id]
                if img is not None:
                    _emote_lru[emote_id] = time.time()
                    _emote_lru.move_to_end(emote_id)
                return img
        if not PIL_OK:
            with _emote_lock:
                _emote_images[emote_id] = None
            return None
        with _emote_pil_lock:
            pil_bundle = _emote_pil_cache.get(emote_id, 'MISS')
            if pil_bundle != 'MISS':
                _emote_pil_cache.move_to_end(emote_id)
        if pil_bundle == 'MISS':
            preload_emote_async(emote_id)
            return None
        if pil_bundle is None:
            with _emote_lock:
                _emote_images[emote_id] = None
            return None
        frames_pil, delays, is_animated = pil_bundle
        photos = []
        for f in frames_pil:
            try:
                photos.append(ImageTk.PhotoImage(f, master=root))
            except Exception:
                photos.append(None)
        photos = [p for p in photos if p is not None]
        if not photos:
            with _emote_lock:
                _emote_images[emote_id] = None
            return None
        with _emote_lock:
            _emote_frames[emote_id] = photos
            _emote_delays[emote_id] = delays[:len(photos)]
            _emote_is_animated[emote_id] = bool(is_animated and len(photos) > 1)
            _emote_images[emote_id] = photos[0]
            _emote_lru[emote_id] = time.time()
            _emote_lru.move_to_end(emote_id)
            _evict_emote_cache()
        return photos[0]
    except Exception:
        return None


def download_emote(emote_id):
    try:
        if not emote_id or not re.search(r'^[a-zA-Z0-9_]+$', str(emote_id)):
            return None
        os.makedirs(EMOTE_CACHE_DIR, exist_ok=True)
        gif_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.gif")
        png_path = os.path.join(EMOTE_CACHE_DIR, f"{emote_id}.png")
        cache_abs = os.path.abspath(EMOTE_CACHE_DIR)
        for path in (gif_path, png_path):
            if not os.path.abspath(path).startswith(cache_abs):
                log_to_gui(f"[EMOTE] REJECT path traversal: {path}", "ERROR")
                return None
        if os.path.exists(gif_path):
            return gif_path
        if os.path.exists(png_path):
            return png_path
        TRUSTED_CDN = "static-cdn.jtvnw.net"
        animated_url = f"https://{TRUSTED_CDN}/emoticons/v2/{emote_id}/animated/dark/1.0"
        static_url = f"https://{TRUSTED_CDN}/emoticons/v2/{emote_id}/default/dark/1.0"
        for url, save_path in [(animated_url, gif_path), (static_url, png_path)]:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'TwitchOverlay/1.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    if not any(ct in content_type for ct in
                               ('image/gif', 'image/png', 'image/webp', 'image/jpeg')):
                        continue
                    data = resp.read(5 * 1024 * 1024)
                if len(data) > 100:
                    with open(save_path, 'wb') as f:
                        f.write(data)
                    return save_path
            except Exception:
                continue
        return None
    except Exception:
        return None


def split_message_with_emotes(message, emotes_list):
    try:
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
    except Exception:
        return [('text', message)]


def update_stats(username, message, tags):
    if not twitch_config["log_stats"] or twitch_config["test_mode"]:
        return
    try:
        user_hash = hash_user(username)
        stats["total_messages"] += 1
        if len(stats["unique_users_hashed"]) < MAX_STATS_USERS:
            stats["unique_users_hashed"].add(user_hash)
        key = datetime.now().strftime("%Y-%m-%d %H:%M")
        if len(stats["messages_per_minute"]) > 1440 * 7:
            old_keys = sorted(stats["messages_per_minute"].keys())[:100]
            for k in old_keys:
                stats["messages_per_minute"].pop(k, None)
        stats["messages_per_minute"][key] += 1
        if tags.get("mod") == "1":
            if len(stats["users_by_role"]["moderators"]) < MAX_STATS_USERS:
                stats["users_by_role"]["moderators"].add(user_hash)
        if tags.get("subscriber") == "1":
            if len(stats["users_by_role"]["subscribers"]) < MAX_STATS_USERS:
                stats["users_by_role"]["subscribers"].add(user_hash)
        if tags.get("vip") == "1":
            if len(stats["users_by_role"]["vips"]) < MAX_STATS_USERS:
                stats["users_by_role"]["vips"].add(user_hash)
        if tags.get("badges", "").startswith("broadcaster"):
            stats["users_by_role"]["broadcaster"].add(user_hash)
    except Exception:
        pass


def setup_irc_connection(channel):
    log_to_gui(t("log_connecting", host=TWITCH_HOST, port=TWITCH_PORT), "INFO")
    sock = socket.socket()
    sock.settimeout(30)
    try:
        sock.connect((TWITCH_HOST, TWITCH_PORT))
        sock.settimeout(None)
        sock.send(b"CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n")
        sock.send(f"NICK {ANON_NICK}\r\n".encode())
        sock.send(f"JOIN #{channel}\r\n".encode())
        log_to_gui(t("log_connected", ch=channel), "OK")
        return sock
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise


def close_sock(sock):
    if sock:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


def chat_loop(overlay: GhostOverlay):
    sock = None
    buffer = ""
    last_reconnect = 0
    last_stats_save = time.time()
    current_channel = None
    reconnect_count = 0
    consecutive_errors = 0
    stable_since = 0.0
    while not should_stop.is_set():
        try:
            try:
                cmd = chat_command.get(timeout=0.5)
            except queue.Empty:
                cmd = None
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
                        t("ov_disconnected", ch=current_channel),
                        '#FFAA00', style='warn')
                    log_to_gui(t("log_disconnected", ch=current_channel), "INFO")
                current_channel = None
                reconnect_count = 0
                consecutive_errors = 0
                stable_since = 0.0
                continue
            if cmd and cmd.startswith("CONNECT:"):
                new_channel = cmd[8:]
                if sock:
                    close_sock(sock)
                    sock = None
                current_channel = new_channel
                reconnect_count = 0
                consecutive_errors = 0
                stable_since = 0.0
                buffer = ""
                with connection_lock:
                    connection_state.update({
                        'connecting': True, 'connected': False,
                        'current_channel': current_channel,
                        'last_activity': time.time(),
                        'got_first_roomstate': False,
                    })
                overlay.clear()
                with _recent_user_msgs_lock:
                    _recent_user_msgs.clear()
                with _recent_chat_tail_lock:
                    _recent_chat_tail.clear()
                overlay.add_system_message(
                    t("ov_connecting", ch=current_channel),
                    '#FFFF00', style='info')
                continue
            if current_channel is None:
                time.sleep(0.3)
                continue
            if reconnect_count > 0 and stable_since and (time.time() - stable_since) > STABLE_RESET_SEC:
                log_to_gui(f"[IRC] Connection stable for {STABLE_RESET_SEC}s — reconnect counter reset", "INFO")
                reconnect_count = 0
            if sock is None:
                if reconnect_count >= twitch_config["max_reconnects"]:
                    overlay.add_system_message(
                        t("ov_too_many_recon"), '#FF4444', style='error')
                    log_to_gui(t("log_max_reconnects"), "ERROR")
                    with connection_lock:
                        connection_state['connecting'] = False
                        connection_state['connected'] = False
                    current_channel = None
                    continue
                wait = max(0, 3 - (time.time() - last_reconnect))
                if wait > 0:
                    time.sleep(wait)
                try:
                    sock = setup_irc_connection(current_channel)
                    last_reconnect = time.time()
                    reconnect_count += 1
                    stats["reconnects"] += 1
                    buffer = ""
                    consecutive_errors = 0
                    stable_since = time.time()
                    with connection_lock:
                        connection_state.update({
                            'connecting': False, 'connected': True,
                            'sock': sock, 'last_activity': time.time(),
                            'got_first_roomstate': False,
                        })
                    overlay.add_system_message(
                        t("ov_connected", ch=current_channel),
                        '#00FF00', style='connect')
                except Exception as e:
                    log_to_gui(t("log_conn_failed", e=e), "ERROR")
                    overlay.add_system_message(
                        t("ov_conn_error", e=e), '#FF4444', style='error')
                    last_reconnect = time.time()
                    time.sleep(2)
                    continue
            try:
                with connection_lock:
                    idle = time.time() - connection_state.get('last_activity', time.time())
                if idle > IRC_IDLE_TIMEOUT:
                    log_to_gui(f"[IRC] Idle for {idle:.0f}s — forcing reconnect", "WARN")
                    raise ConnectionError("idle timeout")
            except ConnectionError:
                raise
            except Exception:
                pass
            try:
                sock.settimeout(1)
                try:
                    data = sock.recv(4096).decode("utf-8", errors="replace")
                except socket.timeout:
                    continue
                except OSError as e:
                    raise ConnectionError(str(e))
                finally:
                    try:
                        sock.settimeout(None)
                    except Exception:
                        pass
                if not data:
                    raise ConnectionError("Server closed connection")
                buffer += data
                if len(buffer) > MAX_IRC_BUFFER:
                    idx = buffer.rfind("\r\n")
                    if idx != -1:
                        buffer = buffer[idx + 2:]
                    else:
                        buffer = ""
                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    if len(line) > MAX_IRC_LINE_LEN:
                        continue
                    parsed = parse_irc_line(line)
                    ptype = parsed['type']
                    try:
                        if ptype == 'ping':
                            try:
                                sock.send(b"PONG :tmi.twitch.tv\r\n")
                                stats["irc_pings"] += 1
                                with connection_lock:
                                    connection_state['last_activity'] = time.time()
                            except Exception:
                                pass
                        elif ptype == 'privmsg':
                            handle_privmsg(overlay, parsed)
                        elif ptype == 'usernotice':
                            handle_usernotice(overlay, parsed)
                        elif ptype == 'clearchat':
                            handle_clearchat(overlay, parsed)
                        elif ptype == 'clearmsg':
                            handle_clearmsg(overlay, parsed)
                        elif ptype == 'roomstate':
                            handle_roomstate(overlay, parsed)
                        elif ptype == 'notice':
                            handle_notice(overlay, parsed)
                        elif ptype == 'whisper':
                            handle_whisper(overlay, parsed)
                        elif ptype in ('join', 'part', 'userstate', 'globaluserstate',
                                        'cap', 'pong', 'hosttarget'):
                            pass
                        elif parsed['command'].isdigit():
                            pass
                        elif ptype == 'reconnect':
                            log_to_gui("[IRC] Server requested RECONNECT", "WARN")
                            try:
                                close_sock(sock)
                            except Exception:
                                pass
                            sock = None
                            with connection_lock:
                                connection_state['connected'] = False
                                connection_state['connecting'] = True
                            break
                        else:
                            log_to_gui(f"[IRC] Unhandled: {parsed['command']}", "WARN")
                    except Exception as e:
                        log_to_gui(f"[IRC] Handler error ({ptype}): {e}", "ERROR")
                        stats["errors"] += 1
                with connection_lock:
                    connection_state['last_activity'] = time.time()
                consecutive_errors = 0
                if time.time() - last_stats_save > 60:
                    save_stats_snapshot()
                    last_stats_save = time.time()
            except (ConnectionError, OSError) as e:
                consecutive_errors += 1
                log_to_gui(t("log_conn_lost", e=e), "WARN")
                if current_channel:
                    overlay.add_system_message(
                        t("ov_reconnecting"), '#FFFF00', style='warn')
                close_sock(sock)
                sock = None
                stable_since = 0.0
                with connection_lock:
                    connection_state['connected'] = False
                    connection_state['connecting'] = bool(current_channel)
                backoff = min(30, 2 ** min(consecutive_errors, 5))
                time.sleep(backoff)
            except Exception as e:
                consecutive_errors += 1
                log_to_gui(t("log_error", e=e), "ERROR")
                stats["errors"] += 1
                close_sock(sock)
                sock = None
                stable_since = 0.0
                with connection_lock:
                    connection_state['connected'] = False
                time.sleep(2)
        except Exception as e:
            try:
                log_to_gui(f"chat_loop outer error: {e}", "ERROR")
                tb = traceback.format_exc()
                with open(CRASH_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().isoformat()}] chat_loop\n{tb}\n")
            except Exception:
                pass
            time.sleep(1)
    close_sock(sock)
    with connection_lock:
        connection_state['connected'] = False
        connection_state['connecting'] = False


def validate_channel_name(name):
    try:
        if not name:
            return False, t("err_empty")
        name = name.lower().lstrip("#").strip()
        if len(name) < 3:
            return False, t("err_short")
        if len(name) > 25:
            return False, t("err_long")
        if not re.match(r"^[a-z0-9_]+$", name):
            return False, t("err_chars")
        return True, name
    except Exception:
        return False, t("err_empty")


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


def _dump_thread_stacks():
    try:
        frames = sys._current_frames()
    except Exception:
        return ""
    name_by_id = {}
    try:
        for th in threading.enumerate():
            if th.ident is not None:
                name_by_id[th.ident] = th.name
    except Exception:
        pass
    parts = []
    for tid, frame in frames.items():
        tname = name_by_id.get(tid, '?')
        parts.append(f"--- Thread {tid} ({tname}) ---")
        try:
            parts.append(''.join(traceback.format_stack(frame, limit=20)))
        except Exception:
            parts.append("<stack unavailable>\n")
    return '\n'.join(parts)


def _main_thread_watchdog_loop():
    stuck_reported = False
    while not should_stop.is_set():
        for _ in range(int(WATCHDOG_CHECK_EVERY * 10)):
            if should_stop.is_set():
                return
            time.sleep(0.1)
        try:
            delta = time.time() - _main_thread_heartbeat[0]
            if delta > MAIN_THREAD_STUCK_WARN:
                if not stuck_reported:
                    stuck_reported = True
                    log_to_gui(f"[WATCHDOG] Main thread unresponsive for {delta:.1f}s", "ERROR")
                    try:
                        dump = _dump_thread_stacks()
                        with open(CRASH_LOG_FILE, "a", encoding="utf-8") as f:
                            f.write(f"\n[{datetime.now().isoformat()}] "
                                    f"WATCHDOG HANG {delta:.1f}s\n{dump}\n")
                    except Exception:
                        pass
            else:
                if stuck_reported and delta < 5.0:
                    stuck_reported = False
                    log_to_gui(
                        f"[WATCHDOG] Main thread recovered (lag was {delta:.1f}s ago)",
                        "INFO")
        except Exception:
            pass


def _chat_loop_supervisor(overlay):
    while not should_stop.is_set():
        try:
            chat_loop(overlay)
        except Exception as e:
            try:
                tb = traceback.format_exc()
                log_to_gui(f"chat_loop crashed: {e}", "ERROR")
                with open(CRASH_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().isoformat()}] "
                            f"chat_loop supervisor\n{tb}\n")
            except Exception:
                pass
        if should_stop.is_set():
            break
        log_to_gui("ChatLoop restart in 3s...", "WARN")
        for _ in range(30):
            if should_stop.is_set():
                return
            time.sleep(0.1)


def _rotate_crash_log():
    try:
        if os.path.exists(CRASH_LOG_FILE) and os.path.getsize(CRASH_LOG_FILE) > CRASH_LOG_MAX_BYTES:
            try:
                if os.path.exists(CRASH_LOG_OLD):
                    os.remove(CRASH_LOG_OLD)
            except Exception:
                pass
            os.replace(CRASH_LOG_FILE, CRASH_LOG_OLD)
    except Exception:
        pass


def _cleanup_emote_disk_cache():
    try:
        if not os.path.isdir(EMOTE_CACHE_DIR):
            return
        cutoff = time.time() - ALERT_EMOTE_DISK_TTL
        removed = 0
        for name in os.listdir(EMOTE_CACHE_DIR):
            try:
                p = os.path.join(EMOTE_CACHE_DIR, name)
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    os.remove(p)
                    removed += 1
            except Exception:
                pass
        if removed:
            log_to_gui(f"[EMOTE] Removed {removed} stale cache files", "INFO")
    except Exception:
        pass


def parse_args():
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("channel", nargs="?", default=None)
        parser.add_argument("--help", "-h", action="store_true")
        parser.add_argument("--test", "-t", action="store_true")
        parser.add_argument("--supervisor-pid", type=int, default=None)
        return parser.parse_args()
    except Exception:
        class _FakeArgs:
            channel = None
            help = False
            test = False
            supervisor_pid = None
        return _FakeArgs()


def _watch_supervisor(supervisor_pid: int):
    while not should_stop.is_set():
        time.sleep(5)
        try:
            os.kill(supervisor_pid, 0)
        except OSError:
            log_to_gui("Supervisor gone → exiting", "WARN")
            should_stop.set()
            break
        except Exception:
            pass


def _setup_global_exception_handler(overlay_ref=None):
    def _handler(exc, val, tb):
        try:
            msg = ''.join(traceback.format_exception(exc, val, tb))
            log_to_gui(f"Uncaught: {val}", "ERROR")
            with open(CRASH_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now().isoformat()}]\n{msg}\n")
        except Exception:
            pass
    try:
        import tkinter
        tkinter.Tk.report_callback_exception = staticmethod(
            lambda exc, val, tb: _handler(exc, val, tb))
    except Exception:
        pass


def _start_background_services(overlay, args):
    _ensure_emote_download_workers()
    threading.Thread(
        target=_chat_loop_supervisor, args=(overlay,),
        name="ChatLoopSupervisor", daemon=True).start()
    log_to_gui(t("log_irc_ready"), "OK")
    threading.Thread(target=_heartbeat_loop, name="Heartbeat", daemon=True).start()
    threading.Thread(target=_main_thread_watchdog_loop,
                     name="MainThreadWatchdog", daemon=True).start()
    threading.Thread(target=_cleanup_emote_disk_cache,
                     name="EmoteDiskCleanup", daemon=True).start()
    if getattr(args, "supervisor_pid", None):
        threading.Thread(target=_watch_supervisor,
                         args=(args.supervisor_pid,),
                         name="SupervisorWatcher", daemon=True).start()
    if getattr(args, "channel", None):
        ok, result = validate_channel_name(args.channel)
        if ok:
            state = load_app_state()
            state['last_channel'] = result
            save_app_state(state)
            overlay.root.after(800, lambda: _safe_put(f"CONNECT:{result}"))


def _safe_put(cmd):
    try:
        chat_command.put_nowait(cmd)
    except queue.Full:
        pass


def run_overlay():
    global system_log_file
    args = parse_args()
    if args.test:
        twitch_config["test_mode"] = True
    _rotate_crash_log()
    load_alerts_config()
    load_filters_config()
    initial_state = load_app_state()
    saved_lang = initial_state.get('language', 'en')
    set_language(saved_lang)
    twitch_config['show_events'] = initial_state.get('show_events', True)
    twitch_config['auto_translate'] = initial_state.get('auto_translate', True)
    twitch_config['censor_enabled'] = initial_state.get('censor_enabled', True)
    _build_profanity_pattern()
    if not os.path.exists(APP_STATE_FILE):
        save_app_state(DEFAULT_APP_STATE)
    overlay_cfg = load_overlay_config()
    overlay = GhostOverlay(overlay_cfg)
    _setup_global_exception_handler(overlay)
    log_to_gui(t("log_started"), "OK")
    log_to_gui(t("log_overlay_created"), "OK")
    control_panel = ControlPanel(overlay)
    tray = TrayManager(overlay, control_panel)
    control_panel.tray_ref = tray
    tray.start()
    log_to_gui(t("log_tray_created"), "OK")
    overlay.root.after(200, control_panel.open)
    _start_background_services(overlay, args)
    try:
        overlay.run()
    except KeyboardInterrupt:
        pass
    finally:
        should_stop.set()
        try:
            chat_command.put_nowait("STOP")
        except Exception:
            pass
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
        try:
            _translate_pool.shutdown(wait=False)
        except Exception:
            pass
        log_to_gui("Overlay закрыт", "INFO")


if __name__ == "__main__":
    run_overlay()