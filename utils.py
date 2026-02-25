"""
╔═══════════════════════════════════════════╗
║  utils.py — Utilities & Helpers           ║
║  APON HOSTING PANEL v4.1                  ║
╚═══════════════════════════════════════════╝
"""

import os
import re
import sys
import json
import time
import string
import hashlib
import psutil
import subprocess
import telebot
from datetime import datetime
from collections import defaultdict

from config import (
    logger, bot_lock, rate_lock, active_lock, state_lock,
    bot_scripts, active_users, admin_ids, user_states, payment_states,
    UPLOAD_DIR, LOGS_DIR, MODULES_MAP, OWNER_ID, BRAND_TAG,
    FORCE_SUB_ENABLED, DEFAULT_FORCE_CHANNELS
)

# ═══════════════════════════════════════════
#  BOT START TIME
# ═══════════════════════════════════════════
bot_start_time = datetime.now()

# ═══════════════════════════════════════════
#  RATE LIMITER (Memory-Safe)
# ═══════════════════════════════════════════
_user_msg_times = defaultdict(list)

def rate_check(uid):
    """Thread-safe rate limiter with memory cleanup"""
    with rate_lock:
        now = time.time()
        _user_msg_times[uid] = [
            t for t in _user_msg_times[uid]
            if now - t < 60
        ][-30:]

        if len(_user_msg_times[uid]) >= 30:
            return False
        if _user_msg_times[uid] and now - _user_msg_times[uid][-1] < 0.5:
            return False

        _user_msg_times[uid].append(now)
        return True


def cleanup_rate_limiter():
    """Remove old entries from rate limiter"""
    with rate_lock:
        now = time.time()
        expired = [uid for uid, times in _user_msg_times.items()
                   if not times or now - times[-1] > 120]
        for uid in expired:
            del _user_msg_times[uid]


# ═══════════════════════════════════════════
#  SAFE MESSAGE FUNCTIONS
# ═══════════════════════════════════════════
_bot_instance = None

def set_bot_instance(bot):
    global _bot_instance
    _bot_instance = bot

