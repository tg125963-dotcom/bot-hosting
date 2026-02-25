"""
╔═══════════════════════════════════════════╗
║  database.py — Thread-Safe Database       ║
║  APON HOSTING PANEL v4.1                  ║
╚═══════════════════════════════════════════╝
"""

import sqlite3
import threading
from datetime import datetime, timedelta

from config import DB_PATH, PLAN_LIMITS, OWNER_ID, admin_ids, logger


class DB:
    _lock = threading.Lock()

    def __init__(self):
        self.path = DB_PATH
        self._init()

    def _conn(self):
        c = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        return c

    def exe(self, q, p=(), fetch=False, one=False):
        with self._lock:
            c = self._conn()
            cur = c.cursor()
            try:
                cur.execute(q, p)
                if fetch:
                    r = [dict(x) for x in cur.fetchall()]
                    c.close()
                    return r
                if one:
                    x = cur.fetchone()
                    c.close()
                    return dict(x) if x else None
                c.commit()
                lid = cur.lastrowid
                c.close()
                return lid
            except Exception as e:
                c.close()
                logger.error(f"DB Error: {e}")
                return None

    def _init(self):
        self.exe("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            full_name TEXT DEFAULT '',
            language TEXT DEFAULT 'en',
            plan TEXT DEFAULT 'free',
            subscription_end TEXT,
            is_lifetime INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT DEFAULT '',
            wallet_balance REAL DEFAULT 0.0,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            referral_level TEXT DEFAULT 'bronze',
            referral_earnings REAL DEFAULT 0.0,
            total_spent REAL DEFAULT 0.0,
            created_at TEXT DEFAULT(datetime('now')),
            last_active TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS bots(
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_name TEXT NOT NULL,
            bot_token TEXT DEFAULT '',
            file_path TEXT NOT NULL,
            entry_file TEXT DEFAULT 'main.py',
            file_type TEXT DEFAULT 'py',
            status TEXT DEFAULT 'stopped',
            pid INTEGER,
            restarts_today INTEGER DEFAULT 0,
            total_restarts INTEGER DEFAULT 0,
            auto_restart INTEGER DEFAULT 1,
            last_started TEXT,
            last_stopped TEXT,
            last_crash TEXT,
            error_log TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            detection_confidence TEXT DEFAULT '',
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS payments(
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            method TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            plan TEXT NOT NULL,
            duration_days INTEGER DEFAULT 30,
            status TEXT DEFAULT 'pending',
            approved_by INTEGER,
            created_at TEXT DEFAULT(datetime('now')),
            processed_at TEXT
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS referrals(
            ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            bonus_days INTEGER DEFAULT 0,
            commission REAL DEFAULT 0,
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS wallet_tx(
            tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            tx_type TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS admin_logs(
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_user INTEGER,
            details TEXT DEFAULT '',
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS force_channels(
            channel_id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_username TEXT UNIQUE NOT NULL,
            channel_name TEXT DEFAULT '',
            added_by INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS tickets(
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            admin_reply TEXT DEFAULT '',
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS notifications(
            notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'Notification',
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        self.exe("""CREATE TABLE IF NOT EXISTS promo_codes(
            promo_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_pct INTEGER DEFAULT 10,
            max_uses INTEGER DEFAULT 100,
            used_count INTEGER DEFAULT 0,
            created_by INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT(datetime('now'))
        )""")

        logger.info("✅ All DB tables ready")

    # ════════════════════════════════
    #  USERS
    # ════════════════════════════════
    def get_user(self, uid):
        return self.exe("SELECT * FROM users WHERE user_id=?", (uid,), one=True)

    def create_user(self, uid, un='', fn='', rc='', rb=None):
        self.exe("INSERT OR IGNORE INTO users(user_id,username,full_name,referral_code,referred_by) VALUES(?,?,?,?,?)",
                 (uid, un, fn, rc, rb))

    def update_user(self, uid, **kw):
        if not kw:
            return
        self.exe(f"UPDATE users SET {','.join(f'{k}=?' for k in kw)} WHERE user_id=?",
                 list(kw.values()) + [uid])

    def get_all_users(self):
        return self.exe("SELECT * FROM users", fetch=True) or []

    def ban(self, uid, r=''):
        self.update_user(uid, is_banned=1, ban_reason=r)

    def unban(self, uid):
        self.update_user(uid, is_banned=0, ban_reason='')

    def set_sub(self, uid, plan, days=30):
        if plan == 'lifetime':
            self.update_user(uid, plan=plan, is_lifetime=1, subscription_end=None)
        else:
            self.update_user(uid, plan=plan, is_lifetime=0,
                             subscription_end=(datetime.now() + timedelta(days=days)).isoformat())

    def rem_sub(self, uid):
        self.update_user(uid, plan='free', is_lifetime=0, subscription_end=None)

    def is_active(self, uid):
        u = self.get_user(uid)
        if not u:
            return False
        if u['is_lifetime'] or u['plan'] == 'free':
            return True
        if u['subscription_end']:
            try:
                return datetime.fromisoformat(u['subscription_end']) > datetime.now()
            except:
                return False
        return False

    def get_plan(self, uid):
        u = self.get_user(uid)
        if not u:
            return PLAN_LIMITS['free']
        if uid == OWNER_ID or uid in admin_ids:
            return PLAN_LIMITS['lifetime']
        return PLAN_LIMITS.get(u['plan'], PLAN_LIMITS['free'])

    # ════════════════════════════════
    #  BOTS
    # ════════════════════════════════
    def add_bot(self, uid, name, path, entry='main.py', ft='py', tok='', sz=0, conf=''):
        return self.exe(
            "INSERT INTO bots(user_id,bot_name,file_path,entry_file,file_type,bot_token,file_size,detection_confidence) VALUES(?,?,?,?,?,?,?,?)",
            (uid, name, path, entry, ft, tok, sz, conf))

    def get_bots(self, uid):
        return self.exe("SELECT * FROM bots WHERE user_id=?", (uid,), fetch=True) or []

    def get_bot(self, bid):
        return self.exe("SELECT * FROM bots WHERE bot_id=?", (bid,), one=True)

    def update_bot(self, bid, **kw):
        if not kw:
            return
        self.exe(f"UPDATE bots SET {','.join(f'{k}=?' for k in kw)} WHERE bot_id=?",
                 list(kw.values()) + [bid])

    def del_bot(self, bid):
        self.exe("DELETE FROM bots WHERE bot_id=?", (bid,))

    def bot_count(self, uid):
        return (self.exe("SELECT COUNT(*) as c FROM bots WHERE user_id=?", (uid,), one=True) or {}).get('c', 0)

    # ════════════════════════════════
    #  PAYMENTS
    # ════════════════════════════════
    def add_pay(self, uid, amt, method, trx, plan, days=30):
        return self.exe(
            "INSERT INTO payments(user_id,amount,method,transaction_id,plan,duration_days) VALUES(?,?,?,?,?,?)",
            (uid, amt, method, trx, plan, days))

    def pending_pay(self):
        return self.exe("SELECT * FROM payments WHERE status='pending' ORDER BY created_at DESC", fetch=True) or []

    def get_pay(self, pid):
        return self.exe("SELECT * FROM payments WHERE payment_id=?", (pid,), one=True)

    def approve_pay(self, pid, aid):
        p = self.get_pay(pid)
        if not p:
            return None
        self.exe("UPDATE payments SET status='approved',approved_by=?,processed_at=datetime('now') WHERE payment_id=?",
                 (aid, pid))
        self.set_sub(p['user_id'], p['plan'], p['duration_days'])
        return p

    def reject_pay(self, pid, aid):
        self.exe("UPDATE payments SET status='rejected',approved_by=?,processed_at=datetime('now') WHERE payment_id=?",
                 (aid, pid))

    # ════════════════════════════════
    #  REFERRALS
    # ════════════════════════════════
    def add_ref(self, rr, rd, days=3, comm=20):
        self.exe("INSERT INTO referrals(referrer_id,referred_id,bonus_days,commission) VALUES(?,?,?,?)",
                 (rr, rd, days, comm))
        u = self.get_user(rr)
        if u:
            nc = u['referral_count'] + 1
            lv = 'diamond' if nc >= 100 else 'platinum' if nc >= 50 else 'gold' if nc >= 25 else 'silver' if nc >= 10 else 'bronze'
            self.update_user(rr, referral_count=nc, referral_earnings=u['referral_earnings'] + comm,
                             wallet_balance=u['wallet_balance'] + comm, referral_level=lv)

    def ref_board(self, lim=10):
        return self.exe("SELECT * FROM users ORDER BY referral_count DESC LIMIT ?", (lim,), fetch=True) or []

    def user_refs(self, uid):
        return self.exe("SELECT * FROM referrals WHERE referrer_id=?", (uid,), fetch=True) or []

    # ════════════════════════════════
    #  WALLET
    # ════════════════════════════════
    def wallet_tx(self, uid, amt, tt, desc=''):
        self.exe("INSERT INTO wallet_tx(user_id,amount,tx_type,description) VALUES(?,?,?,?)",
                 (uid, amt, tt, desc))
        if tt in ('credit', 'referral', 'refund', 'bonus'):
            self.exe("UPDATE users SET wallet_balance=wallet_balance+? WHERE user_id=?", (amt, uid))
        elif tt in ('debit', 'withdraw', 'purchase'):
            self.exe("UPDATE users SET wallet_balance=wallet_balance-? WHERE user_id=?", (amt, uid))

    def wallet_hist(self, uid, lim=20):
        return self.exe("SELECT * FROM wallet_tx WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                         (uid, lim), fetch=True) or []

    # ════════════════════════════════
    #  FORCE CHANNELS
    # ════════════════════════════════
    def add_channel(self, username, name='', added_by=None):
        username = username.strip().lstrip('@').lower()
        ex = self.exe("SELECT * FROM force_channels WHERE channel_username=?", (username,), one=True)
        if ex:
            self.exe("UPDATE force_channels SET is_active=1,channel_name=? WHERE channel_username=?",
                     (name or username, username))
            return ex['channel_id']
        return self.exe("INSERT INTO force_channels(channel_username,channel_name,added_by) VALUES(?,?,?)",
                        (username, name or username, added_by))

    def remove_channel(self, username):
        self.exe("UPDATE force_channels SET is_active=0 WHERE channel_username=?",
                 (username.strip().lstrip('@').lower(),))

    def get_active_channels(self):
        return self.exe("SELECT * FROM force_channels WHERE is_active=1", fetch=True) or []

    def get_all_channels(self):
        return self.exe("SELECT * FROM force_channels ORDER BY is_active DESC", fetch=True) or []

    def toggle_channel(self, cid):
        ch = self.exe("SELECT * FROM force_channels WHERE channel_id=?", (cid,), one=True)
        if ch:
            ns = 0 if ch['is_active'] else 1
            self.exe("UPDATE force_channels SET is_active=? WHERE channel_id=?", (ns, cid))
            return ns
        return None

    def delete_channel(self, cid):
        self.exe("DELETE FROM force_channels WHERE channel_id=?", (cid,))

    # ════════════════════════════════
    #  TICKETS
    # ════════════════════════════════
    def add_ticket(self, uid, subj, msg):
        return self.exe("INSERT INTO tickets(user_id,subject,message) VALUES(?,?,?)", (uid, subj, msg))

    def open_tickets(self):
        return self.exe("SELECT * FROM tickets WHERE status='open' ORDER BY created_at DESC", fetch=True) or []

    def reply_ticket(self, tid, reply):
        self.exe("UPDATE tickets SET admin_reply=?,status='replied' WHERE ticket_id=?", (reply, tid))

    # ════════════════════════════════
    #  NOTIFICATIONS
    # ════════════════════════════════
    def add_notif(self, uid, title, message):
        return self.exe("INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)", (uid, title, message))

    def get_notifs(self, uid, lim=10):
        return self.exe("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                         (uid, lim), fetch=True) or []

    def unread_count(self, uid):
        r = self.exe("SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (uid,), one=True)
        return r['c'] if r else 0

    def mark_read(self, uid):
        self.exe("UPDATE notifications SET is_read=1 WHERE user_id=?", (uid,))

    # ════════════════════════════════
    #  ADMIN
    # ════════════════════════════════
    def admin_log(self, aid, act, tgt=None, det=''):
        self.exe("INSERT INTO admin_logs(admin_id,action,target_user,details) VALUES(?,?,?,?)",
                 (aid, act, tgt, det))

    # ════════════════════════════════
    #  STATS
    # ════════════════════════════════
    def stats(self):
        tu = (self.exe("SELECT COUNT(*) as c FROM users", one=True) or {}).get('c', 0)
        tb = (self.exe("SELECT COUNT(*) as c FROM bots", one=True) or {}).get('c', 0)
        pp = (self.exe("SELECT COUNT(*) as c FROM payments WHERE status='pending'", one=True) or {}).get('c', 0)
        rv = (self.exe("SELECT COALESCE(SUM(amount),0) as s FROM payments WHERE status='approved'", one=True) or {}).get('s', 0)
        td = (self.exe("SELECT COUNT(*) as c FROM users WHERE date(created_at)=date('now')", one=True) or {}).get('c', 0)
        ac = (self.exe("SELECT COUNT(*) as c FROM users WHERE plan!='free' AND(is_lifetime=1 OR subscription_end>datetime('now'))", one=True) or {}).get('c', 0)
        return {'users': tu, 'bots': tb, 'pending': pp, 'revenue': rv, 'today': td, 'active_subs': ac}


# Global instance
db = DB()