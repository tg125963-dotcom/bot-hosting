"""
╔═══════════════════════════════════════════╗
║  keyboards.py — All Keyboards             ║
║  APON HOSTING PANEL v4.1                  ║
╚═══════════════════════════════════════════╝
"""

from telebot import types
from config import (
    OWNER_ID, admin_ids, PLAN_LIMITS, PAYMENT_METHODS, FORCE_SUB_ENABLED
)
from database import db


def main_kb(uid):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.row("🤖 My Bots", "📤 Deploy Bot")
    m.row("💎 Subscription", "💰 Wallet")
    m.row("🎁 Referral", "📊 Statistics")
    m.row("🟢 Running Bots", "⚡ Speed Test")
    m.row("🔔 Notifications", "🎫 Support")
    if uid == OWNER_ID or uid in admin_ids:
        m.row("👑 Admin Panel", "📢 Broadcast")
        m.row("🔒 Lock Bot", "💳 Payments")
    m.row("⚙️ Settings", "📞 Contact")
    return m


def bot_action_kb(bid, st):
    m = types.InlineKeyboardMarkup(row_width=2)
    if st == 'running':
        m.add(
            types.InlineKeyboardButton("🛑 Stop", callback_data=f"stop:{bid}"),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f"restart:{bid}")
        )
        m.add(
            types.InlineKeyboardButton("📋 Logs", callback_data=f"logs:{bid}"),
            types.InlineKeyboardButton("📊 Resources", callback_data=f"res:{bid}")
        )
    else:
        m.add(
            types.InlineKeyboardButton("▶️ Start", callback_data=f"start:{bid}"),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f"del:{bid}")
        )
        m.add(
            types.InlineKeyboardButton("📥 Download", callback_data=f"dl:{bid}"),
            types.InlineKeyboardButton("📋 Logs", callback_data=f"logs:{bid}")
        )
        m.add(types.InlineKeyboardButton("🔍 Re-detect Entry", callback_data=f"redetect:{bid}"))
    m.add(types.InlineKeyboardButton("🔙 Back to Bots", callback_data="mybots"))
    return m


def plan_kb():
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, p in PLAN_LIMITS.items():
        if k == 'free':
            continue
        m.add(types.InlineKeyboardButton(
            f"{p['name']} — {p['price']} BDT/mo",
            callback_data=f"plan:{k}"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu"))
    return m


def pay_method_kb(pk):
    m = types.InlineKeyboardMarkup(row_width=2)
    for k, v in PAYMENT_METHODS.items():
        m.add(types.InlineKeyboardButton(
            f"{v['icon']} {v['name']}",
            callback_data=f"pay:{pk}:{k}"))
    m.add(types.InlineKeyboardButton("💰 Pay from Wallet", callback_data=f"payw:{pk}"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="sub"))
    return m


def admin_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("👥 Users", callback_data="a_users"),
        types.InlineKeyboardButton("📊 Stats", callback_data="a_stats")
    )
    m.add(
        types.InlineKeyboardButton("💳 Payments", callback_data="a_pay"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="a_bc")
    )
    m.add(
        types.InlineKeyboardButton("➕ Add Sub", callback_data="a_addsub"),
        types.InlineKeyboardButton("➖ Remove Sub", callback_data="a_remsub")
    )
    m.add(
        types.InlineKeyboardButton("🚫 Ban", callback_data="a_ban"),
        types.InlineKeyboardButton("✅ Unban", callback_data="a_unban")
    )
    m.add(
        types.InlineKeyboardButton("📢 Channels", callback_data="a_channels"),
        types.InlineKeyboardButton("🎟 Promo", callback_data="a_promo")
    )
    m.add(
        types.InlineKeyboardButton("🎫 Tickets", callback_data="a_tickets"),
        types.InlineKeyboardButton("🖥 System", callback_data="a_sys")
    )
    m.add(
        types.InlineKeyboardButton("🛑 Stop All", callback_data="a_stopall"),
        types.InlineKeyboardButton("💾 Backup", callback_data="a_backup")
    )
    fsub_status = "🟢" if FORCE_SUB_ENABLED else "🔴"
    m.add(types.InlineKeyboardButton(f"{fsub_status} Force Subscribe", callback_data="a_fsub_toggle"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu"))
    return m


def pay_approve_kb(pid):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"appv:{pid}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"rejt:{pid}")
    )
    return m


def force_sub_kb(not_joined):
    m = types.InlineKeyboardMarkup(row_width=1)
    for cu, cn in not_joined:
        m.add(types.InlineKeyboardButton(f"📢 Join {cn}", url=f"https://t.me/{cu}"))
    m.add(types.InlineKeyboardButton("✅ Verify Joined", callback_data="verify_join"))
    return m


def channels_kb():
    channels = db.get_all_channels()
    m = types.InlineKeyboardMarkup(row_width=1)
    if channels:
        for ch in channels:
            status = "🟢" if ch['is_active'] else "🔴"
            m.add(types.InlineKeyboardButton(
                f"{status} @{ch['channel_username']} — {ch['channel_name']}",
                callback_data=f"ch_toggle:{ch['channel_id']}"))
    else:
        m.add(types.InlineKeyboardButton("📭 No channels added", callback_data="none"))
    m.add(types.InlineKeyboardButton("➕ Add Channel", callback_data="ch_add"))
    m.add(types.InlineKeyboardButton("🗑 Remove Channel", callback_data="ch_remove"))
    m.add(types.InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back"))
    return m