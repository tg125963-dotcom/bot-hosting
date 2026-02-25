"""
╔═══════════════════════════════════════════╗
║  runner.py — Bot Runner Engine            ║
║  APON HOSTING PANEL v4.1                  ║
╚═══════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import subprocess
import threading
import shutil
from datetime import datetime

from config import (
    logger, bot_lock, bot_scripts, admin_ids,
    LOGS_DIR, MODULES_MAP, PLAN_LIMITS, BACKUP_DIR, DB_PATH
)
from database import db
from utils import (
    safe_send, report_error, det, user_folder,
    is_running, cleanup_script, kill_tree
)


# ═══════════════════════════════════════════
#  PIP INSTALLER
# ═══════════════════════════════════════════
def pip_install(mod, cid):
    pkg = MODULES_MAP.get(mod.split('.')[0].lower(), mod)
    try:
        safe_send(cid, f"📦 Installing {pkg}...")
        r = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', pkg, '--quiet'],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            safe_send(cid, f"✅ Installed {pkg}")
            return True
        return False
    except Exception as e:
        report_error(e, f"pip_install({pkg})")
        return False


# ═══════════════════════════════════════════
#  BOT RUNNER (Process-Safe)
# ═══════════════════════════════════════════
def run_bot(bid, cid, att=1):
    if att > 3:
        safe_send(cid, "❌ <b>Failed 3 attempts!</b> Check your code.")
        return

    bd = db.get_bot(bid)
    if not bd:
        safe_send(cid, "❌ Bot not found!")
        return

    uid = bd['user_id']
    bn = bd['bot_name']
    fp = bd['file_path']
    ef = bd['entry_file']
    ft = bd['file_type']
    sk = f"{uid}_{bn}"
    wd = fp if os.path.isdir(fp) else user_folder(uid)

    # Re-detect on first attempt
    if att == 1:
        de, dt, dr = det.report(wd)
        if de:
            ef = de
            ft = dt or 'py'
            db.update_bot(bid, entry_file=ef, file_type=ft)

    fsp = os.path.join(wd, ef)

    # Find entry file
    if not os.path.exists(fsp):
        found = False
        for root, dirs, files in os.walk(wd):
            if os.path.basename(ef) in files:
                fsp = os.path.join(root, os.path.basename(ef))
                ef = os.path.relpath(fsp, wd)
                db.update_bot(bid, entry_file=ef)
                found = True
                break
        if not found:
            af = [os.path.relpath(os.path.join(r, f), wd)
                  for r, d, fs in os.walk(wd) for f in fs if f.endswith(('.py', '.js'))]
            err = f"❌ {ef} not found!\n\nAvailable:\n"
            for f in af[:10]:
                err += f"• {f}\n"
            if not af:
                err += "(No .py or .js files)"
            safe_send(cid, err)
            return

    # Install deps on first attempt
    if att == 1:
        if ft == 'py':
            det.install_req(wd, cid)
        else:
            det.install_npm(wd, cid)

    type_icon = '🐍 Python' if ft == 'py' else '🟨 Node.js'
    safe_send(cid,
        f"🚀 <b>Starting Bot...</b>\n\n"
        f"📄 {ef}\n🔤 {type_icon}\n🔄 Attempt: {att}/3")

    try:
        lp = os.path.join(LOGS_DIR, f"{sk}.log")
        lf = open(lp, 'w', encoding='utf-8', errors='ignore')

        cmd = ['node', fsp] if ft == 'js' else [sys.executable, '-u', fsp]

        env = os.environ.copy()
        if bd.get('bot_token'):
            env['BOT_TOKEN'] = bd['bot_token']
        env['PYTHONUNBUFFERED'] = '1'

        proc = subprocess.Popen(
            cmd, cwd=wd, stdout=lf, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='ignore', env=env,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )

        with bot_lock:
            bot_scripts[sk] = {
                'process': proc, 'file_name': bn, 'bot_id': bid,
                'user_id': uid, 'start_time': datetime.now(),
                'log_file': lf, 'log_path': lp, 'entry_file': ef,
                'work_dir': wd, 'type': ft, 'attempt': att,
            }

        # Wait to check if bot stays running
        time.sleep(5)
        if proc.poll() is None:
            time.sleep(3)
            if proc.poll() is None:
                db.update_bot(bid, status='running', pid=proc.pid,
                              last_started=datetime.now().isoformat(),
                              entry_file=ef, file_type=ft)
                safe_send(cid,
                    f"✅ <b>BOT IS RUNNING!</b>\n\n"
                    f"📄 {ef}\n🆔 PID: {proc.pid}\n"
                    f"🔤 {type_icon}\n⏱️ {datetime.now().strftime('%H:%M:%S')}\n"
                    f"📊 🟢 Running")
                return

        # Bot crashed — read error
        lf.close()
        err = ""
        try:
            with open(lp, 'r', encoding='utf-8', errors='ignore') as f:
                err = f.read()[-2000:]
        except:
            pass

        # Auto-install missing Python module
        match = re.search(r"ModuleNotFoundError: No module named '([^']+)'", err)
        if match:
            cleanup_script(sk)
            if pip_install(match.group(1).split('.')[0], cid):
                time.sleep(1)
                run_bot(bid, cid, att + 1)
                return

        # Auto-install missing npm module
        match = re.search(r"Cannot find module '([^']+)'", err)
        if match and not match.group(1).startswith('.'):
            cleanup_script(sk)
            try:
                subprocess.run(['npm', 'install', match.group(1)],
                               cwd=wd, capture_output=True, timeout=60)
                time.sleep(1)
                run_bot(bid, cid, att + 1)
                return
            except:
                pass

        # Try alternate entry file
        if att == 1:
            for alt in ['app.py', 'main.py', 'bot.py', 'run.py', 'index.js', 'app.js']:
                if os.path.exists(os.path.join(wd, alt)) and alt != ef:
                    cleanup_script(sk)
                    db.update_bot(bid, entry_file=alt,
                                  file_type='js' if alt.endswith('.js') else 'py')
                    run_bot(bid, cid, att + 1)
                    return

        err_display = err[-500:] if err.strip() else 'No output'
        safe_send(cid,
            f"❌ <b>BOT CRASHED!</b>\n\n"
            f"📄 {ef}\nExit: {proc.returncode} | Attempt: {att}/3\n\n"
            f"<code>{err_display}</code>")

        db.update_bot(bid, status='crashed',
                      last_crash=datetime.now().isoformat(),
                      error_log=err[-500:])
        cleanup_script(sk)

    except Exception as e:
        logger.error(f"Run error: {e}", exc_info=True)
        report_error(e, f"run_bot(#{bid})")
        safe_send(cid, f"❌ {str(e)[:200]}")
        cleanup_script(sk)


# ═══════════════════════════════════════════
#  BACKGROUND THREADS
# ═══════════════════════════════════════════
def thread_monitor():
    """Auto-restart crashed bots"""
    while True:
        try:
            with bot_lock:
                keys = list(bot_scripts.keys())

            for sk in keys:
                with bot_lock:
                    i = bot_scripts.get(sk)
                if not i:
                    continue

                if i.get('process') and i['process'].poll() is not None:
                    bid = i.get('bot_id')
                    uid = i.get('user_id')
                    if bid:
                        db.update_bot(bid, status='crashed',
                                      last_crash=datetime.now().isoformat())
                    if uid and bid:
                        u = db.get_user(uid)
                        if u and db.is_active(uid):
                            pl = PLAN_LIMITS.get(u['plan'], PLAN_LIMITS['free'])
                            if pl.get('auto_restart') and i.get('attempt', 1) < 3:
                                cleanup_script(sk)
                                time.sleep(5)
                                threading.Thread(
                                    target=run_bot,
                                    args=(bid, uid, i.get('attempt', 1) + 1),
                                    daemon=True
                                ).start()
                                continue
                    cleanup_script(sk)

        except Exception as e:
            logger.error(f"Monitor error: {e}")
            report_error(e, "thread_monitor")
        time.sleep(30)


def thread_cleanup():
    """Memory leak prevention — clean dead scripts"""
    while True:
        try:
            with bot_lock:
                dead_keys = [
                    key for key in list(bot_scripts.keys())
                    if not is_running(key)
                    and bot_scripts[key].get('process')
                    and bot_scripts[key]['process'].poll() is not None
                ]
            for key in dead_keys:
                # Only clean up if it's been dead for a while
                with bot_lock:
                    info = bot_scripts.get(key)
                if info:
                    start = info.get('start_time', datetime.now())
                    if (datetime.now() - start).total_seconds() > 300:
                        cleanup_script(key)

            # Clean rate limiter memory
            from utils import cleanup_rate_limiter
            cleanup_rate_limiter()

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        time.sleep(300)


def thread_backup():
    """Daily database backup"""
    while True:
        try:
            time.sleep(86400)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, f"bk_{ts}.db"))
            bks = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('bk_')], reverse=True)
            for old in bks[10:]:
                try:
                    os.remove(os.path.join(BACKUP_DIR, old))
                except:
                    pass
            logger.info(f"💾 Backup created: bk_{ts}.db")
        except Exception as e:
            report_error(e, "thread_backup")


def thread_expiry():
    """Check expired subscriptions"""
    while True:
        try:
            time.sleep(3600)
            now = datetime.now().isoformat()
            expired = db.exe(
                "SELECT * FROM users WHERE subscription_end<=? AND is_lifetime=0 AND plan!='free'",
                (now,), fetch=True) or []

            for u in expired:
                uid = u['user_id']
                db.rem_sub(uid)
                for b in db.get_bots(uid):
                    sk = f"{uid}_{b['bot_name']}"
                    with bot_lock:
                        info = bot_scripts.get(sk)
                    if info:
                        kill_tree(info)
                        cleanup_script(sk)
                    db.update_bot(b['bot_id'], status='stopped')

                safe_send(uid,
                    f"⚠️ <b>Subscription Expired!</b>\n"
                    f"Your bots have been stopped.\n"
                    f"Renew to continue.\n\n{BRAND_TAG}")

            if expired:
                logger.info(f"⏰ Expired {len(expired)} subscriptions")

        except Exception as e:
            report_error(e, "thread_expiry")


def run_broadcast_thread(text, admin_id):
    """Background broadcast — no freeze"""
    users = db.get_all_users()
    sent = failed = 0

    from config import BRAND_TAG
    for u in users:
        try:
            safe_send(u['user_id'], f"📢 <b>Broadcast</b>\n\n{text}\n\n{BRAND_TAG}")
            sent += 1
        except:
            failed += 1
        time.sleep(0.05)

    safe_send(admin_id,
        f"📢 <b>Broadcast Complete!</b>\n\n"
        f"✅ Sent: {sent}\n❌ Failed: {failed}\n👥 Total: {len(users)}")
    db.admin_log(admin_id, 'broadcast', details=f"sent:{sent} failed:{failed}")


def start_all_threads():
    """Start all background threads"""
    threads = [
        ("Monitor", thread_monitor),
        ("Cleanup", thread_cleanup),
        ("Backup", thread_backup),
        ("Expiry", thread_expiry),
    ]
    for name, target in threads:
        t = threading.Thread(target=target, daemon=True, name=name)
        t.start()
        logger.info(f"🧵 Thread started: {name}")