def safe_send(chat_id, text, **kwargs):
    """Thread-safe message sender with HTML fallback"""
    try:
        kwargs.setdefault('parse_mode', 'HTML')
        return _bot_instance.send_message(chat_id, text, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        err = str(e).lower()
        logger.warning(f"API Error sending to {chat_id}: {e}")
        if "can't parse" in err or 'bad request' in err:
            try:
                kwargs.pop('parse_mode', None)
                return _bot_instance.send_message(chat_id, text, **kwargs)
            except:
                pass
        return None
    except Exception as e:
        logger.error(f"Send error to {chat_id}: {e}")
        return None

def safe_edit(text, chat_id, msg_id, **kwargs):
    """Thread-safe message editor"""
    try:
        kwargs.setdefault('parse_mode', 'HTML')
        return _bot_instance.edit_message_text(text, chat_id, msg_id, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        err = str(e).lower()
        if 'message is not modified' in err:
            return None
        if "can't parse" in err or 'bad request' in err:
            try:
                kwargs.pop('parse_mode', None)
                return _bot_instance.edit_message_text(text, chat_id, msg_id, **kwargs)
            except:
                pass
        logger.warning(f"Edit error: {e}")
        return None
    except Exception as e:
        logger.error(f"Edit error: {e}")
        return None

def safe_answer(call_id, text="", **kwargs):
    """Thread-safe callback answer"""
    try:
        _bot_instance.answer_callback_query(call_id, text, **kwargs)
    except:
        pass

# ═══════════════════════════════════════════
#  ERROR REPORTER (Auto Admin Notify)
# ═══════════════════════════════════════════
def report_error(e, context=""):
    """Report critical errors to all admins"""
    err = str(e)[:500]
    logger.error(f"CRITICAL [{context}]: {err}")
    for aid in admin_ids:
        try:
            safe_send(aid,
                f"⚠️ <b>SYSTEM ERROR</b>\n"
                f"📍 {context}\n\n"
                f"<code>{err}</code>\n\n"
                f"⏱️ {datetime.now().strftime('%H:%M:%S')}")
        except:
            pass

# ═══════════════════════════════════════════
#  UPTIME & FORMATTING
# ═══════════════════════════════════════════
def get_uptime():
    d = datetime.now() - bot_start_time
    h, r = divmod(d.seconds, 3600)
    m, s = divmod(r, 60)
    p = []
    if d.days:
        p.append(f"{d.days}d")
    if h:
        p.append(f"{h}h")
    p.append(f"{m}m {s}s")
    return " ".join(p)

def fmt_size(b):
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"

def gen_ref_code(uid):
    uid = int(uid)
    chars = string.digits + string.ascii_uppercase
    enc = ''
    t = uid
    if t == 0:
        enc = '0'
    else:
        while t > 0:
            enc = chars[t % 36] + enc
            t //= 36
    salt = hashlib.md5(f"{uid}_apon_hosting".encode()).hexdigest()[:2].upper()
    return f"AHP{enc}{salt}"

def time_left(e):
    if not e:
        return "♾️ Lifetime"
    try:
        end = datetime.fromisoformat(e)
        if end <= datetime.now():
            return "❌ Expired"
        d = end - datetime.now()
        if d.days > 0:
            return f"{d.days}d {d.seconds // 3600}h"
        return f"{d.seconds // 3600}h {(d.seconds % 3600) // 60}m"
    except:
        return "?"

def user_folder(uid):
    f = os.path.join(UPLOAD_DIR, str(uid))
    os.makedirs(f, exist_ok=True)
    return f

# ═══════════════════════════════════════════
#  BOT PROCESS MANAGEMENT (Thread-Safe)
# ═══════════════════════════════════════════
def is_running(sk):
    with bot_lock:
        i = bot_scripts.get(sk)
    if i and i.get('process'):
        try:
            p = psutil.Process(i['process'].pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except:
            return False
    return False

def bot_running(uid, name):
    return is_running(f"{uid}_{name}")

def cleanup_script(sk):
    with bot_lock:
        if sk in bot_scripts:
            i = bot_scripts[sk]
            try:
                lf = i.get('log_file')
                if lf and hasattr(lf, 'close') and not lf.closed:
                    lf.close()
            except:
                pass
            del bot_scripts[sk]

def kill_tree(pi):
    """Kill process and all children safely"""
    try:
        try:
            lf = pi.get('log_file')
            if lf and hasattr(lf, 'close') and not lf.closed:
                lf.close()
        except:
            pass
        p = pi.get('process')
        if p and hasattr(p, 'pid'):
            try:
                par = psutil.Process(p.pid)
                ch = par.children(recursive=True)
                for c in ch:
                    try:
                        c.terminate()
                    except:
                        pass
                psutil.wait_procs(ch, timeout=3)
                for c in ch:
                    try:
                        c.kill()
                    except:
                        pass
                try:
                    par.terminate()
                    par.wait(3)
                except psutil.TimeoutExpired:
                    par.kill()
                except psutil.NoSuchProcess:
                    pass
            except psutil.NoSuchProcess:
                pass
    except Exception as e:
        report_error(e, "kill_tree")

def bot_res(sk):
    with bot_lock:
        i = bot_scripts.get(sk)
    if not i or not i.get('process'):
        return 0, 0
    try:
        p = psutil.Process(i['process'].pid)
        return round(p.memory_info().rss / (1024 ** 2), 1), round(p.cpu_percent(0.3), 1)
    except:
        return 0, 0

# ═══════════════════════════════════════════
#  SYSTEM STATS
# ═══════════════════════════════════════════
def sys_stats():
    try:
        c = psutil.cpu_percent(interval=1)
        m = psutil.virtual_memory()
        d = psutil.disk_usage('/')
        return {
            'cpu': c, 'mem': m.percent,
            'disk': round(d.used / d.total * 100, 1),
            'up': get_uptime(),
            'mem_total': fmt_size(m.total),
            'disk_total': fmt_size(d.total)
        }
    except:
        return {'cpu': 0, 'mem': 0, 'disk': 0, 'up': get_uptime(), 'mem_total': '?', 'disk_total': '?'}

# ═══════════════════════════════════════════
#  FORCE SUBSCRIBE
# ═══════════════════════════════════════════
def check_joined(uid):
    if not FORCE_SUB_ENABLED:
        return True, []
    if uid == OWNER_ID or uid in admin_ids:
        return True, []

    from database import db

    channels = db.get_active_channels()
    if not channels:
        ch_list = [(u, n) for u, n in DEFAULT_FORCE_CHANNELS.items()]
    else:
        ch_list = [(c['channel_username'], c['channel_name']) for c in channels]

    not_joined = []
    for cu, cn in ch_list:
        try:
            mem = _bot_instance.get_chat_member(f"@{cu}", uid)
            if mem.status in ['left', 'kicked']:
                not_joined.append((cu, cn))
        except telebot.apihelper.ApiTelegramException:
            not_joined.append((cu, cn))
        except:
            continue
    return len(not_joined) == 0, not_joined

# ═══════════════════════════════════════════
#  LOADING ANIMATIONS
# ═══════════════════════════════════════════
def loading_msg(cid, final_text, atype="loading"):
    try:
        icons = {
            "loading": "⏳", "upload": "📤", "run": "🚀",
            "stop": "🛑", "install": "📦", "verify": "🔍", "pay": "💳"
        }
        icon = icons.get(atype, "⏳")
        msg = _bot_instance.send_message(cid, f"{icon} Processing...")
        time.sleep(1)
        safe_edit(final_text, cid, msg.message_id)
        return msg
    except:
        return safe_send(cid, final_text)

# ═══════════════════════════════════════════
#  SMART ENTRY DETECTOR
# ═══════════════════════════════════════════
class Detector:
    PY = ['main.py', 'app.py', 'bot.py', 'run.py', 'start.py', 'server.py', 'index.py', '__main__.py']
    JS = ['index.js', 'app.js', 'bot.js', 'main.js', 'server.js', 'start.js', 'run.js']

    @staticmethod
    def detect(d):
        if not os.path.isdir(d):
            if os.path.isfile(d):
                return os.path.basename(d), d.rsplit('.', 1)[-1].lower(), 'exact'
            return None, None, None

        top = os.listdir(d)
        for e in Detector.PY:
            if e in top and os.path.isfile(os.path.join(d, e)):
                return e, 'py', 'high'
        for e in Detector.JS:
            if e in top and os.path.isfile(os.path.join(d, e)):
                return e, 'js', 'high'

        pj = os.path.join(d, 'package.json')
        if os.path.exists(pj):
            try:
                with open(pj) as f:
                    pkg = json.load(f)
                if 'main' in pkg and os.path.exists(os.path.join(d, pkg['main'])):
                    return pkg['main'], pkg['main'].rsplit('.', 1)[-1].lower(), 'high'
                if 'scripts' in pkg and 'start' in pkg['scripts']:
                    cmd = pkg['scripts']['start']
                    m = re.search(r'node\s+(\S+\.js)', cmd)
                    if m and os.path.exists(os.path.join(d, m.group(1))):
                        return m.group(1), 'js', 'high'
                    m = re.search(r'python[3]?\s+(\S+\.py)', cmd)
                    if m and os.path.exists(os.path.join(d, m.group(1))):
                        return m.group(1), 'py', 'high'
            except:
                pass

        pf = os.path.join(d, 'Procfile')
        if os.path.exists(pf):
            try:
                with open(pf) as f:
                    c = f.read()
                m = re.search(r'(?:worker|web):\s*python[3]?\s+(\S+\.py)', c)
                if m and os.path.exists(os.path.join(d, m.group(1))):
                    return m.group(1), 'py', 'high'
                m = re.search(r'(?:worker|web):\s*node\s+(\S+\.js)', c)
                if m and os.path.exists(os.path.join(d, m.group(1))):
                    return m.group(1), 'js', 'high'
            except:
                pass

        for root, dirs, files in os.walk(d):
            if os.path.relpath(root, d).count(os.sep) > 1:
                continue
            for e in Detector.PY:
                if e in files:
                    return os.path.relpath(os.path.join(root, e), d), 'py', 'medium'
            for e in Detector.JS:
                if e in files:
                    return os.path.relpath(os.path.join(root, e), d), 'js', 'medium'

        pyf, jsf = [], []
        for root, dirs, files in os.walk(d):
            if os.path.relpath(root, d).count(os.sep) > 1:
                continue
            for f in files:
                fp = os.path.join(root, f)
                rp = os.path.relpath(fp, d)
                if f.endswith('.py'):
                    pyf.append((rp, fp))
                elif f.endswith('.js'):
                    jsf.append((rp, fp))

        pi = ['infinity_polling', 'polling()', 'bot.polling', 'app.run(', 'if __name__', 'telebot.TeleBot', 'Bot(token']
        for rp, fp in pyf:
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    c = f.read(5000)
                if sum(1 for x in pi if x in c) >= 2:
                    return rp, 'py', 'medium'
            except:
                pass

        ji = ['require(', 'app.listen', 'bot.launch', 'client.login', 'express()']
        for rp, fp in jsf:
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    c = f.read(5000)
                if sum(1 for x in ji if x in c) >= 2:
                    return rp, 'js', 'medium'
            except:
                pass

        if pyf:
            return pyf[0][0], 'py', 'low'
        if jsf:
            return jsf[0][0], 'js', 'low'
        return None, None, None

    @staticmethod
    def install_req(d, cid=None):
        r = os.path.join(d, 'requirements.txt')
        if os.path.exists(r):
            if cid:
                safe_send(cid, "📦 Installing requirements...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', r, '--quiet'],
                               capture_output=True, text=True, timeout=300, cwd=d)
            except Exception as e:
                report_error(e, "install_req")
        return True

    @staticmethod
    def install_npm(d, cid=None):
        if os.path.exists(os.path.join(d, 'package.json')) and not os.path.exists(os.path.join(d, 'node_modules')):
            if cid:
                safe_send(cid, "📦 npm install...")
            try:
                subprocess.run(['npm', 'install', '--production'],
                               capture_output=True, text=True, timeout=300, cwd=d)
            except Exception as e:
                report_error(e, "install_npm")
        return True

    @staticmethod
    def report(d):
        e, ft, cf = Detector.detect(d)
        if not e:
            return None, None, "❌ No runnable file!"
        ci = {'exact': '🎯 Exact', 'high': '✅ High', 'medium': '🟡 Medium', 'low': '⚠️ Low'}
        ti = {'py': '🐍 Python', 'js': '🟨 Node.js'}
        return e, ft, f"📄 Entry: {e}\n🔤 Type: {ti.get(ft, ft)}\n🎯 Confidence: {ci.get(cf, cf)}"


det = Detector()