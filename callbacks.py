"""
╔═══════════════════════════════════════════╗
║  callbacks.py — Callback Query Handlers   ║
║  APON HOSTING PANEL v4.1                  ║
╚═══════════════════════════════════════════╝
"""

import os
import time
import shutil
import threading
from datetime import datetime
from telebot import types

from config import (
    logger, OWNER_ID, admin_ids, PLAN_LIMITS, PAYMENT_METHODS,
    BRAND, BRAND_VER, BRAND_TAG, BRAND_SHORT, BOT_USERNAME,
    YOUR_USERNAME, REF_COMMISSION, REF_BONUS_DAYS,
    bot_lock, state_lock, bot_scripts, user_states, payment_states,
    LOGS_DIR, BACKUP_DIR, DB_PATH
)
from database import db
from utils import (
    safe_send, safe_edit, safe_answer, report_error,
    get_uptime, time_left, is_running, bot_res,
    cleanup_script, kill_tree, sys_stats, check_joined,
    user_folder, det, gen_ref_code
)
from keyboards import (
    main_kb, bot_action_kb, plan_kb, pay_method_kb,
    admin_kb, pay_approve_kb, channels_kb
)
from runner import run_bot


def register_callbacks(bot):
    """Register all callback handlers"""

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback(call):
        uid = call.from_user.id
        data = call.data
        chat_id = call.message.chat.id
        msg_id = call.message.message_id

        try:
            # ── VERIFY JOIN ──
            if data == "verify_join":
                joined, nj = check_joined(uid)
                if joined:
                    safe_answer(call.id, "✅ Verified! Welcome!", show_alert=True)
                    try:
                        bot.delete_message(chat_id, msg_id)
                    except:
                        pass
                    class FakeMsg:
                        def __init__(self, c):
                            self.from_user = c.from_user
                            self.chat = c.message.chat
                            self.text = "/start"
                    from handlers import register_handlers
                    # Directly call start-like behavior
                    safe_send(uid, "✅ Welcome back!", reply_markup=main_kb(uid))
                else:
                    safe_answer(call.id, "❌ Join all channels first!", show_alert=True)
                return

            # ── MENU ──
            elif data == "menu":
                safe_answer(call.id)
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass
                safe_send(uid, "🏠 Main Menu", reply_markup=main_kb(uid))

            # ── MY BOTS ──
            elif data == "mybots":
                safe_answer(call.id)
                bots_list = db.get_bots(uid)
                pl = db.get_plan(uid)
                mx = '♾️' if pl['max_bots'] == -1 else str(pl['max_bots'])
                if not bots_list:
                    safe_edit(f"📭 <b>No bots yet!</b>\nDeploy with 📤\n📦 Slots: 0/{mx}\n\n{BRAND_TAG}",
                              chat_id, msg_id)
                    return
                rn = sum(1 for b in bots_list if is_running(f"{uid}_{b['bot_name']}"))
                t = f"🤖 <b>My Bots</b> ({len(bots_list)}) | 🟢 {rn} | 🔴 {len(bots_list) - rn}\n📦 Limit: {mx}\n\n"
                m = types.InlineKeyboardMarkup(row_width=1)
                for b in bots_list:
                    r = is_running(f"{uid}_{b['bot_name']}")
                    ic = "🐍" if b['file_type'] == 'py' else "🟨"
                    st_icon = "🟢" if r else "🔴"
                    t += f"{st_icon} {ic} {b['bot_name'][:20]} #{b['bot_id']} — {b['entry_file']}\n"
                    m.add(types.InlineKeyboardButton(
                        f"{st_icon} {b['bot_name'][:15]} #{b['bot_id']}",
                        callback_data=f"detail:{b['bot_id']}"))
                m.add(types.InlineKeyboardButton("📤 Deploy New", callback_data="deploy"))
                safe_edit(t, chat_id, msg_id, reply_markup=m)

            # ── BOT DETAIL ──
            elif data.startswith("detail:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "❌ Bot not found!")
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                rn = is_running(sk)
                ram, cpu = bot_res(sk) if rn else (0, 0)
                uptime_str = "—"
                if rn:
                    with bot_lock:
                        info = bot_scripts.get(sk)
                    if info:
                        st = info.get('start_time')
                        if st:
                            uptime_str = str(datetime.now() - st).split('.')[0]
                icon = "🐍" if bd['file_type'] == 'py' else "🟨"
                status_icon = "🟢 Running" if rn else "🔴 Stopped"
                t = (f"{icon} <b>{bd['bot_name'][:22]}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                     f"🆔 Bot ID: #{bid}\n📄 Entry: {bd['entry_file']}\n"
                     f"🔤 Type: {bd['file_type'].upper()}\n📊 Status: {status_icon}\n"
                     f"💾 RAM: {ram}MB | ⚡ CPU: {cpu}%\n⏱️ Uptime: {uptime_str}\n"
                     f"🔄 Restarts: {bd['total_restarts']}\n"
                     f"📅 Created: {bd['created_at'][:10] if bd.get('created_at') else '?'}\n━━━━━━━━━━━━━━━━━━━━")
                safe_edit(t, chat_id, msg_id, reply_markup=bot_action_kb(bid, 'running' if rn else 'stopped'))
                safe_answer(call.id)

            # ── BOT START ──
            elif data.startswith("start:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "❌ Not found!")
                if not db.is_active(bd['user_id']):
                    return safe_answer(call.id, "⚠️ Subscription expired!", show_alert=True)
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                if is_running(sk):
                    return safe_answer(call.id, "⚠️ Already running!")
                safe_answer(call.id, "🚀 Starting...")
                threading.Thread(target=run_bot, args=(bid, chat_id), daemon=True).start()

            # ── BOT STOP ──
            elif data.startswith("stop:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "❌ Not found!")
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                with bot_lock:
                    info = bot_scripts.get(sk)
                if info:
                    kill_tree(info)
                    cleanup_script(sk)
                db.update_bot(bid, status='stopped', last_stopped=datetime.now().isoformat())
                safe_answer(call.id, "✅ Stopped!")
                call.data = f"detail:{bid}"
                handle_callback(call)

            # ── BOT RESTART ──
            elif data.startswith("restart:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "❌ Not found!")
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                with bot_lock:
                    info = bot_scripts.get(sk)
                if info:
                    kill_tree(info)
                    cleanup_script(sk)
                time.sleep(2)
                safe_answer(call.id, "🔄 Restarting...")
                threading.Thread(target=run_bot, args=(bid, chat_id), daemon=True).start()

            # ── LOGS ──
            elif data.startswith("logs:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "❌!")
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                lp = os.path.join(LOGS_DIR, f"{sk}.log")
                logs = "📭 No logs."
                if os.path.exists(lp):
                    try:
                        with open(lp, 'r', encoding='utf-8', errors='ignore') as f:
                            logs = f.read()[-1500:] or "📭 Empty."
                    except:
                        logs = "❌ Error reading logs."
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("🔄 Refresh", callback_data=f"logs:{bid}"),
                    types.InlineKeyboardButton("🗑 Clear", callback_data=f"clearlogs:{bid}")
                )
                m.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"detail:{bid}"))
                safe_edit(f"📋 <b>Logs — #{bid}</b>\n\n<code>{logs}</code>"[:4000], chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            elif data.startswith("clearlogs:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if bd:
                    sk = f"{bd['user_id']}_{bd['bot_name']}"
                    lp = os.path.join(LOGS_DIR, f"{sk}.log")
                    try:
                        with open(lp, 'w') as f:
                            f.write("")
                    except:
                        pass
                safe_answer(call.id, "🗑 Cleared!")
                call.data = f"logs:{bid}"
                handle_callback(call)

            # ── RESOURCES ──
            elif data.startswith("res:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "!")
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                ram, cpu = bot_res(sk)
                uptime_str = "—"
                with bot_lock:
                    info = bot_scripts.get(sk)
                if info:
                    st = info.get('start_time')
                    if st:
                        uptime_str = str(datetime.now() - st).split('.')[0]
                m = types.InlineKeyboardMarkup()
                m.add(
                    types.InlineKeyboardButton("🔄 Refresh", callback_data=f"res:{bid}"),
                    types.InlineKeyboardButton("🔙 Back", callback_data=f"detail:{bid}")
                )
                safe_edit(f"📊 <b>Resources — #{bid}</b>\n\n💾 RAM: {ram}MB\n⚡ CPU: {cpu}%\n"
                          f"⏱️ Uptime: {uptime_str}\n🔄 Restarts: {bd['total_restarts']}",
                          chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            # ── RE-DETECT ──
            elif data.startswith("redetect:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "!")
                wd = bd['file_path'] if os.path.isdir(bd['file_path']) else user_folder(bd['user_id'])
                entry, ft, rp = det.report(wd)
                if entry:
                    db.update_bot(bid, entry_file=entry, file_type=ft)
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(
                        types.InlineKeyboardButton("▶️ Start", callback_data=f"start:{bid}"),
                        types.InlineKeyboardButton("🔙 Back", callback_data=f"detail:{bid}")
                    )
                    safe_edit(f"🔍 <b>Re-Detection</b>\n\n{rp}\n\n✅ Entry updated!", chat_id, msg_id, reply_markup=m)
                else:
                    af = [os.path.relpath(os.path.join(r, f), wd)
                          for r, d, fs in os.walk(wd) for f in fs if f.endswith(('.py', '.js'))]
                    m = types.InlineKeyboardMarkup(row_width=1)
                    for f in af[:10]:
                        ftype = 'js' if f.endswith('.js') else 'py'
                        m.add(types.InlineKeyboardButton(f"📄 {f}", callback_data=f"setentry:{bid}:{f}:{ftype}"))
                    m.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"detail:{bid}"))
                    t = "🔍 ❌ Auto-detect failed!\n\nSelect entry file:\n"
                    for f in af[:10]:
                        t += f"• {f}\n"
                    safe_edit(t, chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            elif data.startswith("setentry:"):
                parts = data.split(":")
                bid = int(parts[1])
                entry = parts[2]
                ft = parts[3]
                db.update_bot(bid, entry_file=entry, file_type=ft)
                safe_answer(call.id, f"✅ Entry: {entry}")
                call.data = f"detail:{bid}"
                handle_callback(call)

            # ── DELETE ──
            elif data.startswith("del:"):
                bid = int(data.split(":")[1])
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("✅ Yes Delete", callback_data=f"cdel:{bid}"),
                    types.InlineKeyboardButton("❌ Cancel", callback_data=f"detail:{bid}")
                )
                safe_edit(f"🗑 <b>Delete Bot #{bid}?</b>\n\n⚠️ Cannot be undone!", chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            elif data.startswith("cdel:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if bd:
                    sk = f"{bd['user_id']}_{bd['bot_name']}"
                    with bot_lock:
                        info = bot_scripts.get(sk)
                    if info:
                        kill_tree(info)
                        cleanup_script(sk)
                    if os.path.isdir(bd['file_path']):
                        shutil.rmtree(bd['file_path'], ignore_errors=True)
                    else:
                        try:
                            os.remove(os.path.join(user_folder(bd['user_id']), bd['bot_name']))
                        except:
                            pass
                    db.del_bot(bid)
                safe_answer(call.id, "✅ Deleted!")
                call.data = "mybots"
                handle_callback(call)

            # ── DOWNLOAD ──
            elif data.startswith("dl:"):
                bid = int(data.split(":")[1])
                bd = db.get_bot(bid)
                if not bd:
                    return safe_answer(call.id, "!")
                fp = os.path.join(bd['file_path'], bd['entry_file']) if os.path.isdir(bd['file_path']) else os.path.join(user_folder(bd['user_id']), bd['bot_name'])
                if os.path.exists(fp):
                    try:
                        with open(fp, 'rb') as f:
                            bot.send_document(uid, f, caption=f"📄 {bd['bot_name']}")
                    except:
                        pass
                safe_answer(call.id, "📥 Sent!")

            # ── DEPLOY ──
            elif data == "deploy":
                safe_answer(call.id)
                safe_send(uid,
                    f"📤 <b>DEPLOY YOUR BOT</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"Send your file now!\n\n🐍 Python (.py)\n🟨 Node.js (.js)\n📦 ZIP\n━━━━━━━━━━━━━━━━━━━━")

            # ── REFERRAL ──
            elif data.startswith("cpref:"):
                rc = data.split(":", 1)[1]
                lnk = f"https://t.me/{BOT_USERNAME}?start={rc}"
                safe_answer(call.id)
                safe_send(uid, f"📋 <b>Your Referral Link:</b>\n\n<code>{lnk}</code>\n\n👆 Tap to copy!")

            elif data == "myrefs":
                refs = db.user_refs(uid)
                t = f"📋 <b>Your Referrals ({len(refs)})</b>\n\n"
                for r in refs[:20]:
                    ru = db.get_user(r['referred_id'])
                    name = ru['full_name'] if ru else str(r['referred_id'])
                    t += f"👤 {name} — +{r['commission']} BDT — {r['created_at'][:10]}\n"
                if not refs:
                    t += "No referrals yet!"
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu"))
                safe_edit(t, chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            elif data == "board":
                lb = db.ref_board(10)
                t = f"🏆 <b>Referral Leaderboard</b>\n\n"
                medals = ['🥇', '🥈', '🥉']
                for i, l in enumerate(lb):
                    icon = medals[i] if i < 3 else f"#{i + 1}"
                    t += f"{icon} {l['full_name'] or '?'} — {l['referral_count']} refs ({l['referral_earnings']} BDT)\n"
                if not lb:
                    t += "No referrals yet!"
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu"))
                safe_edit(t, chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            # ── PLANS & SUBSCRIPTION ──
            elif data in ("plans", "sub"):
                t = f"📋 <b>Available Plans</b>\n\n"
                for k, p in PLAN_LIMITS.items():
                    if k == 'free':
                        continue
                    bots_txt = '♾️' if p['max_bots'] == -1 else str(p['max_bots'])
                    t += (f"{p['name']}\n  🤖 {bots_txt} bots | 💾 {p['ram']}MB RAM\n"
                          f"  🔄 Auto Restart: {'✅' if p['auto_restart'] else '❌'}\n  💰 {p['price']} BDT/month\n\n")
                safe_edit(t, chat_id, msg_id, reply_markup=plan_kb())
                safe_answer(call.id)

            elif data.startswith("plan:"):
                pk = data.split(":")[1]
                p = PLAN_LIMITS.get(pk)
                if not p:
                    return
                bots_txt = '♾️' if p['max_bots'] == -1 else str(p['max_bots'])
                safe_edit(
                    f"{p['name']}\n\n🤖 Bots: {bots_txt}\n💾 RAM: {p['ram']}MB\n"
                    f"🔄 Auto Restart: {'✅' if p['auto_restart'] else '❌'}\n"
                    f"💰 Price: {p['price']} BDT/month\n\nSelect payment method:",
                    chat_id, msg_id, reply_markup=pay_method_kb(pk))
                safe_answer(call.id)

            elif data.startswith("pay:"):
                parts = data.split(":")
                pk = parts[1]
                mk = parts[2]
                p = PLAN_LIMITS.get(pk)
                pm = PAYMENT_METHODS.get(mk)
                if not p or not pm:
                    return
                with state_lock:
                    payment_states[uid] = {'step': 'wait_trx', 'plan': pk, 'method': mk, 'amount': p['price']}
                safe_edit(
                    f"{pm['icon']} <b>{pm['name']}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"📱 Send to: <code>{pm['number']}</code>\n📝 Type: {pm['type']}\n"
                    f"💰 Amount: <b>{p['price']} BDT</b>\n📦 Plan: {p['name']}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n📤 Send Transaction ID below:",
                    chat_id, msg_id)
                safe_answer(call.id)

            elif data.startswith("payw:"):
                pk = data.split(":")[1]
                u = db.get_user(uid)
                p = PLAN_LIMITS.get(pk)
                if not u or not p:
                    return
                if u['wallet_balance'] < p['price']:
                    return safe_answer(call.id,
                        f"❌ Need: {p['price']} BDT | Have: {u['wallet_balance']} BDT", show_alert=True)
                db.wallet_tx(uid, p['price'], 'purchase', f"Plan: {pk}")
                db.set_sub(uid, pk if pk != 'lifetime' else 'lifetime', 30)
                safe_answer(call.id, "✅ Plan activated!")
                safe_edit(f"✅ <b>Plan Activated!</b>\n\n📦 {p['name']}\n💰 Paid: {p['price']} BDT\n\n{BRAND_TAG}",
                          chat_id, msg_id)

            # ── PAYMENT APPROVAL ──
            elif data.startswith("appv:"):
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                pid = int(data.split(":")[1])
                p = db.approve_pay(pid, uid)
                if p:
                    safe_answer(call.id, "✅ Approved!")
                    safe_edit((call.message.text or '') + "\n\n✅ APPROVED", chat_id, msg_id)
                    plan_name = PLAN_LIMITS.get(p['plan'], {}).get('name', p['plan'])
                    safe_send(p['user_id'],
                        f"🎉 <b>Payment Approved!</b>\n\n📦 Plan: {plan_name}\n"
                        f"📅 Duration: {p['duration_days']} days\n\n{BRAND_TAG}")

            elif data.startswith("rejt:"):
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                pid = int(data.split(":")[1])
                pay = db.get_pay(pid)
                db.reject_pay(pid, uid)
                safe_answer(call.id, "❌ Rejected!")
                safe_edit((call.message.text or '') + "\n\n❌ REJECTED", chat_id, msg_id)
                if pay:
                    safe_send(pay['user_id'],
                        f"❌ <b>Payment Rejected</b>\n\nPayment #{pid} not approved.\n"
                        f"Contact {YOUR_USERNAME}\n\n{BRAND_TAG}")

            # ── SETTINGS ──
            elif data.startswith("lang:"):
                lang = data.split(":")[1]
                db.update_user(uid, language=lang)
                safe_answer(call.id, "✅ Language updated!")

            elif data == "profile":
                u = db.get_user(uid)
                if not u:
                    return
                pl = PLAN_LIMITS.get(u['plan'], PLAN_LIMITS['free'])
                bc = db.bot_count(uid)
                lvl_icons = {'bronze': '🥉', 'silver': '🥈', 'gold': '🥇', 'platinum': '💠', 'diamond': '💎'}
                safe_edit(
                    f"👤 <b>MY PROFILE</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"📛 {u['full_name']}\n🆔 <code>{uid}</code>\n👤 @{u['username'] or 'N/A'}\n\n"
                    f"📦 Plan: {pl['name']}\n📅 Expires: {time_left(u['subscription_end'])}\n"
                    f"🤖 Bots: {bc}\n💰 Wallet: {u['wallet_balance']} BDT\n"
                    f"💳 Spent: {u['total_spent']} BDT\n\n👥 Refs: {u['referral_count']}\n"
                    f"{lvl_icons.get(u['referral_level'], '🥉')} Level: {u['referral_level'].title()}\n"
                    f"💰 Ref Earnings: {u['referral_earnings']} BDT\n━━━━━━━━━━━━━━━━━━━━",
                    chat_id, msg_id,
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("🔙 Back", callback_data="menu")))
                safe_answer(call.id)

            elif data == "pay_history":
                pays = db.exe("SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
                              (uid,), fetch=True) or []
                t = "💳 <b>Payment History</b>\n\n"
                for p in pays:
                    st_icon = "✅" if p['status'] == 'approved' else "❌" if p['status'] == 'rejected' else "⏳"
                    t += f"{st_icon} #{p['payment_id']} — {p['amount']} BDT — {p['method']} — {p['status']}\n"
                if not pays:
                    t += "No payments yet."
                safe_edit(t, chat_id, msg_id,
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("🔙 Back", callback_data="menu")))
                safe_answer(call.id)

            # ── ADMIN PANELS ──
            elif data == "admin_back":
                safe_answer(call.id)
                s = db.stats()
                with bot_lock:
                    rn = len([k for k in bot_scripts if is_running(k)])
                tickets = len(db.open_tickets())
                safe_edit(
                    f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"👥 Users: {s['users']} (+{s['today']} today)\n🤖 Running: {rn}\n"
                    f"💎 Active Subs: {s['active_subs']}\n💳 Pending: {s['pending']}\n"
                    f"🎫 Tickets: {tickets}\n💰 Revenue: {s['revenue']} BDT\n"
                    f"Force Sub: {'🟢 ON' if FORCE_SUB_ENABLED else '🔴 OFF'}\n━━━━━━━━━━━━━━━━━━━━",
                    chat_id, msg_id, reply_markup=admin_kb())

            elif data == "a_users":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                users = db.get_all_users()
                t = f"👥 <b>Users ({len(users)})</b>\n\n"
                for u in users[:25]:
                    st = "🚫" if u['is_banned'] else "💎" if u['plan'] != 'free' else "✅"
                    t += f"{st} <code>{u['user_id']}</code> {u['full_name'] or '-'} [{u['plan']}]\n"
                if len(users) > 25:
                    t += f"\n... +{len(users) - 25} more"
                safe_send(uid, t[:4000])
                safe_answer(call.id)

            elif data == "a_stats":
                safe_answer(call.id)
                ss = sys_stats()
                s = db.stats()
                with bot_lock:
                    rn = len([k for k in bot_scripts if is_running(k)])
                safe_send(uid,
                    f"📊 <b>SYSTEM STATISTICS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"🖥️ CPU: {ss['cpu']}%\n🧠 RAM: {ss['mem']}%\n💾 Disk: {ss['disk']}%\n"
                    f"⏱️ Uptime: {ss['up']}\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 Running: {rn}\n👥 Users: {s['users']}\n💰 Revenue: {s['revenue']} BDT")

            elif data == "a_pay":
                safe_answer(call.id)
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

            elif data == "a_bc":
                with state_lock:
                    user_states[uid] = {'action': 'broadcast'}
                safe_answer(call.id)
                safe_send(uid, "📢 Send broadcast message:")

            elif data == "a_addsub":
                with state_lock:
                    user_states[uid] = {'action': 'a_addsub', 'step': 1}
                safe_answer(call.id)
                safe_send(uid, "➕ Send user ID:")

            elif data.startswith("asub:"):
                parts = data.split(":")
                plan = parts[1]
                target = int(parts[2])
                with state_lock:
                    user_states[uid] = {'action': 'a_addsub_days', 'target': target, 'plan': plan}
                safe_answer(call.id)
                safe_send(uid, f"📦 Plan: {PLAN_LIMITS[plan]['name']}\n👤 User: <code>{target}</code>\n\nSend days (0 = lifetime):")

            elif data == "a_remsub":
                with state_lock:
                    user_states[uid] = {'action': 'a_remsub'}
                safe_answer(call.id)
                safe_send(uid, "➖ Send user ID to remove subscription:")

            elif data == "a_ban":
                with state_lock:
                    user_states[uid] = {'action': 'a_ban'}
                safe_answer(call.id)
                safe_send(uid, "🚫 Send: USER_ID REASON")

            elif data == "a_unban":
                with state_lock:
                    user_states[uid] = {'action': 'a_unban'}
                safe_answer(call.id)
                safe_send(uid, "✅ Send user ID to unban:")

            elif data == "a_promo":
                with state_lock:
                    user_states[uid] = {'action': 'a_promo'}
                safe_answer(call.id)
                safe_send(uid, "🎟 Send: CODE DISCOUNT% MAX_USES\nEx: SAVE50 50 100")

            elif data == "a_channels":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                from config import FORCE_SUB_ENABLED as FSE
                t = f"📢 <b>Force Subscribe Channels</b>\nStatus: {'🟢 ON' if FSE else '🔴 OFF'}\n\n"
                channels = db.get_all_channels()
                if channels:
                    for ch in channels:
                        st = "🟢 Active" if ch['is_active'] else "🔴 Inactive"
                        t += f"• @{ch['channel_username']} — {ch['channel_name']}\n  {st}\n\n"
                else:
                    t += "No channels. Default: @developer_apon_07\n"
                safe_edit(t, chat_id, msg_id, reply_markup=channels_kb())
                safe_answer(call.id)

            elif data.startswith("ch_toggle:"):
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                cid_ch = int(data.split(":")[1])
                new_status = db.toggle_channel(cid_ch)
                if new_status is not None:
                    safe_answer(call.id, f"{'🟢 Activated' if new_status else '🔴 Deactivated'}")
                call.data = "a_channels"
                handle_callback(call)

            elif data == "ch_add":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                with state_lock:
                    user_states[uid] = {'action': 'ch_add'}
                safe_answer(call.id)
                safe_send(uid, "➕ Send: @username Channel Name\nEx: @mychannel My Channel")

            elif data == "ch_remove":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                channels = db.get_active_channels()
                if not channels:
                    safe_answer(call.id, "No channels!")
                    return
                m = types.InlineKeyboardMarkup(row_width=1)
                for ch in channels:
                    m.add(types.InlineKeyboardButton(f"🗑 @{ch['channel_username']}", callback_data=f"ch_del:{ch['channel_id']}"))
                m.add(types.InlineKeyboardButton("🔙 Back", callback_data="a_channels"))
                safe_edit("🗑 Select channel to remove:", chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            elif data.startswith("ch_del:"):
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                cid_ch = int(data.split(":")[1])
                ch = db.exe("SELECT * FROM force_channels WHERE channel_id=?", (cid_ch,), one=True)
                if ch:
                    db.delete_channel(cid_ch)
                    safe_answer(call.id, f"✅ Deleted @{ch['channel_username']}")
                call.data = "a_channels"
                handle_callback(call)

            elif data == "a_fsub_toggle":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                import config
                config.FORCE_SUB_ENABLED = not config.FORCE_SUB_ENABLED
                safe_answer(call.id, f"Force Subscribe: {'🟢 ON' if config.FORCE_SUB_ENABLED else '🔴 OFF'}")
                call.data = "admin_back"
                handle_callback(call)

            elif data == "a_tickets":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                tickets = db.open_tickets()
                t = f"🎫 <b>Open Tickets ({len(tickets)})</b>\n\n"
                m = types.InlineKeyboardMarkup(row_width=1)
                for tk in tickets[:10]:
                    u = db.get_user(tk['user_id'])
                    name = u['full_name'] if u else str(tk['user_id'])
                    t += f"#{tk['ticket_id']} — {name}\n📝 {tk['message'][:50]}...\n\n"
                    m.add(types.InlineKeyboardButton(f"💬 Reply #{tk['ticket_id']}", callback_data=f"tkt_reply:{tk['ticket_id']}"))
                if not tickets:
                    t += "No open tickets! 🎉"
                m.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_back"))
                safe_edit(t, chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            elif data.startswith("tkt_reply:"):
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                tid = int(data.split(":")[1])
                with state_lock:
                    user_states[uid] = {'action': 'ticket_reply', 'ticket_id': tid}
                safe_answer(call.id)
                ticket = db.exe("SELECT * FROM tickets WHERE ticket_id=?", (tid,), one=True)
                if ticket:
                    safe_send(uid, f"💬 <b>Reply to Ticket #{tid}</b>\n\n📝 {ticket['message'][:200]}\n\nSend reply:")

            elif data == "a_sys":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                ss = sys_stats()
                with bot_lock:
                    rn = len([k for k in bot_scripts if is_running(k)])
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_back"))
                safe_edit(
                    f"🖥 <b>System</b>\n\n🖥️ CPU: {ss['cpu']}%\n🧠 RAM: {ss['mem']}%\n"
                    f"💾 Disk: {ss['disk']}%\n📊 RAM: {ss.get('mem_total', '?')}\n"
                    f"💿 Disk: {ss.get('disk_total', '?')}\n⏱️ Uptime: {ss['up']}\n🤖 Running: {rn}",
                    chat_id, msg_id, reply_markup=m)
                safe_answer(call.id)

            elif data == "a_stopall":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                count = 0
                with bot_lock:
                    keys = list(bot_scripts.keys())
                for sk in keys:
                    try:
                        with bot_lock:
                            info = bot_scripts.get(sk)
                        if info:
                            kill_tree(info)
                            cleanup_script(sk)
                            count += 1
                    except:
                        pass
                db.admin_log(uid, 'stop_all', details=f"stopped:{count}")
                safe_answer(call.id, f"🛑 Stopped {count} bots")

            elif data == "a_backup":
                if uid not in admin_ids and uid != OWNER_ID:
                    return
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                bp = os.path.join(BACKUP_DIR, f"bk_{ts}.db")
                shutil.copy2(DB_PATH, bp)
                safe_answer(call.id, "💾 Backup created!")
                try:
                    with open(bp, 'rb') as f:
                        bot.send_document(uid, f, caption=f"💾 Backup {ts}")
                except:
                    pass

            elif data == "none":
                safe_answer(call.id)

            else:
                safe_answer(call.id)

        except Exception as e:
            logger.error(f"Callback [{data}]: {e}", exc_info=True)
            report_error(e, f"callback:{data}")
            safe_answer(call.id, "❌ Error!")