"""
╔═══════════════════════════════════════════╗
║  config.py — Secure Configuration         ║
║  APON HOSTING PANEL v4.1                  ║
╚═══════════════════════════════════════════╝
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from threading import Lock

# ═══════════════════════════════════════════
#  SECURITY: Environment Variables
# ═══════════════════════════════════════════
TOKEN = os.getenv("BOT_TOKEN", "8258702948:AAHCT3iI934w6MnLle72GPUxQTR2O3z6aWA")
OWNER_ID = int(os.getenv("OWNER_ID", "6678577936"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "6678577936"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "apon_vps_bot")
YOUR_USERNAME = "@developer_apon"
UPDATE_CHANNEL = "https://t.me/developer_apon_07"

# ═══════════════════════════════════════════
#  BRANDING
# ═══════════════════════════════════════════
BRAND = "🌟 APON HOSTING PANEL"
BRAND_SHORT = "AHP"
BRAND_VER = "v4.1"
BRAND_TAG = f"{BRAND} {BRAND_VER}"

# ═══════════════════════════════════════════
#  PATHS
# ═══════════════════════════════════════════
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'upload_bots')
DATA_DIR = os.path.join(BASE_DIR, 'apon_data')
DB_PATH = os.path.join(DATA_DIR, 'apon.db')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

for _d in [UPLOAD_DIR, DATA_DIR, LOGS_DIR, BACKUP_DIR]:
    os.makedirs(_d, exist_ok=True)

# ═══════════════════════════════════════════
#  FORCE SUBSCRIBE
# ═══════════════════════════════════════════
DEFAULT_FORCE_CHANNELS = {'developer_apon_07': 'Developer Apon Updates'}
FORCE_SUB_ENABLED = True

# ═══════════════════════════════════════════
#  PLANS
# ═══════════════════════════════════════════
PLAN_LIMITS = {
    'free':       {'name': '🆓 Free',        'max_bots': 1,  'ram': 128,  'auto_restart': False, 'price': 0},
    'starter':    {'name': '🟢 Starter',     'max_bots': 2,  'ram': 256,  'auto_restart': True,  'price': 99},
    'basic':      {'name': '⭐ Basic',        'max_bots': 5,  'ram': 512,  'auto_restart': True,  'price': 199},
    'pro':        {'name': '💎 Pro',          'max_bots': 15, 'ram': 2048, 'auto_restart': True,  'price': 499},
    'enterprise': {'name': '🏢 Enterprise',   'max_bots': 50, 'ram': 4096, 'auto_restart': True,  'price': 999},
    'lifetime':   {'name': '👑 Lifetime',     'max_bots': -1, 'ram': 8192, 'auto_restart': True,  'price': 1999},
}

# ═══════════════════════════════════════════
#  PAYMENT METHODS
# ═══════════════════════════════════════════
PAYMENT_METHODS = {
    'bkash':   {'name': 'bKash',       'number': '01306633616',            'type': 'Send Money',       'icon': '🟪'},
    'nagad':   {'name': 'Nagad',       'number': '01306633616',            'type': 'Send Money',       'icon': '🟧'},
    'rocket':  {'name': 'Rocket',      'number': '01306633616',            'type': 'Send Money',       'icon': '🟦'},
    'upay':    {'name': 'Upay',        'number': '01306633616',            'type': 'Send Money',       'icon': '🟩'},
    'binance': {'name': 'Binance Pay', 'number': 'Binance ID: 758637628', 'type': 'Binance Pay/USDT', 'icon': '🟡'},
    'bank':    {'name': 'Bank',        'number': 'Contact Admin',          'type': 'Transfer',         'icon': '🏦'},
}

# ═══════════════════════════════════════════
#  REFERRAL
# ═══════════════════════════════════════════
REF_BONUS_DAYS = 3
REF_COMMISSION = 20

# ═══════════════════════════════════════════
#  MODULE MAP (auto-install)
# ═══════════════════════════════════════════
MODULES_MAP = {
    'telebot': 'pytelegrambotapi', 'telegram': 'python-telegram-bot',
    'pyrogram': 'pyrogram', 'telethon': 'telethon', 'aiogram': 'aiogram',
    'PIL': 'Pillow', 'cv2': 'opencv-python', 'sklearn': 'scikit-learn',
    'bs4': 'beautifulsoup4', 'dotenv': 'python-dotenv', 'yaml': 'pyyaml',
    'aiohttp': 'aiohttp', 'numpy': 'numpy', 'pandas': 'pandas',
    'requests': 'requests', 'flask': 'flask', 'fastapi': 'fastapi',
    'motor': 'motor', 'pymongo': 'pymongo', 'httpx': 'httpx',
    'cryptography': 'cryptography',
}

# ═══════════════════════════════════════════
#  THREAD LOCKS (THREAD SAFETY)
# ═══════════════════════════════════════════
bot_lock = Lock()
state_lock = Lock()
rate_lock = Lock()
active_lock = Lock()

# ═══════════════════════════════════════════
#  SHARED STATE (Thread-Safe Access Only)
# ═══════════════════════════════════════════
bot_scripts = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
user_states = {}
payment_states = {}

# ═══════════════════════════════════════════
#  LOGGING (with Rotation)
# ═══════════════════════════════════════════
def setup_logging():
    handler = RotatingFileHandler(
        os.path.join(LOGS_DIR, 'apon.log'),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    formatter = logging.Formatter('%(asctime)s|%(name)s|%(levelname)s|%(message)s')
    handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger('APON')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.addHandler(stream_handler)
    return logger

logger = setup_logging()