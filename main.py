"""
╔═══════════════════════════════════════════════════════════╗
║  🌟 APON HOSTING PANEL — Premium Edition v4.1 🌟         ║
║  Developer: @developer_apon                               ║
║  Production-Ready | Thread-Safe | Auto-Recovery           ║
╚═══════════════════════════════════════════════════════════╝
"""

import time
import atexit
import requests
import telebot

from config import (
    TOKEN, OWNER_ID, BRAND, BRAND_VER, BRAND_TAG, BRAND_SHORT,
    logger, bot_lock, bot_scripts, admin_ids,
    DEFAULT_FORCE_CHANNELS, FORCE_SUB_ENABLED
)
from database import db
from utils import (
    set_bot_instance, safe_send, gen_ref_code,
    is_running, kill_tree, get_uptime, report_error
)
from runner import start_all_threads
from handlers import register_handlers
from callbacks import register_callbacks

# ═══════════════════════════════════════════
#  CREATE BOT INSTANCE
# ═══════════════════════════════════════════
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')
set_bot_instance(bot)

# ═══════════════════════════════════════════
#  FLASK KEEP-ALIVE
# ═══════════════════════════════════════════
from flask import Flask, jsonify
from threading import Thread
import os

flask_app = Flask('AponHosting')

@flask_app.route('/')
def flask_home():
    return "<h1>🌟 APON HOSTING PANEL 🌟</h1><p>Status: ✅ Online</p>"

@flask_app.route('/health')
def flask_health():
    return jsonify({"status": "ok", "uptime": get_uptime(), "v": "4.1"})

def keep_alive():
    Thread(
        target=lambda: flask_app.run(
            host='0.0.0.0',
            port=int(os.environ.get("PORT", 8080))
        ),
        daemon=True
    ).start()

# ═══════════════════════════════════════════
#  CLEANUP ON EXIT
# ═══════════════════════════════════════════
def cleanup_all():
    logger.info("🛑 Shutting down...")
    count = 0
    with bot_lock:
        keys = list(bot_scripts.keys())
    for sk in keys:
        try:
            with bot_lock:
                info = bot_scripts.get(sk)
            if info:
                kill_tree(info)
                count += 1
        except:
            pass
    logger.info(f"🛑 Stopped {count} bots")

atexit.register(cleanup_all)

# ═══════════════════════════════════════════
#  REGISTER ALL HANDLERS
# ═══════════════════════════════════════════
register_handlers(bot)
register_callbacks(bot)

# ═══════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════
def main():
    logger.info("=" * 50)
    logger.info(f"  {BRAND} {BRAND_VER}")
    logger.info(f"  Production Mode | Thread-Safe | Auto-Recovery")
    logger.info("=" * 50)

    # Seed default channels
    existing_channels = db.get_all_channels()
    if not existing_channels:
        for ch_user, ch_name in DEFAULT_FORCE_CHANNELS.items():
            db.add_channel(ch_user, ch_name, OWNER_ID)

    # Fix referral codes
    fixed = 0
    for u in db.get_all_users():
        rc = u.get('referral_code', '')
        if not rc or len(rc) < 5:
            try:
                db.update_user(u['user_id'], referral_code=gen_ref_code(u['user_id']))
                fixed += 1
            except:
                pass
    if fixed:
        logger.info(f"🔧 Fixed {fixed} referral codes")

    # Start background threads
    start_all_threads()

    # Flask keep-alive
    keep_alive()

    # Notify admins
    stats = db.stats()
    for aid in admin_ids:
        safe_send(aid,
            f"🚀 <b>{BRAND_SHORT} STARTED!</b>\n"
            f"{BRAND_TAG}\n━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ All systems online\n"
            f"🧵 4 background threads\n"
            f"🔒 Thread-safe mode\n"
            f"👥 Users: {stats['users']}\n"
            f"🤖 Bots: {stats['bots']}\n"
            f"💰 Revenue: {stats['revenue']} BDT\n"
            f"Force Sub: {'🟢 ON' if FORCE_SUB_ENABLED else '🔴 OFF'}\n"
            f"━━━━━━━━━━━━━━━━━━━━")

    logger.info("🟢 Bot READY! Starting polling...")

    # ═══════════════════════════════════════
    #  AUTO-RECOVERY POLLING LOOP
    # ═══════════════════════════════════════
    while True:
        try:
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=30,
                allowed_updates=["message", "callback_query"]
            )
        except requests.exceptions.ConnectionError:
            logger.error("🔴 Connection error! Retry 10s...")
            report_error("Connection lost", "polling")
            time.sleep(10)
        except requests.exceptions.ReadTimeout:
            logger.error("🔴 Timeout! Retry 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("🛑 KeyboardInterrupt — stopping...")
            break
        except Exception as e:
            logger.error(f"🔴 Fatal: {e}", exc_info=True)
            report_error(e, "polling_loop")
            time.sleep(5)


if __name__ == "__main__":
    main()