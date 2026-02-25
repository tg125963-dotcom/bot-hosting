"""
╔═══════════════════════════════════════════╗
║  handlers.py — All Message Handlers       ║
║  APON HOSTING PANEL v4.1                  ║
╚═══════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import shutil
import zipfile
import tempfile
import threading
from datetime import datetime
from telebot import types

from config import (
    logger, OWNER_ID, admin_ids, PLAN_LIMITS, PAYMENT_METHODS,
    BRAND, BRAND_VER, BRAND_TAG, BRAND_SHORT, BOT_USERNAME,
    YOUR_USERNAME, UPDATE_CHANNEL, REF_COMMISSION, REF_BONUS_DAYS,
    FORCE_SUB_ENABLED, DEFAULT_FORCE_CHANNELS,
    bot_lock, state_lock, active_lock,
    bot_scripts, active_users, user_states, payment_states, bot_locked
)
from database import db
from utils import (
    safe_send, safe_edit, safe_answer, rate_check,
    get_uptime, fmt_size, gen_ref_code, time_left,
    user_folder, is_running, bot_running, bot_res,
    sys_stats, check_joined, det, report_error,
    cleanup_script, kill_tree
)
from keyboards import (
    main_kb, bot_action_kb, plan_kb, pay_method_kb,
    admin_kb, pay_approve_kb, force_sub_kb, channels_kb
)
from runner import run_bot, run_broadcast_thread


# ═══════════════════════════════════════════
#  FORCE SUBSCRIBE MESSAGE
# ═══════════════════════════════════════════
def send_force_sub(cid, nj):
    ch = ""
    for i, (cu, cn) in enumerate(nj, 1):
        ch += f"  {i}. {cn} — @{cu}\n"
    safe_send(cid,
        f"🔒 <b>CHANNEL VERIFICATION</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Join our channels to continue!\n\n"
        f"{ch}\n👇 Join all, then press Verify\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=force_sub_kb(nj))


# ═══════════════════════════════════════════
#  REGISTER HANDLERS
# ═══════════════════════════════════════════
def register_handlers(bot):
    """Register all handlers with bot instance"""

    # ──────────────────────────────
    #  /START
    # ──────────────────────────────
    @bot.message_handler(commands=['start'])
    def cmd_start(msg):
        uid = msg.from_user.id
        un = msg.from_user.username or ''
        fn = f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip()

        with active_lock:
            active_users.add(uid)

        joined, nj = check_joined(uid)
        if not joined:
            send_force_sub(msg.chat.id, nj)
            return

        ex = db.get_user(uid)
        if ex and ex['is_banned']:
            return bot.reply_to(msg, f"🚫 Banned: {ex.get('ban_reason', '')}")
        if bot_locked and uid not in admin_ids and uid != OWNER_ID:
            return bot.reply_to(msg, "🔒 Bot is in maintenance mode.")

        is_new = ex is None
        ref_by = None
        args = msg.text.split()

        if len(args) > 1:
            rc = args[1].strip()
            rr = db.exe("SELECT user_id FROM users WHERE referral_code=?", (rc,), one=True)
            if rr and rr['user_id'] != uid and is_new:
                ref_by = rr['user_id']

        code = gen_ref_code(uid)

        if is_new:
            db.create_user(uid, un, fn, code, ref_by)
            if ref_by:
                db.add_ref(ref_by, uid, REF_BONUS_DAYS, REF_COMMISSION)
                rd = db.get_user(ref_by)
                safe_send(ref_by,
                    f"🎉 <b>NEW REFERRAL!</b>\n\n"
                    f"👤 {fn} joined via your link!\n"
                    f"💰 +{REF_COMMISSION} BDT added!\n"
                    f"📅 +{REF_BONUS_DAYS} days bonus!\n"
                    f"👥 Total: {rd['referral_count'] if rd else '?'}")
        else:
            db.update_user(uid, username=un, full_name=fn, last_active=datetime.now().isoformat())
            if not ex.get('referral_code') or len(ex.get('referral_code', '')) < 5:
                db.update_user(uid, referral_code=code)

        u = db.get_user(uid)
        pl = PLAN_LIMITS.get(u['plan'], PLAN_LIMITS['free']) if u else PLAN_LIMITS['free']
        bc = db.bot_count(uid)
        mx = '♾️' if pl['max_bots'] == -1 else str(pl['max_bots'])
        st = '👑 Owner' if uid == OWNER_ID else '⭐ Admin' if uid in admin_ids else pl['name']

        notif_count = db.unread_count(uid)
        notif_text = f"\n🔔 {notif_count} unread notifications" if notif_count > 0 else ""

        w = (
            f"🌟 <b>APON HOSTING PANEL</b> {BRAND_VER}\n"
            f"<i>Premium Bot Hosting Platform</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👋 Welcome, <b>{fn}</b>!\n\n"
            f"📤 Deploy &amp; Host your bots\n"
            f"🚀 Python &amp; Node.js support\n"
            f"🔍 Smart Entry Detection\n"
            f"💳 bKash / Nagad / Binance\n"
            f"🎁 Earn with Referrals\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <code>{uid}</code>\n📦 {st}\n"
            f"🤖 Bots: {bc}/{mx}\n"
            f"💰 {u['wallet_balance'] if u else 0} BDT\n"
            f"👥 {u['referral_count'] if u else 0} referrals\n"
            f"🔑 <code>{u['referral_code'] if u else code}</code>"
            f"{notif_text}\n━━━━━━━━━━━━━━━━━━━━"
        )
        safe_send(msg.chat.id, w)
        safe_send(msg.chat.id, "⬇️ Choose an option:", reply_markup=main_kb(uid))

    # ──────────────────────────────
    #  /HELP
    # ──────────────────────────────
    @bot.message_handler(commands=['help'])
    def cmd_help(msg):
        safe_send(msg.chat.id,
            f"📚 <b>HELP CENTER</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📤 <b>Deploy:</b> Send ZIP / .py / .js\n"
            f"🔍 <b>Detection:</b> Auto-finds entry file\n"
            f"🤖 <b>Control:</b> Start/Stop/Restart/Logs\n"
            f"💎 <b>Plans:</b> Free → Lifetime\n"
            f"💳 <b>Pay:</b> bKash/Nagad/Binance\n"
            f"🎁 <b>Refer:</b> Earn {REF_COMMISSION} BDT per ref\n"
            f"🎫 <b>Support:</b> Create ticket\n"
            f"👑 <b>Admin:</b> /admin\n"
            f"📞 <b>Contact:</b> {YOUR_USERNAME}\n\n{BRAND_TAG}")

    # ──────────────────────────────
    #  /ADMIN
    # ──────────────────────────────
    @bot.message_handler(commands=['admin'])
    def cmd_admin_cmd(msg):
        show_admin(msg)

    # ──────────────────────────────
    #  /ID, /PING
    # ──────────────────────────────
    @bot.message_handler(commands=['id'])
    def cmd_id(msg):
        uid = msg.from_user.id
        safe_send(msg.chat.id,
            f"🆔 <b>Your Info</b>\n\n"
            f"👤 ID: <code>{uid}</code>\n"
            f"📛 Name: {msg.from_user.first_name or ''} {msg.from_user.last_name or ''}\n"
            f"👤 Username: @{msg.from_user.username or 'N/A'}\n\n{BRAND_TAG}")

    @bot.message_handler(commands=['ping'])
    def cmd_ping(msg):
        start = time.time()
        m = bot.reply_to(msg, "🏓 Pinging...")
        latency = round((time.time() - start) * 1000, 2)
        with bot_lock:
            rn = len([k for k in bot_scripts if is_running(k)])
        safe_edit(
            f"🏓 <b>Pong!</b>\n\n⚡ Latency: {latency}ms\n"
            f"⏱️ Uptime: {get_uptime()}\n🤖 Running: {rn} bots\n\n{BRAND_TAG}",
            msg.chat.id, m.message_id)

    # ──────────────────────────────
    #  ADMIN COMMANDS
    # ──────────────────────────────
    @bot.message_handler(commands=['reply'])
    def cmd_reply_ticket(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 3:
            return bot.reply_to(msg, "Usage: /reply TICKET_ID MESSAGE")
        try:
            tid = int(parts[1])
            reply_text = parts[2]
            ticket = db.exe("SELECT * FROM tickets WHERE ticket_id=?", (tid,), one=True)
            if not ticket:
                return bot.reply_to(msg, f"❌ Ticket #{tid} not found!")
            db.reply_ticket(tid, reply_text)
            bot.reply_to(msg, f"✅ Replied to ticket #{tid}")
            safe_send(ticket['user_id'], f"📩 <b>Ticket #{tid} — Admin Reply</b>\n\n💬 {reply_text}\n\n{BRAND_TAG}")
        except ValueError:
            bot.reply_to(msg, "❌ Invalid ticket ID!")

    @bot.message_handler(commands=['subscribe'])
    def cmd_sub_admin(msg):
        if msg.from_user.id not in admin_ids and msg.from_user.id != OWNER_ID:
            return
        p = msg.text.split()
        if len(p) < 3:
            return bot.reply_to(msg, "/subscribe UID DAYS")
        try:
            db.set_sub(int(p[1]), 'pro' if int(p[2]) > 0 else 'lifetime', int(p[2]))
            bot.reply_to(msg, "✅ Done")
        except:
            bot.reply_to(msg, "❌ Error")

    @bot.message_handler(commands=['ban'])
    def cmd_ban(msg):
        if msg.from_user.id not in admin_ids and msg.from_user.id != OWNER_ID:
            return
        p = msg.text.split(maxsplit=2)
        if len(p) < 2:
            return
        try:
            db.ban(int(p[1]), p[2] if len(p) > 2 else "Banned")
            bot.reply_to(msg, "🚫 Banned")
        except:
            pass

    @bot.message_handler(commands=['unban'])
    def cmd_unban(msg):
        if msg.from_user.id not in admin_ids and msg.from_user.id != OWNER_ID:
            return
        try:
            db.unban(int(msg.text.split()[1]))
            bot.reply_to(msg, "✅ Unbanned")
        except:
            pass

    @bot.message_handler(commands=['addchannel'])
    def cmd_add_channel(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 2:
            return bot.reply_to(msg, "Usage: /addchannel @username Channel Name")
        ch_username = parts[1].lstrip('@').lower()
        ch_name = parts[2] if len(parts) > 2 else ch_username
        try:
            chat_info = bot.get_chat(f"@{ch_username}")
            ch_name = chat_info.title or ch_name
        except:
            pass
        db.add_channel(ch_username, ch_name, uid)
        db.admin_log(uid, 'add_channel', details=f"@{ch_username}")
        bot.reply_to(msg, f"✅ Channel @{ch_username} added!\n⚠️ Make sure bot is admin!")

    @bot.message_handler(commands=['removechannel', 'rmchannel'])
    def cmd_remove_channel(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            return bot.reply_to(msg, "Usage: /removechannel @username")
        db.remove_channel(parts[1].lstrip('@').lower())
        bot.reply_to(msg, "✅ Removed!")

    @bot.message_handler(commands=['channels'])
    def cmd_channels(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        channels = db.get_all_channels()
        t = f"📢 <b>Force Subscribe Channels</b>\nStatus: {'🟢 ON' if FORCE_SUB_ENABLED else '🔴 OFF'}\n\n"
        if channels:
            for ch in channels:
                st = "🟢" if ch['is_active'] else "🔴"
                t += f"{st} @{ch['channel_username']} — {ch['channel_name']}\n"
        else:
            t += "No channels. Default: @developer_apon_07\n"
        safe_send(uid, t)

    @bot.message_handler(commands=['broadcast', 'bc'])
    def cmd_broadcast(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        text = msg.text.split(maxsplit=1)
        if len(text) < 2:
            with state_lock:
                user_states[uid] = {'action': 'broadcast'}
            return bot.reply_to(msg, "📢 Send broadcast message:")
        # Background broadcast
        threading.Thread(
            target=run_broadcast_thread,
            args=(text[1], uid),
            daemon=True
        ).start()
        bot.reply_to(msg, "📢 Broadcasting in background...")

    @bot.message_handler(commands=['userinfo'])
    def cmd_userinfo(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        parts = msg.text.split()
        if len(parts) < 2:
            return bot.reply_to(msg, "Usage: /userinfo USER_ID")
        try:
            target = int(parts[1])
            u = db.get_user(target)
            if not u:
                return bot.reply_to(msg, f"❌ User {target} not found!")
            pl = PLAN_LIMITS.get(u['plan'], PLAN_LIMITS['free'])
            bc = db.bot_count(target)
            bots_list = db.get_bots(target)
            running = sum(1 for b in bots_list if bot_running(target, b['bot_name']))
            safe_send(uid,
                f"👤 <b>User Info</b>\n\n"
                f"🆔 ID: <code>{target}</code>\n📛 Name: {u['full_name']}\n"
                f"👤 @{u['username'] or 'N/A'}\n"
                f"🚫 Banned: {'Yes — ' + u['ban_reason'] if u['is_banned'] else 'No'}\n\n"
                f"📦 Plan: {pl['name']}\n📅 Expires: {time_left(u['subscription_end'])}\n"
                f"👑 Lifetime: {'Yes' if u['is_lifetime'] else 'No'}\n\n"
                f"🤖 Bots: {bc} (🟢 {running})\n💰 Wallet: {u['wallet_balance']} BDT\n"
                f"💳 Spent: {u['total_spent']} BDT\n\n"
                f"👥 Refs: {u['referral_count']}\n🔑 Code: <code>{u['referral_code']}</code>\n"
                f"📅 Joined: {u['created_at'][:16] if u.get('created_at') else '?'}")
        except ValueError:
            bot.reply_to(msg, "❌ Invalid user ID!")

    @bot.message_handler(commands=['stopbot'])
    def cmd_stopbot(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        parts = msg.text.split()
        if len(parts) < 2:
            return bot.reply_to(msg, "Usage: /stopbot BOT_ID")
        try:
            bid = int(parts[1])
            bd = db.get_bot(bid)
            if not bd:
                return bot.reply_to(msg, "❌ Bot not found!")
            sk = f"{bd['user_id']}_{bd['bot_name']}"
            with bot_lock:
                info = bot_scripts.get(sk)
            if info:
                kill_tree(info)
                cleanup_script(sk)
            db.update_bot(bid, status='stopped')
            bot.reply_to(msg, f"✅ Stopped bot #{bid}")
        except:
            bot.reply_to(msg, "❌ Error!")

    @bot.message_handler(commands=['give'])
    def cmd_give(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        parts = msg.text.split()
        if len(parts) < 3:
            return bot.reply_to(msg, "Usage: /give USER_ID AMOUNT")
        try:
            target = int(parts[1])
            amount = float(parts[2])
            u = db.get_user(target)
            if not u:
                return bot.reply_to(msg, f"❌ User {target} not found!")
            db.wallet_tx(target, amount, 'bonus', f"Admin bonus by {uid}")
            bot.reply_to(msg, f"✅ Gave {amount} BDT to <code>{target}</code>", parse_mode='HTML')
            safe_send(target, f"🎁 <b>Bonus!</b>\n💰 +{amount} BDT added!\n\n{BRAND_TAG}")
        except:
            bot.reply_to(msg, "❌ Error!")

    @bot.message_handler(commands=['notify'])
    def cmd_notify(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 3:
            return bot.reply_to(msg, "Usage: /notify USER_ID MESSAGE")
        try:
            target = int(parts[1])
            text = parts[2]
            db.add_notif(target, "Admin Notice", text)
            bot.reply_to(msg, f"✅ Sent to <code>{target}</code>", parse_mode='HTML')
            safe_send(target, f"🔔 <b>Notification</b>\n\n{text}\n\n{BRAND_TAG}")
        except:
            bot.reply_to(msg, "❌ Error!")

    # ──────────────────────────────
    #  TEXT HANDLER
    # ──────────────────────────────
    @bot.message_handler(content_types=['text'])
    def handle_text(msg):
        uid = msg.from_user.id
        txt = msg.text

        with active_lock:
            active_users.add(uid)

        if not rate_check(uid):
            return

        joined, nj = check_joined(uid)
        if not joined:
            send_force_sub(msg.chat.id, nj)
            return

        u = db.get_user(uid)
        if u and u['is_banned']:
            return
        if bot_locked and uid not in admin_ids and uid != OWNER_ID:
            return bot.reply_to(msg, "🔒 Maintenance mode")

        with state_lock:
            has_pay = uid in payment_states
            has_state = uid in user_states

        if has_pay:
            return handle_pay_text(msg)
        if has_state:
            return handle_state(msg)

        handlers_map = {
            "🤖 My Bots": lambda m: show_bots(m),
            "📤 Deploy Bot": lambda m: show_deploy(m),
            "💎 Subscription": lambda m: show_sub(m),
            "💰 Wallet": lambda m: show_wallet(m),
            "🎁 Referral": lambda m: show_ref(m),
            "📊 Statistics": lambda m: show_stats(m),
            "🟢 Running Bots": lambda m: show_running(m),
            "⚡ Speed Test": lambda m: show_speed(m),
            "🔔 Notifications": lambda m: show_notifs(m),
            "🎫 Support": lambda m: show_support(m),
            "👑 Admin Panel": lambda m: show_admin(m),
            "📢 Broadcast": lambda m: do_broadcast(m),
            "🔒 Lock Bot": lambda m: do_lock(m),
            "💳 Payments": lambda m: show_payments(m),
            "⚙️ Settings": lambda m: show_settings(m),
        }

        if txt in handlers_map:
            handlers_map[txt](msg)
        elif txt == "📞 Contact":
            safe_send(uid, f"📞 {YOUR_USERNAME}\n📢 {UPDATE_CHANNEL}\n\n{BRAND_TAG}")
        else:
            safe_send(uid, "❓ Use the buttons below ⬇️", reply_markup=main_kb(uid))

    # ──────────────────────────────
    #  DOCUMENT HANDLER
    # ──────────────────────────────
    @bot.message_handler(content_types=['document'])
    def handle_doc(msg):
        uid = msg.from_user.id

        joined, nj = check_joined(uid)
        if not joined:
            send_force_sub(msg.chat.id, nj)
            return

        u = db.get_user(uid)
        if not u:
            return bot.reply_to(msg, "Please /start first!")
        if u['is_banned']:
            return

        pl = db.get_plan(uid)
        cur = db.bot_count(uid)
        mx = pl['max_bots']
        if mx != -1 and cur >= mx:
            return bot.reply_to(msg, f"❌ Bot limit reached ({cur}/{mx})! Upgrade your plan.")

        fn = msg.document.file_name
        fs = msg.document.file_size
        ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''

        allowed = ['py', 'js', 'zip', 'json', 'txt', 'env', 'yml', 'yaml', 'cfg', 'ini', 'toml']
        if ext not in allowed:
            return bot.reply_to(msg, f"❌ Unsupported file type: .{ext}")

        if fs > 100 * 1024 * 1024:
            return bot.reply_to(msg, "❌ File too large! Max 100MB.")

        pm = bot.reply_to(msg, f"📤 Uploading {fn[:25]} ({fmt_size(fs)})...")

        try:
            fi = bot.get_file(msg.document.file_id)
            dl = bot.download_file(fi.file_path)
            uf = user_folder(uid)

            if ext == 'zip':
                _handle_zip(msg, uid, fn, fs, dl, uf, pm)
            elif ext in ['py', 'js']:
                _handle_script(msg, uid, fn, fs, dl, uf, ext, pm)
            else:
                file_path = os.path.join(uf, fn)
                with open(file_path, 'wb') as f:
                    f.write(dl)
                safe_edit(f"✅ Config file {fn} saved!", msg.chat.id, pm.message_id)

        except Exception as e:
            logger.error(f"Upload error: {e}", exc_info=True)
            report_error(e, "handle_doc")
            safe_edit(f"❌ Error: {str(e)[:100]}", msg.chat.id, pm.message_id)

    # ── ZIP Handler ──
    def _handle_zip(msg, uid, fn, fs, dl, uf, pm):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp.write(dl)
            tp = tmp.name

        try:
            with zipfile.ZipFile(tp, 'r') as z:
                for n in z.namelist():
                    if n.startswith('/') or '..' in n:
                        safe_edit("❌ Suspicious file paths!", msg.chat.id, pm.message_id)
                        os.unlink(tp)
                        return

                bn = fn.replace('.zip', '').replace(' ', '_')
                ed = os.path.join(uf, bn)
                if os.path.exists(ed):
                    shutil.rmtree(ed, ignore_errors=True)
                os.makedirs(ed, exist_ok=True)
                z.extractall(ed)

                # Handle single root folder
                items = os.listdir(ed)
                if len(items) == 1 and os.path.isdir(os.path.join(ed, items[0])):
                    inner = os.path.join(ed, items[0])
                    for item in os.listdir(inner):
                        src = os.path.join(inner, item)
                        dst = os.path.join(ed, item)
                        if os.path.exists(dst):
                            if os.path.isdir(dst):
                                shutil.rmtree(dst)
                            else:
                                os.remove(dst)
                        shutil.move(src, dst)
                    try:
                        os.rmdir(inner)
                    except:
                        pass

            os.unlink(tp)

            entry, ft, report = det.report(ed)
            if not entry:
                af = []
                for r, d, fs_list in os.walk(ed):
                    for f in fs_list:
                        if f.endswith(('.py', '.js')):
                            af.append(os.path.relpath(os.path.join(r, f), ed))
                err_text = f"❌ <b>No entry file detected!</b>\n\nFiles in ZIP:\n"
                for f in af[:15]:
                    err_text += f"• {f}\n"
                if not af:
                    err_text += "(No .py or .js files)\n"
                err_text += "\nMake sure ZIP has app.py, main.py, or bot.py"
                safe_edit(err_text, msg.chat.id, pm.message_id)
                return

            bid = db.add_bot(uid, bn, ed, entry, ft, '', fs, '')
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(
                types.InlineKeyboardButton("▶️ Start Now", callback_data=f"start:{bid}"),
                types.InlineKeyboardButton("🤖 My Bots", callback_data="mybots")
            )
            mk.add(types.InlineKeyboardButton("🔍 Re-detect", callback_data=f"redetect:{bid}"))

            safe_edit(
                f"✅ <b>ZIP DEPLOYED!</b>\n\n"
                f"📦 {bn[:20]}\n🆔 Bot ID: #{bid}\n\n"
                f"🔍 Detection:\n{report}",
                msg.chat.id, pm.message_id, reply_markup=mk)

        except zipfile.BadZipFile:
            safe_edit("❌ Invalid or corrupted ZIP file!", msg.chat.id, pm.message_id)
            try:
                os.unlink(tp)
            except:
                pass

    # ── Script Handler ──
    def _handle_script(msg, uid, fn, fs, dl, uf, ext, pm):
        file_path = os.path.join(uf, fn)
        with open(file_path, 'wb') as f:
            f.write(dl)

        bid = db.add_bot(uid, fn, uf, fn, ext, '', fs, 'exact')
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(
            types.InlineKeyboardButton("▶️ Run Now", callback_data=f"start:{bid}"),
            types.InlineKeyboardButton("🤖 My Bots", callback_data="mybots")
        )
        safe_edit(
            f"✅ <b>FILE UPLOADED!</b>\n\n"
            f"📄 {fn[:25]}\n🆔 Bot ID: #{bid}\n"
            f"🔤 {'🐍 Python' if ext == 'py' else '🟨 Node.js'}\n📊 {fmt_size(fs)}",
            msg.chat.id, pm.message_id, reply_markup=mk)

    # ──────────────────────────────
    #  SHOW FUNCTIONS
    # ──────────────────────────────
    def show_bots(msg):
        uid = msg.from_user.id
        bots_list = db.get_bots(uid)
        pl = db.get_plan(uid)
        mx = '♾️' if pl['max_bots'] == -1 else str(pl['max_bots'])
        if not bots_list:
            safe_send(msg.chat.id, f"📭 <b>No bots yet!</b>\nDeploy with 📤\n📦 Slots: 0/{mx}\n\n{BRAND_TAG}")
            return
        rn = sum(1 for b in bots_list if bot_running(uid, b['bot_name']))
        t = f"🤖 <b>My Bots</b> ({len(bots_list)}) | 🟢 {rn} | 🔴 {len(bots_list) - rn}\n📦 Limit: {mx}\n\n"
        m = types.InlineKeyboardMarkup(row_width=1)
        for b in bots_list:
            r = bot_running(uid, b['bot_name'])
            ic = "🐍" if b['file_type'] == 'py' else "🟨"
            st_icon = "🟢" if r else "🔴"
            t += f"{st_icon} {ic} {b['bot_name'][:20]} #{b['bot_id']} — {b['entry_file']}\n"
            m.add(types.InlineKeyboardButton(
                f"{st_icon} {b['bot_name'][:15]} #{b['bot_id']}",
                callback_data=f"detail:{b['bot_id']}"))
        m.add(types.InlineKeyboardButton("📤 Deploy New", callback_data="deploy"))
        safe_send(msg.chat.id, t, reply_markup=m)

    def show_deploy(msg):
        uid = msg.from_user.id
        u = db.get_user(uid)
        if not u:
            return bot.reply_to(msg, "/start first!")
        pl = db.get_plan(uid)
        cur = db.bot_count(uid)
        mx = pl['max_bots']
        if mx != -1 and cur >= mx:
            return bot.reply_to(msg, f"⚠️ Limit ({cur}/{mx})! Upgrade plan.")
        rem = '♾️' if mx == -1 else str(mx - cur)
        safe_send(msg.chat.id,
            f"📤 <b>DEPLOY YOUR BOT</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"Send your file now!\n\n🐍 Python (.py)\n🟨 Node.js (.js)\n📦 ZIP (auto-detects entry!)\n\n"
            f"🔍 <b>Smart Detection:</b>\napp.py / main.py / bot.py\n"
            f"package.json / Procfile\nrequirements.txt (auto-install)\n\n📦 Slots remaining: {rem}\n━━━━━━━━━━━━━━━━━━━━")

    def show_sub(msg):
        u = db.get_user(msg.from_user.id)
        if not u:
            return
        pl = PLAN_LIMITS.get(u['plan'], PLAN_LIMITS['free'])
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("📋 View Plans", callback_data="plans"))
        safe_send(msg.from_user.id,
            f"💎 <b>YOUR SUBSCRIPTION</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Plan: {pl['name']}\n📅 Expires: {time_left(u['subscription_end'])}\n"
            f"🤖 Slots: {'♾️' if pl['max_bots'] == -1 else pl['max_bots']}\n"
            f"💾 RAM: {pl['ram']}MB\n🔄 Auto Restart: {'✅' if pl['auto_restart'] else '❌'}\n"
            f"💰 Total Spent: {u['total_spent']} BDT\n━━━━━━━━━━━━━━━━━━━━",
            reply_markup=m)

    def show_wallet(msg):
        u = db.get_user(msg.from_user.id)
        if not u:
            return
        h = db.wallet_hist(msg.from_user.id, 5)
        t = (f"💰 <b>WALLET</b>\n━━━━━━━━━━━━━━━━━━━━\n"
             f"💵 Balance: <b>{u['wallet_balance']} BDT</b>\n"
             f"💰 Total Earned: {u['referral_earnings']} BDT\n━━━━━━━━━━━━━━━━━━━━\n"
             f"<b>Recent Transactions:</b>\n")
        for x in h:
            ic = "➕" if x['tx_type'] in ('credit', 'referral', 'bonus') else "➖"
            t += f"{ic} {x['amount']} BDT — {x['description'][:25]}\n"
        if not h:
            t += "(No transactions yet)\n"
        safe_send(msg.from_user.id, t)

    def show_ref(msg):
        uid = msg.from_user.id
        u = db.get_user(uid)
        if not u:
            return bot.reply_to(msg, "/start first!")
        rc = u.get('referral_code')
        if not rc or len(rc) < 5:
            rc = gen_ref_code(uid)
            db.update_user(uid, referral_code=rc)
            u = db.get_user(uid)
            rc = u['referral_code']
        lnk = f"https://t.me/{BOT_USERNAME}?start={rc}"
        lvl_icons = {'bronze': '🥉', 'silver': '🥈', 'gold': '🥇', 'platinum': '💠', 'diamond': '💎'}
        t = (f"🎁 <b>REFERRAL PROGRAM</b>\n━━━━━━━━━━━━━━━━━━━━\n"
             f"🔑 Code: <code>{rc}</code>\n🔗 Link:\n<code>{lnk}</code>\n\n"
             f"👥 Referrals: {u['referral_count']}\n"
             f"{lvl_icons.get(u['referral_level'], '🥉')} Level: {u['referral_level'].title()}\n"
             f"💰 Earned: {u['referral_earnings']} BDT\n━━━━━━━━━━━━━━━━━━━━\n"
             f"💰 {REF_COMMISSION} BDT + 📅 {REF_BONUS_DAYS} days per ref\n👆 Tap link to copy!")
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton("📋 Copy Link", callback_data=f"cpref:{rc}"),
            types.InlineKeyboardButton("🏆 Leaderboard", callback_data="board"),
            types.InlineKeyboardButton("📋 My Referrals", callback_data="myrefs"),
            types.InlineKeyboardButton("📤 Share", switch_inline_query=f"🚀 Join {BRAND}!\n{lnk}")
        )
        safe_send(uid, t, reply_markup=m)

    def show_stats(msg):
        s = db.stats()
        ss = sys_stats()
        with bot_lock:
            rn = len([k for k in bot_scripts if is_running(k)])
        safe_send(msg.chat.id,
            f"📊 <b>SYSTEM STATISTICS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥️ CPU: {ss['cpu']}%\n🧠 RAM: {ss['mem']}%\n💾 Disk: {ss['disk']}%\n"
            f"⏱️ Uptime: {ss['up']}\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Running: {rn}\n👥 Total Users: {s['users']}\n📅 Today: {s['today']}\n"
            f"💎 Active Subs: {s['active_subs']}\n💰 Revenue: {s['revenue']} BDT\n━━━━━━━━━━━━━━━━━━━━")

    def show_running(msg):
        uid = msg.from_user.id
        r = []
        with bot_lock:
            items = list(bot_scripts.items())
        for sk, i in items:
            if is_running(sk) and (uid == OWNER_ID or uid in admin_ids or i.get('user_id') == uid):
                up = str(datetime.now() - i.get('start_time', datetime.now())).split('.')[0]
                ram, cpu = bot_res(sk)
                r.append(f"📄 {i.get('file_name', '?')[:20]}\n   PID:{i['process'].pid} ⏱️{up} 💾{ram}MB")
        t = f"🟢 <b>Running ({len(r)})</b>\n\n" + "\n".join(r) if r else "🔴 No bots running."
        safe_send(msg.chat.id, t)

    def show_speed(msg):
        ss = sys_stats()
        safe_send(msg.chat.id,
            f"⚡ <b>Speed Test</b>\n\n🖥️ CPU: {ss['cpu']}%\n🧠 RAM: {ss['mem']}%\n"
            f"💾 Disk: {ss['disk']}%\n🌐 Mem: {ss['mem_total']}\n⏱️ {ss['up']}")

    def show_notifs(msg):
        uid = msg.from_user.id
        notifs = db.get_notifs(uid, 10)
        t = f"🔔 <b>Notifications</b>\n\n"
        for n in notifs:
            ic = "🔴" if not n['is_read'] else "⚪"
            t += f"{ic} <b>{n['title']}</b>\n{n['message'][:50]}\n\n"
        if not notifs:
            t += "No notifications yet!"
        db.mark_read(uid)
        safe_send(uid, t)

    def show_support(msg):
        uid = msg.from_user.id
        with state_lock:
            user_states[uid] = {'action': 'ticket'}
        safe_send(uid,
            f"🎫 <b>Create Support Ticket</b>\n\n"
            f"Send your issue/question in one message.\n"
            f"Our team will respond ASAP!\n\n📞 Direct: {YOUR_USERNAME}\n\n{BRAND_TAG}")

    def show_settings(msg):
        uid = msg.from_user.id
        u = db.get_user(uid)
        if not u:
            return
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton("🇺🇸 English", callback_data="lang:en"),
            types.InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang:bn")
        )
        m.add(types.InlineKeyboardButton("📊 My Profile", callback_data="profile"))
        m.add(types.InlineKeyboardButton("💳 Payment History", callback_data="pay_history"))
        safe_send(uid,
            f"⚙️ <b>Settings</b>\n👤 {u['full_name']}\n🆔 <code>{uid}</code>\n"
            f"📅 Joined: {u['created_at'][:10] if u.get('created_at') else '?'}\n"
            f"📦 Plan: {PLAN_LIMITS.get(u['plan'], PLAN_LIMITS['free'])['name']}\n\n{BRAND_TAG}",
            reply_markup=m)

    def show_admin(msg):
        uid = msg.from_user.id
        if uid != OWNER_ID and uid not in admin_ids:
            return bot.reply_to(msg, "❌ Admin only!")
        s = db.stats()
        with bot_lock:
            rn = len([k for k in bot_scripts if is_running(k)])
        tickets = len(db.open_tickets())
        safe_send(uid,
            f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Users: {s['users']} (+{s['today']} today)\n🤖 Running: {rn}\n"
            f"💎 Active Subs: {s['active_subs']}\n💳 Pending: {s['pending']}\n"
            f"🎫 Open Tickets: {tickets}\n💰 Revenue: {s['revenue']} BDT\n"
            f"Force Sub: {'🟢 ON' if FORCE_SUB_ENABLED else '🔴 OFF'}\n━━━━━━━━━━━━━━━━━━━━",
            reply_markup=admin_kb())

    def do_broadcast(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        with state_lock:
            user_states[uid] = {'action': 'broadcast'}
        bot.reply_to(msg, "📢 Send broadcast message:")

    def do_lock(msg):
        global bot_locked
        import config
        if msg.from_user.id not in admin_ids and msg.from_user.id != OWNER_ID:
            return
        config.bot_locked = not config.bot_locked
        bot.reply_to(msg, f"{'🔒 LOCKED' if config.bot_locked else '🔓 UNLOCKED'}")

    def show_payments(msg):
        uid = msg.from_user.id
        if uid not in admin_ids and uid != OWNER_ID:
            return
        pays = db.pending_pay()
        if not pays:
            return safe_send(uid, "💳 No pending payments!")
        t = f"💳 <b>Pending ({len(pays)})</b>\n\n"
        m = types.InlineKeyboardMarkup(row_width=2)
        for p in pays[:10]:
            u = db.get_user(p['user_id'])
            name = u['full_name'] if u else str(p['user_id'])
            t += f"#{p['payment_id']} — {name}\n💰 {p['amount']} {p['method']} TRX:{p['transaction_id'][:15]}\n\n"
            m.add(
                types.InlineKeyboardButton(f"✅ #{p['payment_id']}", callback_data=f"appv:{p['payment_id']}"),
                types.InlineKeyboardButton(f"❌ #{p['payment_id']}", callback_data=f"rejt:{p['payment_id']}")
            )
        safe_send(uid, t, reply_markup=m)

    # ──────────────────────────────
    #  STATE HANDLER
    # ──────────────────────────────
    def handle_state(msg):
        uid = msg.from_user.id
        with state_lock:
            s = user_states.get(uid)
        if not s:
            return

        action = s.get('action')

        if action == 'broadcast':
            if uid not in admin_ids and uid != OWNER_ID:
                with state_lock:
                    user_states.pop(uid, None)
                return
            text = msg.text
            # Background broadcast — NO FREEZE
            threading.Thread(
                target=run_broadcast_thread,
                args=(text, uid),
                daemon=True
            ).start()
            bot.reply_to(msg, f"📢 Broadcasting in background to all users...")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'a_addsub' and s.get('step', 1) == 1:
            try:
                target = int(msg.text.strip())
                target_user = db.get_user(target)
                if not target_user:
                    bot.reply_to(msg, f"❌ User {target} not found!")
                    with state_lock:
                        user_states.pop(uid, None)
                    return
                with state_lock:
                    user_states[uid] = {'action': 'a_addsub', 'step': 2, 'target': target}
                m = types.InlineKeyboardMarkup(row_width=2)
                for k, p in PLAN_LIMITS.items():
                    if k != 'free':
                        m.add(types.InlineKeyboardButton(p['name'], callback_data=f"asub:{k}:{target}"))
                bot.reply_to(msg,
                    f"👤 User: <code>{target}</code> — {target_user['full_name']}\n"
                    f"Current: {PLAN_LIMITS.get(target_user['plan'], PLAN_LIMITS['free'])['name']}\n\n"
                    f"Select new plan:", parse_mode='HTML', reply_markup=m)
                return
            except ValueError:
                bot.reply_to(msg, "❌ Invalid user ID!")
                with state_lock:
                    user_states.pop(uid, None)

        elif action == 'a_addsub_days':
            try:
                days = int(msg.text.strip())
                target = s['target']
                plan = s['plan']
                if days == 0:
                    db.set_sub(target, 'lifetime')
                    plan_name = "👑 Lifetime"
                else:
                    db.set_sub(target, plan, days)
                    plan_name = PLAN_LIMITS.get(plan, {}).get('name', plan)
                bot.reply_to(msg,
                    f"✅ <b>Subscription Added!</b>\n\n"
                    f"👤 User: <code>{target}</code>\n📦 Plan: {plan_name}\n"
                    f"📅 Duration: {'Lifetime' if days == 0 else f'{days} days'}",
                    parse_mode='HTML')
                db.admin_log(uid, 'add_sub', target, f"{plan}/{days}d")
                safe_send(target,
                    f"🎉 <b>Plan Upgraded!</b>\n\n📦 New Plan: {plan_name}\n"
                    f"📅 Duration: {'Lifetime' if days == 0 else f'{days} days'}\n\n{BRAND_TAG}")
            except ValueError:
                bot.reply_to(msg, "❌ Invalid! Send a number (0 = lifetime).")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'a_remsub':
            try:
                target = int(msg.text.strip())
                db.rem_sub(target)
                bot.reply_to(msg, f"✅ Subscription removed: <code>{target}</code>", parse_mode='HTML')
                db.admin_log(uid, 'remove_sub', target)
                safe_send(target, "⚠️ Your subscription has been removed by admin.")
            except:
                bot.reply_to(msg, "❌ Invalid user ID!")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'a_ban':
            parts = msg.text.strip().split(maxsplit=1)
            try:
                target = int(parts[0])
                reason = parts[1] if len(parts) > 1 else "Banned by admin"
                db.ban(target, reason)
                db.admin_log(uid, 'ban', target, reason)
                for b in db.get_bots(target):
                    sk = f"{target}_{b['bot_name']}"
                    with bot_lock:
                        info = bot_scripts.get(sk)
                    if info:
                        kill_tree(info)
                        cleanup_script(sk)
                    db.update_bot(b['bot_id'], status='stopped')
                bot.reply_to(msg, f"🚫 Banned <code>{target}</code>\nReason: {reason}", parse_mode='HTML')
                safe_send(target, f"🚫 <b>You have been banned!</b>\nReason: {reason}\n\nContact {YOUR_USERNAME}")
            except:
                bot.reply_to(msg, "❌ Format: USER_ID REASON")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'a_unban':
            try:
                target = int(msg.text.strip())
                db.unban(target)
                db.admin_log(uid, 'unban', target)
                bot.reply_to(msg, f"✅ Unbanned <code>{target}</code>", parse_mode='HTML')
                safe_send(target, "✅ You have been unbanned! Welcome back.")
            except:
                bot.reply_to(msg, "❌ Invalid user ID!")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'a_promo':
            parts = msg.text.strip().split()
            if len(parts) >= 3:
                try:
                    code = parts[0].upper()
                    discount = int(parts[1])
                    max_uses = int(parts[2])
                    db.exe("INSERT OR IGNORE INTO promo_codes(code,discount_pct,max_uses,created_by) VALUES(?,?,?,?)",
                           (code, discount, max_uses, uid))
                    bot.reply_to(msg,
                        f"✅ <b>Promo Created!</b>\n\n🎟 Code: <code>{code}</code>\n"
                        f"💰 Discount: {discount}%\n🔢 Max Uses: {max_uses}", parse_mode='HTML')
                    db.admin_log(uid, 'create_promo', details=f"{code}/{discount}%/{max_uses}")
                except:
                    bot.reply_to(msg, "❌ Error!")
            else:
                bot.reply_to(msg, "❌ Format: CODE DISCOUNT% MAX_USES\nEx: SAVE50 50 100")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'ch_add':
            text = msg.text.strip()
            if not text:
                bot.reply_to(msg, "❌ Send channel username!")
                with state_lock:
                    user_states.pop(uid, None)
                return
            parts = text.split(maxsplit=1)
            ch_username = parts[0].lstrip('@').lower()
            ch_name = parts[1] if len(parts) > 1 else ch_username
            try:
                chat_info = bot.get_chat(f"@{ch_username}")
                ch_name = chat_info.title or ch_name
            except:
                pass
            db.add_channel(ch_username, ch_name, uid)
            db.admin_log(uid, 'add_channel', details=f"@{ch_username}")
            bot.reply_to(msg,
                f"✅ <b>Channel Added!</b>\n\n📢 @{ch_username}\n📝 {ch_name}\n\n"
                f"⚠️ Make sure bot is admin!", parse_mode='HTML')
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'ch_remove':
            text = msg.text.strip().lstrip('@').lower()
            if not text:
                bot.reply_to(msg, "❌ Send channel username!")
                with state_lock:
                    user_states.pop(uid, None)
                return
            db.remove_channel(text)
            db.admin_log(uid, 'remove_channel', details=f"@{text}")
            bot.reply_to(msg, f"✅ Removed @{text} from force subscribe!")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'ticket':
            text = msg.text.strip()
            if len(text) < 5:
                bot.reply_to(msg, "❌ Message too short!")
                with state_lock:
                    user_states.pop(uid, None)
                return
            tid = db.add_ticket(uid, "Support Request", text)
            bot.reply_to(msg,
                f"✅ <b>Ticket #{tid} Created!</b>\n\n📝 {text[:100]}...\n\n"
                f"Our team will respond soon.\n{YOUR_USERNAME}\n\n{BRAND_TAG}",
                parse_mode='HTML')
            u = db.get_user(uid)
            for aid in admin_ids:
                safe_send(aid,
                    f"🎫 <b>New Ticket #{tid}</b>\n\n"
                    f"👤 {u['full_name'] if u else uid} (<code>{uid}</code>)\n"
                    f"📝 {text[:200]}\n\nReply: /reply {tid} your_message")
            with state_lock:
                user_states.pop(uid, None)

        elif action == 'ticket_reply':
            tid = s.get('ticket_id')
            text = msg.text.strip()
            if not text or not tid:
                with state_lock:
                    user_states.pop(uid, None)
                return
            ticket = db.exe("SELECT * FROM tickets WHERE ticket_id=?", (tid,), one=True)
            if ticket:
                db.reply_ticket(tid, text)
                bot.reply_to(msg, f"✅ Replied to ticket #{tid}")
                safe_send(ticket['user_id'],
                    f"📩 <b>Ticket #{tid} Reply</b>\n\n💬 {text}\n\nFrom: Admin\n{BRAND_TAG}")
            with state_lock:
                user_states.pop(uid, None)

        else:
            with state_lock:
                user_states.pop(uid, None)

    # ──────────────────────────────
    #  PAYMENT TEXT HANDLER
    # ──────────────────────────────
    def handle_pay_text(msg):
        uid = msg.from_user.id
        with state_lock:
            s = payment_states.get(uid)
        if not s or s.get('step') != 'wait_trx':
            return

        trx = msg.text.strip() if msg.text else 'SCREENSHOT'
        if not trx or len(trx) < 3:
            return bot.reply_to(msg, "❌ Please send a valid Transaction ID!")

        pid = db.add_pay(uid, s['amount'], s['method'], trx, s['plan'], 30)
        with state_lock:
            payment_states.pop(uid, None)

        safe_send(uid,
            f"✅ <b>PAYMENT SUBMITTED!</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Payment ID: #{pid}\n💰 Amount: {s['amount']} BDT\n"
            f"💳 Method: {s['method']}\n📦 Plan: {s['plan']}\n"
            f"🔖 TRX: <code>{trx}</code>\n\n⏳ Waiting for admin approval...\n━━━━━━━━━━━━━━━━━━━━")

        u = db.get_user(uid)
        for aid in admin_ids:
            method_info = PAYMENT_METHODS.get(s['method'], {})
            safe_send(aid,
                f"💳 <b>NEW PAYMENT!</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {u['full_name'] if u else '?'} (<code>{uid}</code>)\n"
                f"📦 Plan: {s['plan']}\n💰 Amount: {s['amount']} BDT\n"
                f"{method_info.get('icon', '💳')} Method: {method_info.get('name', s['method'])}\n"
                f"🔖 TRX: <code>{trx}</code>\n🆔 Payment #{pid}\n━━━━━━━━━━━━━━━━━━━━",
                reply_markup=pay_approve_kb(pid))