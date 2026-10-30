# vote.py
# -----------------------------------------------------------------------
# Professional Telegram Channel Poll Bot — Top 3 Live Leaderboard Edition
# (English Language Version)
# -----------------------------------------------------------------------

import html
import json
import random
import sqlite3
import threading
import time
import traceback
import requests

# ======================================================================
# CONFIG
# ======================================================================

BOT_TOKEN = "8944212122:AAGZzFuVsYg2k2XtnZuGUFEtqbmdbeI2g8s"      # from @BotFather

OWNER_IDS = [
    8573155257,  # <-- your numeric Telegram user ID
]

# Credit & promo settings
CREDIT_BOT_USERNAME = "Bot"
PROMO_BOT_URL = "https://t.me/"
PROMO_BUTTON_TEXT = "🗳 Create a Free Poll"

DB_PATH = "pollbot.db"
POLL_TIMEOUT = 30
MIN_OPTIONS = 2
MAX_OPTIONS = 50

API_ROOT = "https://api.telegram.org/bot{token}/{method}"

# Random emoji pool
EMOJI_POOL = [
    "🔥", "❤️", "💎", "🌟", "🎯", "🎲", "🎉", "🏆", "🥇", "🎊",
    "🍀", "🌈", "💥", "🎈", "🎵", "🎨", "🚀", "🌙", "⭐️", "🦋",
    "🌺", "🍭", "🔔", "✨", "🌸", "🎺", "🍬", "🧿", "🎀", "🌻",
]

COLOR_CYCLE = ["primary", "success", "danger"]

# ======================================================================
# TELEGRAM API WRAPPER
# ======================================================================

class TelegramAPI:
    def __init__(self, token):
        self.token = token

    def _url(self, method):
        return API_ROOT.format(token=self.token, method=method)

    def call(self, method, files=None, **params):
        payload = {}
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                payload[k] = json.dumps(v)
            else:
                payload[k] = v
        resp = requests.post(self._url(method), data=payload, files=files, timeout=60)
        data = resp.json()
        if not data.get("ok"):
            desc = data.get("description", "")
            if "message is not modified" in desc.lower():
                return True
            raise RuntimeError(f"{method} failed: {desc}")
        return data["result"]

    def get_me(self):
        return self.call("getMe")

    def get_updates(self, offset=None, timeout=30):
        return self.call("getUpdates", offset=offset, timeout=timeout,
                          allowed_updates=["message", "callback_query", "chat_member"])

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        return self.call("sendMessage", chat_id=chat_id, text=text,
                          reply_markup=reply_markup, parse_mode=parse_mode)

    def send_photo(self, chat_id, photo_file_id, caption, reply_markup=None, parse_mode="HTML"):
        return self.call("sendPhoto", chat_id=chat_id, photo=photo_file_id,
                          caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
        return self.call("editMessageText", chat_id=chat_id, message_id=message_id,
                          text=text, reply_markup=reply_markup, parse_mode=parse_mode)

    def edit_message_caption(self, chat_id, message_id, caption, reply_markup=None, parse_mode="HTML"):
        return self.call("editMessageCaption", chat_id=chat_id, message_id=message_id,
                          caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        return self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        try:
            return self.call("answerCallbackQuery", callback_query_id=callback_query_id,
                              text=text, show_alert=show_alert)
        except Exception:
            return False

    def delete_message(self, chat_id, message_id):
        try:
            return self.call("deleteMessage", chat_id=chat_id, message_id=message_id)
        except Exception:
            return False

    def get_chat(self, chat_id):
        return self.call("getChat", chat_id=chat_id)

    def get_chat_member(self, chat_id, user_id):
        return self.call("getChatMember", chat_id=chat_id, user_id=user_id)

    def get_user_profile_photos(self, user_id, limit=1):
        try:
            return self.call("getUserProfilePhotos", user_id=user_id, limit=limit)
        except Exception:
            return {"total_count": 0}


def safe_delete(chat_id, message_id):
    if chat_id and message_id:
        try:
            api.delete_message(chat_id, message_id)
        except Exception:
            pass


def inline_button(text, callback_data=None, url=None, style=None):
    btn = {"text": text}
    if url:
        btn["url"] = url
    else:
        btn["callback_data"] = callback_data
    if style:
        btn["style"] = style
    return btn


def inline_keyboard(rows):
    return {"inline_keyboard": rows}


def reply_button(text, style=None):
    btn = {"text": text}
    if style:
        btn["style"] = style
    return btn


def reply_keyboard(rows, resize=True, one_time=False):
    return {
        "keyboard": rows,
        "resize_keyboard": resize,
        "one_time_keyboard": one_time
    }


api = TelegramAPI(BOT_TOKEN)

# ======================================================================
# DATABASE
# ======================================================================

_lock = threading.Lock()
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row


def init_db():
    with _lock:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS polls (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id        INTEGER NOT NULL,
                channel_id        INTEGER NOT NULL,
                channel_title     TEXT,
                channel_username  TEXT,
                question          TEXT NOT NULL,
                photo_file_id     TEXT,
                options           TEXT NOT NULL,
                emojis            TEXT NOT NULL,
                message_id        INTEGER,
                status            TEXT NOT NULL DEFAULT 'open',
                winner_index      INTEGER,
                created_at        INTEGER,
                photo_check       INTEGER DEFAULT 1,
                username_check    INTEGER DEFAULT 1,
                fake_filter       INTEGER DEFAULT 1,
                end_time          INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS votes (
                poll_id       INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                user_name     TEXT,
                option_index  INTEGER NOT NULL,
                voted_at      INTEGER,
                PRIMARY KEY (poll_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                joined_at   INTEGER
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        cur = conn.execute("PRAGMA table_info(polls)")
        existing_cols = [r["name"] for r in cur.fetchall()]
        for col, col_type in [("photo_check", "INTEGER DEFAULT 1"), 
                              ("username_check", "INTEGER DEFAULT 1"), 
                              ("fake_filter", "INTEGER DEFAULT 1"),
                              ("end_time", "INTEGER DEFAULT 0")]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE polls ADD COLUMN {col} {col_type}")
        conn.commit()


def get_setting(key, default=""):
    with _lock:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with _lock:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
        conn.commit()


def create_poll(creator_id, channel_id, channel_title, channel_username,
                 question, photo_file_id, options, photo_check=1, username_check=1, fake_filter=1, end_time=0):
    emojis = random.sample(EMOJI_POOL, len(options)) if len(options) <= len(EMOJI_POOL) \
        else [random.choice(EMOJI_POOL) for _ in options]
    with _lock:
        cur = conn.execute(
            """INSERT INTO polls
               (creator_id, channel_id, channel_title, channel_username,
                question, photo_file_id, options, emojis, status, created_at,
                photo_check, username_check, fake_filter, end_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)""",
            (creator_id, channel_id, channel_title, channel_username,
             question, photo_file_id, json.dumps(options), json.dumps(emojis),
             int(time.time()), photo_check, username_check, fake_filter, end_time),
        )
        conn.commit()
        return cur.lastrowid


def set_poll_message_id(poll_id, message_id):
    with _lock:
        conn.execute("UPDATE polls SET message_id = ? WHERE id = ?", (message_id, poll_id))
        conn.commit()


def get_poll(poll_id):
    with _lock:
        row = conn.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
        return dict(row) if row else None


def update_poll_options(poll_id, options, emojis):
    with _lock:
        conn.execute("UPDATE polls SET options = ?, emojis = ? WHERE id = ?",
                     (json.dumps(options), json.dumps(emojis), poll_id))
        conn.commit()


def list_open_polls_by_creator(creator_id):
    with _lock:
        rows = conn.execute(
            "SELECT * FROM polls WHERE creator_id = ? AND status = 'open' ORDER BY id DESC",
            (creator_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_all_open_polls():
    with _lock:
        rows = conn.execute(
            "SELECT * FROM polls WHERE status = 'open' ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def list_distinct_channels():
    with _lock:
        rows = conn.execute(
            "SELECT channel_id, channel_title, channel_username, COUNT(*) as poll_count FROM polls GROUP BY channel_id"
        ).fetchall()
        return [dict(r) for r in rows]


def cast_vote(poll_id, user_id, user_name, option_index):
    with _lock:
        existing = conn.execute(
            "SELECT 1 FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO votes (poll_id, user_id, user_name, option_index, voted_at) VALUES (?, ?, ?, ?, ?)",
            (poll_id, user_id, user_name, option_index, int(time.time())),
        )
        conn.commit()
        return True


def add_boosted_votes(poll_id, option_index, count):
    with _lock:
        cur_min = conn.execute("SELECT MIN(user_id) as min_id FROM votes WHERE poll_id = ?", (poll_id,)).fetchone()
        base_id = (cur_min["min_id"] if cur_min and cur_min["min_id"] and cur_min["min_id"] < 0 else 0) - 1
        
        now = int(time.time())
        for i in range(count):
            uid = base_id - i
            conn.execute(
                """INSERT INTO votes (poll_id, user_id, user_name, option_index, voted_at)
                   VALUES (?, ?, 'Boosted User', ?, ?)""",
                (poll_id, uid, option_index, now),
            )
        conn.commit()


def retract_vote(poll_id, user_id):
    with _lock:
        cur = conn.execute(
            "DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0


def vote_counts(poll_id, num_options):
    with _lock:
        rows = conn.execute(
            "SELECT option_index, COUNT(*) as c FROM votes WHERE poll_id = ? GROUP BY option_index",
            (poll_id,),
        ).fetchall()
    counts = [0] * num_options
    for r in rows:
        idx = r["option_index"]
        if 0 <= idx < num_options:
            counts[idx] = r["c"]
    return counts


def reduce_votes_count(poll_id, option_index, amount_to_reduce):
    with _lock:
        rows = conn.execute(
            "SELECT user_id FROM votes WHERE poll_id = ? AND option_index = ? ORDER BY user_id ASC LIMIT ?",
            (poll_id, option_index, amount_to_reduce),
        ).fetchall()
        for r in rows:
            conn.execute("DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, r["user_id"]))
        conn.commit()
        return len(rows)


def close_poll_db(poll_id, winner_index):
    with _lock:
        conn.execute(
            "UPDATE polls SET status = 'closed', winner_index = ? WHERE id = ?",
            (winner_index, poll_id),
        )
        conn.commit()


def record_user(user_id, username, first_name):
    with _lock:
        conn.execute(
            """INSERT INTO users (user_id, username, first_name, joined_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username = excluded.username,
                 first_name = excluded.first_name""",
            (user_id, username, first_name, int(time.time())),
        )
        conn.commit()


def list_all_users():
    with _lock:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


def stats_counts():
    with _lock:
        total_polls = conn.execute("SELECT COUNT(*) c FROM polls").fetchone()["c"]
        open_polls = conn.execute("SELECT COUNT(*) c FROM polls WHERE status='open'").fetchone()["c"]
        closed_polls = total_polls - open_polls
        total_votes = conn.execute("SELECT COUNT(*) c FROM votes").fetchone()["c"]
        total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_channels = conn.execute("SELECT COUNT(DISTINCT channel_id) c FROM polls").fetchone()["c"]
    return {
        "total_polls": total_polls,
        "open_polls": open_polls,
        "closed_polls": closed_polls,
        "total_votes": total_votes,
        "total_users": total_users,
        "total_channels": total_channels,
    }

# ======================================================================
# STATE & HELPERS (Anti-Flood & Global State)
# ======================================================================

STATE = {}
BOT_ID = None
BOT_USERNAME = None

USER_LAST_ACTION = {}
FLOOD_COOLDOWN = 1.2  # more than one click within 1.2 seconds will be ignored


def is_flooding(user_id):
    now = time.time()
    last = USER_LAST_ACTION.get(user_id, 0)
    if now - last < FLOOD_COOLDOWN:
        return True
    USER_LAST_ACTION[user_id] = now
    return False


def esc(text):
    return html.escape(str(text or ""))


def is_owner(user_id):
    return user_id in OWNER_IDS


def reset_state(user_id):
    STATE.pop(user_id, None)


def get_state(user_id):
    return STATE.get(user_id)


def set_step(user_id, step, data=None):
    st = STATE.get(user_id, {"data": {}})
    st["step"] = step
    if data is not None:
        st["data"].update(data)
    STATE[user_id] = st


def bar(pct, length=10):
    filled = max(0, min(length, round(pct / 100 * length)))
    return "█" * filled + "─" * (length - filled)


def is_user_channel_member(channel_id, user_id):
    try:
        member = api.get_chat_member(channel_id, user_id)
        return member.get("status") in ("creator", "administrator", "member", "restricted")
    except Exception:
        return False


def get_force_channels_list():
    raw = get_setting("force_channel", "").strip()
    if not raw:
        return []
    return [c.strip() for c in raw.replace("\n", ",").split(",") if c.strip()]


def check_force_sub(user_id):
    if is_owner(user_id):
        return True
    channels = get_force_channels_list()
    if not channels:
        return True
    for ch in channels:
        try:
            chat = api.get_chat(ch)
            if not is_user_channel_member(chat["id"], user_id):
                return False
        except Exception:
            continue
    return True


def send_force_sub_message(chat_id):
    channels = get_force_channels_list()
    rows = []
    current_row = []
    
    for i, ch in enumerate(channels, start=1):
        link = ch if ch.startswith("https://") else f"https://t.me/{ch.lstrip('@')}"
        current_row.append(inline_button(f"📣 Channel {i}", url=link, style="primary"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)

    rows.append([inline_button("🔄 I Have Joined (Verify)", callback_data="verify_force_sub", style="success")])

    api.send_message(
        chat_id,
        "⚠️ <b>To use this bot, you must join our official channel(s)!</b>\n\n"
        "Please join the channel(s) below and tap the 'Verify' button:",
        reply_markup=inline_keyboard(rows)
    )

# ---------------------------------------------------------------- Dynamic Fake ID Detector

def is_account_newer_than_configured_days(user_id):
    if user_id <= 0:
        return False
    
    try:
        allowed_days = float(get_setting("fake_id_days", "7"))
    except ValueError:
        allowed_days = 7.0
    
    anchor_id = 7500000000
    anchor_time = 1730419200  # 2024-11-01 00:00:00 UTC
    rate_per_sec = 31.25

    if user_id < anchor_id:
        return False

    estimated_created_time = anchor_time + ((user_id - anchor_id) / rate_per_sec)
    age_seconds = time.time() - estimated_created_time
    age_days = age_seconds / 86400

    return age_days < allowed_days

# ---------------------------------------------------------------- Keyboards

def main_menu_keyboard(user_id):
    rows = [
        [reply_button("📣 Create Channel Poll", style="success")],
        [reply_button("✏️ Edit Poll", style="primary")],
        [
            reply_button("🛒 Buy Code", style="primary"),
            reply_button("📞 Support", style="primary")
        ],
    ]
    if is_owner(user_id):
        rows.append([reply_button("🛠️ Admin Panel", style="danger")])
    return reply_keyboard(rows)


def cancel_keyboard():
    return reply_keyboard([[reply_button("❌ Cancel", style="danger")]])


def photo_step_keyboard():
    return reply_keyboard([
        [reply_button("🟢 Text Only", style="success")],
        [reply_button("❌ Cancel", style="danger")],
    ])


def confirm_question_inline_keyboard():
    return inline_keyboard([
        [
            inline_button("✅ Yes, Correct", callback_data="confirm_q:yes", style="success"),
            inline_button("📝 Rewrite", callback_data="confirm_q:edit", style="primary")
        ],
        [
            inline_button("❌ Cancel", callback_data="confirm_q:cancel", style="danger")
        ]
    ])


def build_timer_keyboard():
    return inline_keyboard([
        [
            inline_button("⏱️ 1 Hour", callback_data="timer_set:1h", style="primary"),
            inline_button("⏱️ 6 Hours", callback_data="timer_set:6h", style="primary"),
            inline_button("⏱️ 12 Hours", callback_data="timer_set:12h", style="primary")
        ],
        [
            inline_button("📅 1 Day", callback_data="timer_set:1d", style="primary"),
            inline_button("📅 3 Days", callback_data="timer_set:3d", style="primary"),
            inline_button("📅 7 Days", callback_data="timer_set:7d", style="primary")
        ],
        [
            inline_button("♾️ Unlimited (No Timer)", callback_data="timer_set:none", style="success")
        ],
        [
            inline_button("❌ Cancel", callback_data="timer_set:cancel", style="danger")
        ]
    ])


def build_preview_markup(photo_check, username_check, fake_filter):
    def get_toggle_btn(title, key, val):
        badge = "🟢 ON" if val else "🔴 OFF"
        style = "success" if val else "danger"
        return inline_button(f"{title}: {badge}", callback_data=f"preview_toggle:{key}", style=style)

    return inline_keyboard([
        [get_toggle_btn("🖼️ Photo Check", "photo", photo_check)],
        [get_toggle_btn("🔰 Username Check", "username", username_check)],
        [get_toggle_btn("🚫 New ID Filter (Fake)", "fake", fake_filter)],
        [inline_button("🚀 Send to Channel", callback_data="preview_action:send", style="success")],
        [inline_button("❌ Cancel", callback_data="preview_action:cancel", style="danger")]
    ])


def admin_panel_inline_keyboard():
    fake_days = get_setting("fake_id_days", "7")
    notify_status = get_setting("vote_notification", "0")
    notify_badge = "🟢 ON" if notify_status == "1" else "🔴 OFF"
    notify_style = "success" if notify_status == "1" else "danger"

    return inline_keyboard([
        [
            inline_button("📣 User Broadcast", callback_data="admin_bc:users", style="primary"),
            inline_button("📣 Channel Broadcast", callback_data="admin_bc:channels", style="primary")
        ],
        [
            inline_button("🎯 Broadcast to Specific Channel", callback_data="admin_bc:custom", style="primary")
        ],
        [
            inline_button("🗳️ All Active Polls (Vote Control)", callback_data="admin:allpolls", style="success")
        ],
        [
            inline_button(f"🔔 Vote Notification: {notify_badge}", callback_data="admin:toggle_notify", style=notify_style)
        ],
        [
            inline_button(f"⏳ Fake ID Days Setting ({fake_days} days)", callback_data="admin:set_fake_days", style="primary")
        ],
        [
            inline_button("🔐 Force Subscribe (Force Join)", callback_data="admin:force_sub", style="primary"),
            inline_button("📡 Connected Channels", callback_data="admin:connected_ch", style="primary")
        ],
        [
            inline_button("⚙️ Code & Support Button Settings", callback_data="admin:btn_settings", style="primary"),
            inline_button("📊 Statistics", callback_data="admin:stats", style="primary")
        ],
        [
            inline_button("⬅️ Main Menu", callback_data="menu:main", style="danger")
        ]
    ])

# ---------------------------------------------------------------- Rendering (Top 3 Leaderboard)

def render_open_text(poll, total_votes):
    """Post body: shows only the question and the Top 3 live leaderboard"""
    options = json.loads(poll["options"])
    emojis = json.loads(poll["emojis"])
    counts = vote_counts(poll["id"], len(options))
    total_votes = sum(counts)

    # Rank by highest votes
    ranked = sorted(
        enumerate(zip(options, emojis, counts)),
        key=lambda x: x[1][2],
        reverse=True
    )

    medals = ["🥇", "🥈", "🥉"]
    rank_names = ["1st", "2nd", "3rd"]

    time_str = ""
    if poll.get("end_time") and poll["end_time"] > 0:
        remain = poll["end_time"] - int(time.time())
        if remain > 0:
            hrs = remain // 3600
            mins = (remain % 3600) // 60
            time_str = f"⏳ Time remaining: {hrs}h {mins}m"

    lines = [
        f"🗳️ <b>{esc(poll['question'])}</b>\n",
        "🏆 Live Leaderboard (Top 3) 🏆",
        "━━━━━━━━━━━━━━━━━━━━"
    ]

    # Show only the top 3
    for rank_idx, (_, (opt, emo, cnt)) in enumerate(ranked[:3]):
        badge = medals[rank_idx]
        r_name = rank_names[rank_idx]
        pct = round((cnt / total_votes) * 100) if total_votes else 0
        lines.append(f"{badge} {r_name}: {emo} {esc(opt)}")
        lines.append(f"➤ Votes: {cnt} ({pct}%)\n")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 Total Votes: {total_votes}")
    if time_str:
        lines.append(time_str)
    lines.append("⚡ Leaderboard updating live...\n")
    handle = CREDIT_BOT_USERNAME if CREDIT_BOT_USERNAME else (BOT_USERNAME or "PollzyBot")
    lines.append(f"⚡ Poll Create :- @{handle}")

    return "\n".join(lines)


def render_open_keyboard(poll, counts):
    options = json.loads(poll["options"])
    emojis = json.loads(poll["emojis"])
    max_count = max(counts) if counts else 0
    leader_idx = counts.index(max_count) if max_count > 0 and counts.count(max_count) == 1 else None

    rows, current_row = [], []
    for i, opt in enumerate(options):
        crown = "👑 " if i == leader_idx else ""
        label = f"{crown}🗳 {counts[i]} ┃ {emojis[i]} {opt}"
        color = COLOR_CYCLE[i % len(COLOR_CYCLE)]
        
        current_row.append(inline_button(label, callback_data=f"vote:{poll['id']}:{i}", style=color))
        
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
            
    if current_row:
        rows.append(current_row)

    rows.append([inline_button("🔄 Retract Vote", callback_data=f"retract:{poll['id']}", style="primary")])
    rows.append([inline_button("🛑 Close Poll", callback_data=f"close:{poll['id']}", style="danger")])
    
    return inline_keyboard(rows)


def promo_keyboard():
    if not PROMO_BOT_URL:
        return None
    return inline_keyboard([[inline_button(PROMO_BUTTON_TEXT, url=PROMO_BOT_URL, style="success")]])


def render_closed_text(poll, counts):
    options = json.loads(poll["options"])
    emojis = json.loads(poll["emojis"])
    total = sum(counts)
    
    winner_idx = poll.get("winner_index")
    if winner_idx is None or winner_idx >= len(options):
        winner_idx = counts.index(max(counts)) if total > 0 else 0

    lines = [
        f"📋 Poll: {esc(poll['question'])}",
        "──────────────────────",
        ""
    ]
    for i, opt in enumerate(options):
        c = counts[i]
        pct = round((c / total) * 100) if total else 0
        lines.append(f"{emojis[i]} {esc(opt)} ➤ {c} votes")
        lines.append(f"➩ {bar(pct)} {pct}%")
        lines.append("")
    
    lines.append("──────────────────────")
    lines.append(f"👑 Winner ➜ {emojis[winner_idx]} {esc(options[winner_idx])} ({counts[winner_idx]} votes)")
    lines.append("")
    lines.append(f"📊 Total Votes ➜ {total}")
    lines.append("")
    lines.append("🛑 The poll has now been closed.")
    lines.append("➡️ Results and the winner have been announced.")
    lines.append("")
    handle = CREDIT_BOT_USERNAME if CREDIT_BOT_USERNAME else (BOT_USERNAME or "PollBot")
    lines.append(f"⚡ <i>Poll Create :- @{handle}</i>")
    return "\n".join(lines)


def push_open_update(poll):
    counts = vote_counts(poll["id"], len(json.loads(poll["options"])))
    text = render_open_text(poll, sum(counts))
    kb = render_open_keyboard(poll, counts)
    try:
        if poll.get("photo_file_id"):
            api.edit_message_caption(poll["channel_id"], poll["message_id"], text, reply_markup=kb)
        else:
            api.edit_message_text(poll["channel_id"], poll["message_id"], text, reply_markup=kb)
    except Exception:
        pass


def push_closed_update(poll):
    options = json.loads(poll["options"])
    counts = vote_counts(poll["id"], len(options))

    text = render_closed_text(poll, counts)
    kb = promo_keyboard()
    try:
        if poll.get("photo_file_id"):
            api.edit_message_caption(poll["channel_id"], poll["message_id"], text, reply_markup=kb)
        else:
            api.edit_message_text(poll["channel_id"], poll["message_id"], text, reply_markup=kb)
    except Exception:
        pass


def user_can_manage_poll(poll, user_id):
    if user_id == poll["creator_id"] or is_owner(user_id):
        return True
    try:
        member = api.get_chat_member(poll["channel_id"], user_id)
        return member.get("status") in ("administrator", "creator")
    except Exception:
        return False

# ---------------------------------------------------------------- UI & Menus

def send_main_menu(chat_id, user_id):
    api.send_message(
        chat_id,
        "🗳 <b>Welcome To Poll Bot</b>\n\n"
        "Create polls, collect votes, and manage them easily.\n\n"
        "Choose an option from the menu below.",
        reply_markup=main_menu_keyboard(user_id),
    )


def send_admin_panel(chat_id):
    api.send_message(
        chat_id,
        "🛠️ <b>Admin Panel</b>\n\nChoose an option below:",
        reply_markup=admin_panel_inline_keyboard(),
    )


def handle_start(msg):
    user = msg["from"]
    record_user(user["id"], user.get("username"), user.get("first_name"))
    reset_state(user["id"])
    if not check_force_sub(user["id"]):
        send_force_sub_message(msg["chat"]["id"])
        return
    send_main_menu(msg["chat"]["id"], user["id"])


def handle_cancel(user_id, chat_id):
    reset_state(user_id)
    api.send_message(chat_id, "❌ Cancelled.")
    send_main_menu(chat_id, user_id)

# ---------------------------------------------------------------- Create Flow

def start_create_flow(user_id, chat_id):
    if not check_force_sub(user_id):
        send_force_sub_message(chat_id)
        return
    kb = inline_keyboard([[inline_button("🗳️ Create Now Poll 🚀", callback_data="start_poll_creation", style="success")]])
    api.send_message(
        chat_id,
        "😇 <b>Tap the button below to create your own poll in a channel.</b>",
        reply_markup=kb,
    )


def ask_channel_link(user_id, chat_id):
    msg = api.send_message(
        chat_id,
        "♀️ <b>Now send your channel link.</b>\n\n"
        "Example 👉 @mychannel",
        reply_markup=cancel_keyboard(),
    )
    set_step(user_id, "await_channel", {"last_bot_msg_id": msg["message_id"]})


def handle_channel_input(user_id, chat_id, text, user_msg_id):
    st = get_state(user_id) or {}
    prev_bot_msg = st.get("data", {}).get("last_bot_msg_id")

    channel = text.strip()
    if not channel.startswith("@") and not channel.startswith("-100"):
        channel = "@" + channel.lstrip("@")

    try:
        chat = api.get_chat(channel)
    except Exception:
        api.send_message(chat_id, "❌ Channel not found. Please send the correct username.", reply_markup=cancel_keyboard())
        return

    if chat.get("type") != "channel":
        api.send_message(chat_id, "❌ This is not a channel. Please send a channel username.", reply_markup=cancel_keyboard())
        return

    try:
        member = api.get_chat_member(chat["id"], BOT_ID)
        if member.get("status") not in ("administrator", "creator"):
            raise RuntimeError("not admin")
    except Exception:
        api.send_message(
            chat_id,
            "❌ The bot is not an admin in that channel. Please make the bot an admin and try again.",
            reply_markup=cancel_keyboard(),
        )
        return

    safe_delete(chat_id, user_msg_id)
    safe_delete(chat_id, prev_bot_msg)

    next_msg = api.send_message(chat_id, "📝 Now write your poll question:", reply_markup=cancel_keyboard())
    set_step(user_id, "await_question", {
        "channel_id": chat["id"],
        "channel_title": chat.get("title"),
        "channel_username": chat.get("username"),
        "last_bot_msg_id": next_msg["message_id"]
    })


def handle_question_input(user_id, chat_id, text, user_msg_id):
    question = text.strip()
    if not question:
        api.send_message(chat_id, "❌ The question cannot be empty. Please try again:", reply_markup=cancel_keyboard())
        return

    st = get_state(user_id) or {}
    prev_bot_msg = st.get("data", {}).get("last_bot_msg_id")

    safe_delete(chat_id, user_msg_id)
    safe_delete(chat_id, prev_bot_msg)

    rem = api.send_message(chat_id, "🔄", reply_markup={"remove_keyboard": True})
    safe_delete(chat_id, rem["message_id"])

    prev_q_msg = api.send_message(
        chat_id,
        f"📝 Preview of your poll question:\n\n{esc(question)}\n\n✅ Is this question correct?",
        reply_markup=confirm_question_inline_keyboard(),
    )
    set_step(user_id, "confirm_question", {"question": question, "preview_msg_id": prev_q_msg["message_id"]})


def handle_confirm_question(user_id, chat_id, choice):
    st = get_state(user_id) or {}
    preview_msg_id = st.get("data", {}).get("preview_msg_id")
    safe_delete(chat_id, preview_msg_id)

    if choice == "edit":
        next_msg = api.send_message(chat_id, "📝 Now write your poll question again:", reply_markup=cancel_keyboard())
        set_step(user_id, "await_question", {"last_bot_msg_id": next_msg["message_id"]})
        return

    next_msg = api.send_message(
        chat_id,
        "📸 Add a photo/banner for your poll\n\n"
        "If you want to show a picture with the poll, send it now (as a photo).\n\n"
        "If you don't want to add a photo, tap the \"🟢 Text Only\" button below.",
        reply_markup=photo_step_keyboard(),
    )
    set_step(user_id, "await_photo", {"last_bot_msg_id": next_msg["message_id"]})


def handle_photo_input(user_id, chat_id, photo_sizes, user_msg_id):
    st = get_state(user_id) or {}
    prev_bot_msg = st.get("data", {}).get("last_bot_msg_id")
    safe_delete(chat_id, user_msg_id)
    safe_delete(chat_id, prev_bot_msg)

    file_id = photo_sizes[-1]["file_id"]
    next_msg = ask_for_options(chat_id)
    set_step(user_id, "await_options", {"photo_file_id": file_id, "last_bot_msg_id": next_msg["message_id"]})


def handle_skip_photo(user_id, chat_id, user_msg_id=None):
    st = get_state(user_id) or {}
    prev_bot_msg = st.get("data", {}).get("last_bot_msg_id")
    safe_delete(chat_id, user_msg_id)
    safe_delete(chat_id, prev_bot_msg)

    next_msg = ask_for_options(chat_id)
    set_step(user_id, "await_options", {"photo_file_id": None, "last_bot_msg_id": next_msg["message_id"]})


def ask_for_options(chat_id):
    return api.send_message(
        chat_id,
        "🏷️ Now send the poll options/participant names (comma or new line):\n\n"
        "Example:\nRana, Kamal, Boro\n\n"
        f"Minimum {MIN_OPTIONS} options and maximum {MAX_OPTIONS} options are allowed.",
        reply_markup=cancel_keyboard(),
    )


def handle_options_input(user_id, chat_id, text, user_msg_id):
    st = get_state(user_id) or {}
    prev_bot_msg = st.get("data", {}).get("last_bot_msg_id")

    raw = text.replace("\n", ",")
    options = [o.strip() for o in raw.split(",") if o.strip()]
    seen, clean = set(), []
    for o in options:
        if o.lower() not in seen:
            seen.add(o.lower())
            clean.append(o)

    if len(clean) < MIN_OPTIONS:
        api.send_message(chat_id, f"❌ Please provide at least {MIN_OPTIONS} options. Try again:", reply_markup=cancel_keyboard())
        return
    if len(clean) > MAX_OPTIONS:
        api.send_message(chat_id, f"❌ Maximum {MAX_OPTIONS} options are allowed. Try again:", reply_markup=cancel_keyboard())
        return

    safe_delete(chat_id, user_msg_id)
    safe_delete(chat_id, prev_bot_msg)

    st["data"]["options"] = clean

    # Timer menu
    t_msg = api.send_message(
        chat_id,
        "⏱️ <b>Choose how long this poll should run:</b>\n\n"
        "The poll will close automatically after the selected time.",
        reply_markup=build_timer_keyboard()
    )
    set_step(user_id, "await_timer_choice", {"timer_msg_id": t_msg["message_id"]})


def render_final_preview_text(data):
    ch_handle = f"@{data.get('channel_username')}" if data.get('channel_username') else str(data.get('channel_id'))
    has_photo = "Yes" if data.get("photo_file_id") else "No"
    
    cand_lines = []
    for idx, opt in enumerate(data["options"], start=1):
        cand_lines.append(f"👤 {idx}. {esc(opt)}")

    timer_text = data.get("timer_str", "Unlimited")

    return (
        "📊 <b>Final Preview of Your Poll:</b>\n\n"
        f"📢 <b>Channel:</b> {ch_handle}\n"
        f"❓ <b>Question:</b> {esc(data['question'])}\n"
        f"⏱️ <b>Duration:</b> {timer_text}\n"
        f"🖼️ <b>Photo Attached:</b> {has_photo}\n\n"
        "📝 <b>Participants:</b>\n" +
        "\n".join(cand_lines) + "\n"
        "────────────────────────\n"
        "🛡️ <b>Set the poll's security settings:</b>\n"
        "Click the buttons below to toggle security on/off."
    )

# ---------------------------------------------------------------- Manage & Edit Flow

def show_edit_poll_list(chat_id, user_id):
    polls = list_open_polls_by_creator(user_id)
    if not polls:
        api.send_message(chat_id, "📭 You have no active polls.", reply_markup=main_menu_keyboard(user_id))
        return
    rows = []
    for p in polls:
        label = p["question"][:35] + ("…" if len(p["question"]) > 35 else "")
        rows.append([inline_button(f"✏️ {label}", callback_data=f"poll_edit_select:{p['id']}", style="primary")])
    rows.append([inline_button("⬅️ Back to Menu", callback_data="menu:main", style="danger")])
    api.send_message(chat_id, "🗂️ Select the poll where you want to add new names/options:", reply_markup=inline_keyboard(rows))


def handle_add_options_input(user_id, chat_id, text, user_msg_id):
    st = get_state(user_id)
    poll_id = st["data"]["poll_id"]
    poll = get_poll(poll_id)
    if not poll or poll["status"] != "open":
        api.send_message(chat_id, "❌ This poll is no longer active.", reply_markup=main_menu_keyboard(user_id))
        reset_state(user_id)
        return

    if poll["creator_id"] != user_id:
        api.send_message(chat_id, "⛔ Only the poll creator can add names.", reply_markup=main_menu_keyboard(user_id))
        reset_state(user_id)
        return

    raw = text.replace("\n", ",")
    new_opts = [o.strip() for o in raw.split(",") if o.strip()]
    if not new_opts:
        api.send_message(chat_id, "❌ Please send valid names:", reply_markup=cancel_keyboard())
        return

    safe_delete(chat_id, user_msg_id)

    existing_opts = json.loads(poll["options"])
    existing_emojis = json.loads(poll["emojis"])
    seen_lower = {o.lower() for o in existing_opts}

    added = []
    for o in new_opts:
        if o.lower() not in seen_lower:
            seen_lower.add(o.lower())
            existing_opts.append(o)
            added.append(o)
            existing_emojis.append(random.choice(EMOJI_POOL))

    if not added:
        api.send_message(chat_id, "⚠️ These names are already added to the poll!", reply_markup=main_menu_keyboard(user_id))
        reset_state(user_id)
        return

    update_poll_options(poll_id, existing_opts, existing_emojis)
    updated_poll = get_poll(poll_id)
    push_open_update(updated_poll)
    reset_state(user_id)

    api.send_message(
        chat_id,
        f"✅ Successfully added {len(added)} new name(s) to the poll and updated the channel!\n\n"
        f"➕ Added names: {', '.join(added)}",
        reply_markup=main_menu_keyboard(user_id),
    )

# ---------------------------------------------------------------- Admin Panel Features

def admin_show_all_polls_boost(chat_id):
    polls = list_all_open_polls()
    if not polls:
        api.send_message(chat_id, "📭 There are no active polls right now.", reply_markup=admin_panel_inline_keyboard())
        return
    rows = []
    for p in polls:
        ch_name = p.get('channel_title') or p.get('channel_username') or str(p['channel_id'])
        label = f"📊 {p['question'][:25]}… ({ch_name})"
        rows.append([inline_button(label, callback_data=f"admin_poll:{p['id']}", style="primary")])
    rows.append([inline_button("⬅️ Go Back", callback_data="menu:admin", style="danger")])
    api.send_message(chat_id, f"🗳️ All active polls ({len(polls)}):\nSelect a poll to manage votes:", reply_markup=inline_keyboard(rows))


def admin_show_poll_options(chat_id, poll_id):
    poll = get_poll(poll_id)
    if not poll or poll["status"] != "open":
        api.send_message(chat_id, "❌ This poll is now closed or not found.")
        return

    options = json.loads(poll["options"])
    emojis = json.loads(poll["emojis"])
    counts = vote_counts(poll_id, len(options))

    ch_handle = f"@{poll.get('channel_username')}" if poll.get('channel_username') else str(poll.get('channel_id'))
    ch_title = poll.get('channel_title') or ""
    ch_info = f"{esc(ch_title)} ({ch_handle})" if ch_title else ch_handle

    rows = []
    for i, opt in enumerate(options):
        btn_text = f"{emojis[i]} {opt} (Votes: {counts[i]})"
        rows.append([inline_button(btn_text, callback_data=f"admin_opt_menu:{poll_id}:{i}", style="primary")])
    rows.append([inline_button("⬅️ Back", callback_data="admin:allpolls", style="danger")])

    api.send_message(
        chat_id,
        f"📢 <b>Channel:</b> {ch_info}\n"
        f"📋 <b>Poll Question:</b> {esc(poll['question'])}\n\n"
        "👉 Click on the option/participant whose votes you want to control:",
        reply_markup=inline_keyboard(rows),
    )


def admin_show_option_action_menu(chat_id, poll_id, opt_idx):
    poll = get_poll(poll_id)
    if not poll or poll["status"] != "open":
        api.send_message(chat_id, "❌ This poll is no longer active.")
        return

    options = json.loads(poll["options"])
    emojis = json.loads(poll["emojis"])
    counts = vote_counts(poll_id, len(options))

    ch_handle = f"@{poll.get('channel_username')}" if poll.get('channel_username') else str(poll.get('channel_id'))
    ch_title = poll.get('channel_title') or ""
    ch_info = f"{esc(ch_title)} ({ch_handle})" if ch_title else ch_handle

    opt_name = options[opt_idx]
    emoji = emojis[opt_idx]

    rows = [
        [inline_button("➕ Add Votes (Boost)", callback_data=f"admin_boost:{poll_id}:{opt_idx}", style="success")],
        [inline_button("➖ Reduce Votes", callback_data=f"admin_reduce:{poll_id}:{opt_idx}", style="danger")],
        [inline_button("⬅️ Back", callback_data=f"admin_poll:{poll_id}", style="primary")],
    ]

    api.send_message(
        chat_id,
        f"📢 <b>Channel:</b> {ch_info}\n"
        f"👤 <b>Participant:</b> {emoji} {esc(opt_name)}\n"
        f"📊 <b>Current Votes:</b> {counts[opt_idx]}\n\n"
        "Choose an option below:",
        reply_markup=inline_keyboard(rows),
    )


def admin_handle_boost(user_id, chat_id, text):
    st = get_state(user_id)
    poll_id = st["data"]["poll_id"]
    opt_idx = st["data"]["opt_idx"]

    try:
        count = int(text.strip())
        if count <= 0:
            raise ValueError()
    except Exception:
        api.send_message(chat_id, "❌ Please enter a valid positive number (e.g. 50):", reply_markup=cancel_keyboard())
        return

    add_boosted_votes(poll_id, opt_idx, count)
    poll = get_poll(poll_id)
    push_open_update(poll)

    options = json.loads(poll["options"])
    reset_state(user_id)

    api.send_message(
        chat_id,
        f"✅ <b>Votes successfully added!</b>\n\n"
        f"👤 Participant: <b>{esc(options[opt_idx])}</b>\n"
        f"➕ Votes Added: <b>{count}</b>\n\n"
        f"The channel has been updated live!",
        reply_markup=main_menu_keyboard(user_id),
    )


def admin_handle_reduce(user_id, chat_id, text):
    st = get_state(user_id)
    poll_id = st["data"]["poll_id"]
    opt_idx = st["data"]["opt_idx"]
    max_c = st["data"]["current_votes"]

    try:
        amount = int(text.strip())
        if amount <= 0 or amount > max_c:
            raise ValueError()
    except Exception:
        api.send_message(chat_id, f"❌ Please enter a valid number between 1 and {max_c}:", reply_markup=cancel_keyboard())
        return

    reduced = reduce_votes_count(poll_id, opt_idx, amount)
    poll = get_poll(poll_id)
    push_open_update(poll)

    options = json.loads(poll["options"])
    reset_state(user_id)

    api.send_message(
        chat_id,
        f"✅ <b>Votes successfully reduced!</b>\n\n"
        f"👤 Participant: <b>{esc(options[opt_idx])}</b>\n"
        f"📉 Reduced By: <b>{reduced}</b>\n\n"
        f"The channel has been updated live!",
        reply_markup=main_menu_keyboard(user_id),
    )


def admin_show_stats(chat_id):
    s = stats_counts()
    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"🗳️ Total Polls: {s['total_polls']}\n"
        f"🟢 Active Polls: {s['open_polls']}\n"
        f"🔴 Closed Polls: {s['closed_polls']}\n"
        f"✅ Total Votes: {s['total_votes']}\n"
        f"👥 Total Users: {s['total_users']}\n"
        f"📣 Total Channels: {s['total_channels']}"
    )
    api.send_message(chat_id, text, reply_markup=admin_panel_inline_keyboard())


def admin_show_connected_channels(chat_id):
    channels = list_distinct_channels()
    if not channels:
        api.send_message(chat_id, "📭 No channels have been connected yet.", reply_markup=admin_panel_inline_keyboard())
        return
    text = f"📡 <b>Connected Channels ({len(channels)}):</b>\n\n"
    for i, ch in enumerate(channels, start=1):
        username = f"@{ch['channel_username']}" if ch['channel_username'] else "No Username"
        text += f"{i}. <b>{esc(ch['channel_title'] or 'Unknown')}</b>\n   🔗 {username} | ID: <code>{ch['channel_id']}</code>\n   🗳 Total Polls: {ch['poll_count']}\n\n"
    api.send_message(chat_id, text, reply_markup=inline_keyboard([[inline_button("⬅️ Back", callback_data="menu:admin", style="danger")]]))


def admin_show_force_sub_menu(chat_id):
    current = get_setting("force_channel", "Not set")
    text = (
        f"🔐 <b>Force Subscribe (Force Join) Settings</b>\n\n"
        f"📌 Current Channel(s): <b>{esc(current)}</b>\n\n"
        "<i>(To add multiple channels, separate them with commas, e.g. @ch1, @ch2)</i>"
    )
    kb = inline_keyboard([
        [inline_button("➕ Set/Change Channel", callback_data="force:set", style="success")],
        [inline_button("🗑️ Remove", callback_data="force:remove", style="danger")],
        [inline_button("⬅️ Back", callback_data="menu:admin", style="primary")]
    ])
    api.send_message(chat_id, text, reply_markup=kb)


def admin_show_btn_settings_menu(chat_id):
    kb = inline_keyboard([
        [inline_button("🛒 Buy Code Button Settings", callback_data="btnset:code", style="primary")],
        [inline_button("📞 Support Button Settings", callback_data="btnset:sup", style="primary")],
        [inline_button("⬅️ Back", callback_data="menu:admin", style="danger")]
    ])
    api.send_message(chat_id, "⚙️ <b>Code & Support Button Settings</b>\n\nSelect which button you want to customize:", reply_markup=kb)

# ---------------------------------------------------------------- Actions

def do_vote(cq, poll_id, option_index):
    user = cq["from"]
    
    # Anti-flood check
    if is_flooding(user["id"]):
        api.answer_callback_query(cq["id"], "⚠️ You are clicking too fast! Please try again in a moment.", show_alert=True)
        return

    poll = get_poll(poll_id)
    if not poll:
        api.answer_callback_query(cq["id"], "❌ This poll no longer exists.", show_alert=True)
        return
    if poll["status"] != "open":
        api.answer_callback_query(cq["id"], "🔒 This poll has been closed.", show_alert=True)
        return

    # Membership check
    if not is_user_channel_member(poll["channel_id"], user["id"]):
        api.answer_callback_query(
            cq["id"],
            "⚠️ To vote, you must first join this channel!",
            show_alert=True
        )
        return

    # Username check
    if poll.get("username_check", 0) == 1 and not user.get("username"):
        api.answer_callback_query(
            cq["id"],
            "⚠️ Security Alert: Your Telegram account has no username set! Please set a username to vote.",
            show_alert=True
        )
        return

    # Photo check
    if poll.get("photo_check", 0) == 1:
        photos = api.get_user_profile_photos(user["id"], limit=1)
        if photos.get("total_count", 0) == 0:
            api.answer_callback_query(
                cq["id"],
                "⚠️ Security Alert: You must have a profile picture to vote!",
                show_alert=True
            )
            return

    # New ID filter
    if poll.get("fake_filter", 0) == 1:
        if is_account_newer_than_configured_days(user["id"]):
            api.answer_callback_query(
                cq["id"],
                "⚠️ Your account is new/fake 🚫 so your vote cannot be accepted. ❌",
                show_alert=True
            )
            return

    name = user.get("username") or user.get("first_name") or str(user["id"])
    ok = cast_vote(poll_id, user["id"], name, option_index)
    if not ok:
        api.answer_callback_query(cq["id"], "⚠️ You have already voted.", show_alert=True)
        return

    push_open_update(poll)

    # Custom success alert
    options = json.loads(poll["options"])
    emojis = json.loads(poll["emojis"])
    counts = vote_counts(poll_id, len(options))
    opt_name = f"{emojis[option_index]} {options[option_index]}"
    opt_count = counts[option_index]

    sorted_counts = sorted(counts, reverse=True)
    rank = sorted_counts.index(opt_count) + 1
    rank_str = f"{rank}{'st' if rank == 1 else 'nd' if rank == 2 else 'rd' if rank == 3 else 'th'} place"

    alert_text = (
        "🎉 Vote Successful!\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👤 Your Choice: {opt_name}\n"
        f"📈 Current Votes for this Participant: {opt_count}\n"
        f"🏆 Current Position: {rank_str}\n\n"
        "⚠️ Remember: If you leave the channel, your vote will be cancelled!"
    )
    api.answer_callback_query(cq["id"], alert_text, show_alert=True)

    # Vote notification (to admins)
    if get_setting("vote_notification", "0") == "1":
        name_parts = [user.get("first_name", ""), user.get("last_name") or ""]
        fullname = " ".join([p for p in name_parts if p]).strip() or user.get("username") or str(user["id"])
        username_text = f"@{user['username']}" if user.get("username") else "None"

        notif_text = (
            "🗳 <b>The poll is being tracked automatically.</b>\n\n"
            "👷 <b>A new vote has been cast:</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"👤 Name : {esc(fullname)}\n"
            f"🔰 Username : {esc(username_text)}\n"
            f"🆔 User ID : <code>{user['id']}</code>\n"
            f"📌 Voted For : {esc(opt_name)} (Votes: {opt_count})\n"
            "━━━━━━━━━━━━━━"
        )
        for owner_id in OWNER_IDS:
            try:
                api.send_message(owner_id, notif_text)
            except Exception:
                pass


def do_retract(cq, poll_id):
    user = cq["from"]
    poll = get_poll(poll_id)
    if not poll:
        api.answer_callback_query(cq["id"], "❌ This poll no longer exists.", show_alert=True)
        return
    if poll["status"] != "open":
        api.answer_callback_query(cq["id"], "🔒 This poll has been closed.", show_alert=True)
        return
    removed = retract_vote(poll_id, user["id"])
    if not removed:
        api.answer_callback_query(cq["id"], "⚠️ You haven't voted yet.", show_alert=True)
        return
    push_open_update(poll)
    api.answer_callback_query(cq["id"], "🔄 Your vote has been retracted.")


def do_close(cq, poll_id):
    user = cq["from"]
    poll = get_poll(poll_id)
    if not poll:
        api.answer_callback_query(cq["id"], "❌ This poll no longer exists.", show_alert=True)
        return
    if poll["status"] != "open":
        api.answer_callback_query(cq["id"], "🔒 The poll is already closed.", show_alert=True)
        return
    if not user_can_manage_poll(poll, user["id"]):
        api.answer_callback_query(cq["id"], "⛔ You do not have permission to close this poll.", show_alert=True)
        return

    options = json.loads(poll["options"])
    counts = vote_counts(poll_id, len(options))
    winner_index = counts.index(max(counts)) if sum(counts) > 0 else 0

    close_poll_db(poll_id, winner_index)
    poll = get_poll(poll_id)
    api.answer_callback_query(cq["id"], "🔴 Closing the poll…")
    push_closed_update(poll)

# ---------------------------------------------------------------- Handle Leave / Chat Member (Vote cancellation & admin notification)

def handle_chat_member(upd):
    """If a user leaves or is banned from the channel, their vote is cancelled and admins are notified"""
    chat = upd.get("chat")
    if not chat:
        return
    channel_id = chat.get("id")
    new_member = upd.get("new_chat_member")
    if not new_member:
        return
    user = new_member.get("user")
    if not user:
        return
    user_id = user.get("id")
    status = new_member.get("status")

    if not channel_id or not user_id:
        return

    if status in ("left", "kicked", "banned"):
        with _lock:
            rows = conn.execute(
                "SELECT * FROM polls WHERE channel_id = ? AND status = 'open'",
                (channel_id,)
            ).fetchall()
            open_polls = [dict(r) for r in rows]

        for p in open_polls:
            pid = p["id"]
            vote_row = None
            with _lock:
                vote_row = conn.execute(
                    "SELECT option_index FROM votes WHERE poll_id = ? AND user_id = ?",
                    (pid, user_id)
                ).fetchone()

                deleted = False
                if vote_row:
                    conn.execute("DELETE FROM votes WHERE poll_id = ? AND user_id = ?", (pid, user_id))
                    conn.commit()
                    deleted = True

            # If vote was removed, live-update the channel post
            if deleted:
                poll = get_poll(pid)
                if poll and poll.get("message_id"):
                    try:
                        push_open_update(poll)
                    except Exception:
                        pass

                # Notify admins
                if get_setting("vote_notification", "0") == "1":
                    try:
                        opt_idx = vote_row["option_index"]
                        opts = json.loads(p["options"])
                        ems = json.loads(p["emojis"])
                        opt_name = f"{ems[opt_idx]} {opts[opt_idx]}" if opt_idx < len(opts) else f"Option {opt_idx+1}"

                        name_parts = [user.get("first_name", ""), user.get("last_name") or ""]
                        fullname = " ".join([pt for pt in name_parts if pt]).strip() or user.get("username") or str(user_id)
                        username_text = f"@{user['username']}" if user.get("username") else "None"
                        ch_name = p.get("channel_title") or chat.get("title") or str(channel_id)

                        leave_notif = (
                            "⚠️ <b>Warning: A user has left the channel!</b>\n\n"
                            "❌ <b>Vote automatically cancelled:</b>\n"
                            "━━━━━━━━━━━━━━\n"
                            f"👤 Name : {esc(fullname)}\n"
                            f"🔰 Username : {esc(username_text)}\n"
                            f"🆔 User ID : <code>{user_id}</code>\n"
                            f"📢 Channel : {esc(ch_name)}\n"
                            f"📌 Cancelled Vote : {esc(opt_name)}\n"
                            "━━━━━━━━━━━━━━"
                        )
                        for owner_id in OWNER_IDS:
                            try:
                                api.send_message(owner_id, leave_notif)
                            except Exception:
                                pass
                    except Exception:
                        pass

# ---------------------------------------------------------------- Auto Timer Background Loop

def auto_poll_closer_loop():
    """Auto-timer monitor thread"""
    while True:
        try:
            now = int(time.time())
            with _lock:
                rows = conn.execute(
                    "SELECT id FROM polls WHERE status = 'open' AND end_time > 0 AND end_time <= ?",
                    (now,)
                ).fetchall()
                expired_ids = [r["id"] for r in rows]

            for pid in expired_ids:
                poll = get_poll(pid)
                if poll and poll["status"] == "open":
                    options = json.loads(poll["options"])
                    counts = vote_counts(pid, len(options))
                    winner_index = counts.index(max(counts)) if sum(counts) > 0 else 0
                    close_poll_db(pid, winner_index)
                    poll = get_poll(pid)
                    push_closed_update(poll)
        except Exception:
            traceback.print_exc()
        time.sleep(15)

# ---------------------------------------------------------------- Dispatch

def handle_message(msg):
    if "from" not in msg or msg["from"].get("is_bot"):
        return
    user = msg["from"]
    user_id = user["id"]
    chat_id = msg["chat"]["id"]
    msg_id = msg.get("message_id")
    text = msg.get("text", "") or ""

    if text == "/start":
        handle_start(msg)
        return
    if text in ("/cancel", "❌ Cancel"):
        handle_cancel(user_id, chat_id)
        return

    if not check_force_sub(user_id):
        send_force_sub_message(chat_id)
        return

    if text == "📣 Create Channel Poll":
        start_create_flow(user_id, chat_id)
        return
    elif text == "✏️ Edit Poll":
        reset_state(user_id)
        show_edit_poll_list(chat_id, user_id)
        return
    elif text == "🛒 Buy Code":
        buy_msg = get_setting("code_buy_text", "🛒 To buy the source code, contact via the button below:")
        buy_btn = get_setting("code_buy_btn_name", "📩 Contact Us")
        buy_url = get_setting("code_buy_url", "https://t.me/your_admin")
        if not buy_url.startswith("http"):
            buy_url = f"https://t.me/{buy_url.lstrip('@')}"
        kb = inline_keyboard([[inline_button(buy_btn, url=buy_url, style="success")]])
        api.send_message(chat_id, esc(buy_msg), reply_markup=kb)
        return
    elif text == "📞 Support":
        sup_msg = get_setting("support_text", "📞 For any help, contact via the button below:")
        sup_btn = get_setting("support_btn_name", "📩 Contact Us")
        sup_url = get_setting("support_url", "https://t.me/your_admin")
        if not sup_url.startswith("http"):
            sup_url = f"https://t.me/{sup_url.lstrip('@')}"
        kb = inline_keyboard([[inline_button(sup_btn, url=sup_url, style="primary")]])
        api.send_message(chat_id, esc(sup_msg), reply_markup=kb)
        return
    elif text == "🛠️ Admin Panel":
        if is_owner(user_id):
            reset_state(user_id)
            send_admin_panel(chat_id)
        return

    st = get_state(user_id)
    step = st["step"] if st else None

    if step == "await_photo" and text == "🟢 Text Only":
        handle_skip_photo(user_id, chat_id, msg_id)
        return

    if step == "admin_await_fake_days" and is_owner(user_id) and text:
        try:
            d_val = float(text.strip())
            if d_val <= 0:
                raise ValueError()
            days_str = str(int(d_val)) if d_val.is_integer() else str(d_val)
            set_setting("fake_id_days", days_str)
            reset_state(user_id)
            api.send_message(chat_id, f"✅ New/fake ID filter age threshold successfully set to <b>{days_str} days</b>!", reply_markup=admin_panel_inline_keyboard())
        except Exception:
            api.send_message(chat_id, "❌ Please enter a valid positive number (e.g. 7 or 15):", reply_markup=cancel_keyboard())
        return

    if step == "admin_await_force_channel" and is_owner(user_id) and text:
        ch = text.strip()
        set_setting("force_channel", ch)
        reset_state(user_id)
        api.send_message(chat_id, f"✅ Force subscribe channel successfully updated: <b>{esc(ch)}</b>", reply_markup=admin_panel_inline_keyboard())
        return

    if step == "admin_code_step1" and is_owner(user_id) and text:
        set_step(user_id, "admin_code_step2", {"code_text": text.strip()})
        api.send_message(chat_id, "🛒 <b>Buy Code Settings (Step 2/3):</b>\n\nNow enter the button name:\n<i>(e.g. 📩 Contact Us)</i>", reply_markup=cancel_keyboard())
        return
    if step == "admin_code_step2" and is_owner(user_id) and text:
        st["data"]["code_btn_name"] = text.strip()
        set_step(user_id, "admin_code_step3", st["data"])
        api.send_message(chat_id, "🛒 <b>Buy Code Settings (Step 3/3):</b>\n\nSend the username or link:\n<i>(e.g. @your_username)</i>", reply_markup=cancel_keyboard())
        return
    if step == "admin_code_step3" and is_owner(user_id) and text:
        d = st["data"]
        set_setting("code_buy_text", d["code_text"])
        set_setting("code_buy_btn_name", d["code_btn_name"])
        set_setting("code_buy_url", text.strip())
        reset_state(user_id)
        api.send_message(chat_id, "✅ <b>Buy Code button settings completed successfully!</b>", reply_markup=admin_panel_inline_keyboard())
        return

    if step == "admin_sup_step1" and is_owner(user_id) and text:
        set_step(user_id, "admin_sup_step2", {"sup_text": text.strip()})
        api.send_message(chat_id, "📞 <b>Support Settings (Step 2/3):</b>\n\nNow enter the button name:\n<i>(e.g. 📩 Support Inbox)</i>", reply_markup=cancel_keyboard())
        return
    if step == "admin_sup_step2" and is_owner(user_id) and text:
        st["data"]["sup_btn_name"] = text.strip()
        set_step(user_id, "admin_sup_step3", st["data"])
        api.send_message(chat_id, "📞 <b>Support Settings (Step 3/3):</b>\n\nSend the support link or username:\n<i>(e.g. @your_support)</i>", reply_markup=cancel_keyboard())
        return
    if step == "admin_sup_step3" and is_owner(user_id) and text:
        d = st["data"]
        set_setting("support_text", d["sup_text"])
        set_setting("support_btn_name", d["sup_btn_name"])
        set_setting("support_url", text.strip())
        reset_state(user_id)
        api.send_message(chat_id, "✅ <b>Support button settings completed successfully!</b>", reply_markup=admin_panel_inline_keyboard())
        return

        if step == "admin_await_custom_ch_id" and is_owner(user_id) and text:
        ch = text.strip()
        set_step(user_id, "admin_await_custom_ch_msg", {"target_channel": ch})
        api.send_message(chat_id, f"📣 Write the message to send to <b>{esc(ch)}</b>:", reply_markup=cancel_keyboard())
        return
    if step == "admin_await_custom_ch_msg" and is_owner(user_id) and text:
        target = st["data"]["target_channel"]
        reset_state(user_id)
        try:
            api.send_message(target, text)
            api.send_message(chat_id, f"✅ Message sent to <b>{esc(target)}</b>!", reply_markup=admin_panel_inline_keyboard())
        except Exception as e:
            api.send_message(chat_id, f"❌ Failed to send message: {e}", reply_markup=admin_panel_inline_keyboard())
        return

    if step == "admin_await_broadcast_users" and is_owner(user_id) and text:
        reset_state(user_id)
        user_ids = list_all_users()
        ok = fail = 0
        for uid in user_ids:
            try:
                api.send_message(uid, text)
                ok += 1
            except Exception:
                fail += 1
            time.sleep(0.05)
        api.send_message(chat_id, f"✅ User broadcast complete!\n\n✅ Success: {ok}\n❌ Failed: {fail}", reply_markup=admin_panel_inline_keyboard())
        return

    if step == "admin_await_broadcast_channels" and is_owner(user_id) and text:
        reset_state(user_id)
        channels = list_distinct_channels()
        ok = fail = 0
        for ch in channels:
            try:
                api.send_message(ch["channel_id"], text)
                ok += 1
            except Exception:
                fail += 1
            time.sleep(0.05)
        api.send_message(chat_id, f"✅ Channel broadcast complete!\n\n✅ Success: {ok}\n❌ Failed: {fail}", reply_markup=admin_panel_inline_keyboard())
        return

    if step == "admin_boost_step" and is_owner(user_id) and text:
        admin_handle_boost(user_id, chat_id, text)
        return
    if step == "admin_reduce_step" and is_owner(user_id) and text:
        admin_handle_reduce(user_id, chat_id, text)
        return

    if step == "await_add_options" and text:
        handle_add_options_input(user_id, chat_id, text, msg_id)
        return
    if step == "await_channel" and text:
        handle_channel_input(user_id, chat_id, text, msg_id)
        return
    if step == "await_question" and text:
        handle_question_input(user_id, chat_id, text, msg_id)
        return
    if step == "await_photo" and msg.get("photo"):
        handle_photo_input(user_id, chat_id, msg["photo"], msg_id)
        return
    if step == "await_options" and text:
        handle_options_input(user_id, chat_id, text, msg_id)
        return

    send_main_menu(chat_id, user_id)


def handle_callback(cq):
    data = cq.get("data", "")
    user_id = cq["from"]["id"]
    chat_id = cq["message"]["chat"]["id"]
    msg_id = cq["message"]["message_id"]

    try:
        if data == "start_poll_creation":
            api.answer_callback_query(cq["id"])
            safe_delete(chat_id, msg_id)
            ask_channel_link(user_id, chat_id)
            return

        if data.startswith("timer_set:"):
            choice = data.split(":")[1]
            if choice == "cancel":
                api.answer_callback_query(cq["id"])
                safe_delete(chat_id, msg_id)
                handle_cancel(user_id, chat_id)
                return

            timer_map = {
                "1h": (3600, "1 Hour"),
                "6h": (21600, "6 Hours"),
                "12h": (43200, "12 Hours"),
                "1d": (86400, "1 Day"),
                "3d": (259200, "3 Days"),
                "7d": (604800, "7 Days"),
                "none": (0, "Unlimited (No Timer)")
            }

            sec, label = timer_map.get(choice, (0, "Unlimited"))
            end_time = int(time.time()) + sec if sec > 0 else 0

            st = get_state(user_id)
            if not st:
                api.answer_callback_query(cq["id"], "❌ Session expired. Please start again.", show_alert=True)
                return

            st["data"]["end_time"] = end_time
            st["data"]["timer_str"] = label
            st["data"]["photo_check"] = 1
            st["data"]["username_check"] = 1
            st["data"]["fake_filter"] = 1

            api.answer_callback_query(cq["id"])
            safe_delete(chat_id, msg_id)

            preview_text = render_final_preview_text(st["data"])
            kb = build_preview_markup(1, 1, 1)

            sent_prev = api.send_message(chat_id, preview_text, reply_markup=kb)
            set_step(user_id, "await_preview_action", {"preview_msg_id": sent_prev["message_id"]})
            return

        if data.startswith("preview_toggle:"):
            toggle_type = data.split(":")[1]
            st = get_state(user_id)
            if not st or "data" not in st:
                api.answer_callback_query(cq["id"], "❌ Session expired. Please start again.", show_alert=True)
                return

            d = st["data"]
            if toggle_type == "photo":
                d["photo_check"] = 1 if d.get("photo_check", 1) == 0 else 0
            elif toggle_type == "username":
                d["username_check"] = 1 if d.get("username_check", 1) == 0 else 0
            elif toggle_type == "fake":
                d["fake_filter"] = 1 if d.get("fake_filter", 1) == 0 else 0

            kb = build_preview_markup(d["photo_check"], d["username_check"], d["fake_filter"])
            api.answer_callback_query(cq["id"])
            api.edit_message_text(chat_id, msg_id, render_final_preview_text(d), reply_markup=kb)
            return

        if data == "preview_action:cancel":
            api.answer_callback_query(cq["id"])
            safe_delete(chat_id, msg_id)
            handle_cancel(user_id, chat_id)
            return

        if data == "preview_action:send":
            st = get_state(user_id)
            if not st or "data" not in st:
                api.answer_callback_query(cq["id"], "❌ Session expired. Please start again.", show_alert=True)
                return
            
            d = st["data"]
            poll_id = create_poll(
                creator_id=user_id,
                channel_id=d["channel_id"],
                channel_title=d.get("channel_title"),
                channel_username=d.get("channel_username"),
                question=d["question"],
                photo_file_id=d.get("photo_file_id"),
                options=d["options"],
                photo_check=d.get("photo_check", 1),
                username_check=d.get("username_check", 1),
                fake_filter=d.get("fake_filter", 1),
                end_time=d.get("end_time", 0)
            )
            poll = get_poll(poll_id)
            counts = [0] * len(d["options"])
            text_out = render_open_text(poll, 0)
            kb = render_open_keyboard(poll, counts)

            try:
                if poll["photo_file_id"]:
                    sent = api.send_photo(poll["channel_id"], poll["photo_file_id"], text_out, reply_markup=kb)
                else:
                    sent = api.send_message(poll["channel_id"], text_out, reply_markup=kb)
                set_poll_message_id(poll_id, sent["message_id"])
            except Exception as e:
                api.answer_callback_query(cq["id"], f"❌ Failed to post in channel: {e}", show_alert=True)
                return

            api.answer_callback_query(cq["id"], "🚀 Successfully posted in channel!")
            safe_delete(chat_id, msg_id)
            reset_state(user_id)
            api.send_message(chat_id, "✅ Poll successfully posted in the channel!", reply_markup=main_menu_keyboard(user_id))
            return

        if data == "verify_force_sub":
            if check_force_sub(user_id):
                api.answer_callback_query(cq["id"], "✅ Thank you! You have joined the channel.")
                safe_delete(chat_id, msg_id)
                send_main_menu(chat_id, user_id)
            else:
                api.answer_callback_query(cq["id"], "⚠️ You haven't joined all channels yet!", show_alert=True)
            return

        if data.startswith("confirm_q:"):
            choice = data.split(":")[1]
            api.answer_callback_query(cq["id"])
            if choice == "yes":
                handle_confirm_question(user_id, chat_id, "yes")
            elif choice == "edit":
                handle_confirm_question(user_id, chat_id, "edit")
            elif choice == "cancel":
                handle_cancel(user_id, chat_id)
            return

        if data == "menu:admin":
            if not is_owner(user_id):
                api.answer_callback_query(cq["id"], "⛔ Permission denied.", show_alert=True)
                return
            reset_state(user_id)
            api.answer_callback_query(cq["id"])
            send_admin_panel(chat_id)
            return
        elif data == "admin:toggle_notify":
            if not is_owner(user_id):
                return
            curr = get_setting("vote_notification", "0")
            new_val = "1" if curr == "0" else "0"
            set_setting("vote_notification", new_val)
            status_text = "🟢 ON" if new_val == "1" else "🔴 OFF"
            api.answer_callback_query(cq["id"], f"Vote notification turned {status_text}!")
            api.edit_message_reply_markup(chat_id, msg_id, reply_markup=admin_panel_inline_keyboard())
            return
        elif data == "admin:set_fake_days":
            if not is_owner(user_id):
                return
            set_step(user_id, "admin_await_fake_days")
            api.answer_callback_query(cq["id"])
            curr_days = get_setting("fake_id_days", "7")
            api.send_message(
                chat_id,
                f"⏳ <b>Set Fake ID Age Threshold:</b>\n\n"
                f"📌 Current setting: <b>{curr_days} days</b>\n\n"
                "Enter a number for how many days new accounts should be considered fake/ineligible (e.g. 7 or 10):",
                reply_markup=cancel_keyboard()
            )
            return
        elif data == "admin:stats":
            if not is_owner(user_id):
                return
            api.answer_callback_query(cq["id"])
            admin_show_stats(chat_id)
            return
        elif data == "admin:connected_ch":
            if not is_owner(user_id):
                return
            api.answer_callback_query(cq["id"])
            admin_show_connected_channels(chat_id)
            return
        elif data == "admin:force_sub":
            if not is_owner(user_id):
                return
            api.answer_callback_query(cq["id"])
            admin_show_force_sub_menu(chat_id)
            return
        elif data == "force:set":
            if not is_owner(user_id):
                return
            set_step(user_id, "admin_await_force_channel")
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, "📣 Enter the channel username for force subscribe (multiple channels can be separated by commas):", reply_markup=cancel_keyboard())
            return
        elif data == "force:remove":
            if not is_owner(user_id):
                return
            set_setting("force_channel", "")
            api.answer_callback_query(cq["id"], "✅ Force subscribe removed!")
            admin_show_force_sub_menu(chat_id)
            return
        elif data == "admin:btn_settings":
            if not is_owner(user_id):
                return
            api.answer_callback_query(cq["id"])
            admin_show_btn_settings_menu(chat_id)
            return
        elif data == "btnset:code":
            if not is_owner(user_id):
                return
            set_step(user_id, "admin_code_step1", {})
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, "🛒 <b>Buy Code Settings (Step 1/3):</b>\n\nWrite the detailed message you want to show:", reply_markup=cancel_keyboard())
            return
        elif data == "btnset:sup":
            if not is_owner(user_id):
                return
            set_step(user_id, "admin_sup_step1", {})
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, "📞 <b>Support Settings (Step 1/3):</b>\n\nWrite the detailed message you want to show:", reply_markup=cancel_keyboard())
            return
        elif data == "admin_bc:custom":
            if not is_owner(user_id):
                return
            set_step(user_id, "admin_await_custom_ch_id")
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, "🎯 Send the channel username or ID:", reply_markup=cancel_keyboard())
            return
        elif data == "admin_bc:users":
            if not is_owner(user_id):
                return
            set_step(user_id, "admin_await_broadcast_users")
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, "📣 Write the message to send to all users:", reply_markup=cancel_keyboard())
            return
        elif data == "admin_bc:channels":
            if not is_owner(user_id):
                return
            set_step(user_id, "admin_await_broadcast_channels")
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, "📣 Write the message to send to all channels:", reply_markup=cancel_keyboard())
            return
        elif data == "admin:allpolls":
            if not is_owner(user_id):
                return
            api.answer_callback_query(cq["id"])
            admin_show_all_polls_boost(chat_id)
            return
        elif data == "menu:main":
            reset_state(user_id)
            api.answer_callback_query(cq["id"])
            send_main_menu(chat_id, user_id)
            return

        elif data.startswith("poll_edit_select:"):
            poll_id = int(data.split(":")[1])
            poll = get_poll(poll_id)
            if not poll or poll["status"] != "open":
                api.answer_callback_query(cq["id"], "❌ This poll is not active.", show_alert=True)
                return
            
            if poll["creator_id"] != user_id:
                api.answer_callback_query(cq["id"], "⛔ You are not the creator of this poll! Only the creator can edit it.", show_alert=True)
                return

            set_step(user_id, "await_add_options", {"poll_id": poll_id})
            api.answer_callback_query(cq["id"])
            api.send_message(
                chat_id,
                "✏️ <b>Add new participants to the active poll</b>\n\n"
                "Send the names of the participants you want to add (separated by commas).",
                reply_markup=cancel_keyboard(),
            )
        elif data.startswith("vote:"):
            _, poll_id, opt_idx = data.split(":")
            do_vote(cq, int(poll_id), int(opt_idx))
        elif data.startswith("retract:"):
            poll_id = int(data.split(":")[1])
            do_retract(cq, poll_id)
        elif data.startswith("close:"):
            poll_id = int(data.split(":")[1])
            do_close(cq, poll_id)
        elif data.startswith("admin_poll:"):
            poll_id = int(data.split(":")[1])
            api.answer_callback_query(cq["id"])
            admin_show_poll_options(chat_id, poll_id)
        elif data.startswith("admin_opt_menu:"):
            _, poll_id, opt_idx = data.split(":")
            api.answer_callback_query(cq["id"])
            admin_show_option_action_menu(chat_id, int(poll_id), int(opt_idx))
        elif data.startswith("admin_boost:"):
            _, poll_id, opt_idx = data.split(":")
            set_step(user_id, "admin_boost_step", {"poll_id": int(poll_id), "opt_idx": int(opt_idx)})
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, "➕ How many votes do you want to add? (e.g. 50):", reply_markup=cancel_keyboard())
        elif data.startswith("admin_reduce:"):
            _, poll_id, opt_idx = data.split(":")
            poll = get_poll(int(poll_id))
            counts = vote_counts(int(poll_id), len(json.loads(poll["options"])))
            curr_c = counts[int(opt_idx)]
            if curr_c <= 0:
                api.answer_callback_query(cq["id"], "⚠️ There are no votes to reduce for this option.", show_alert=True)
                return
            set_step(user_id, "admin_reduce_step", {
                "poll_id": int(poll_id),
                "opt_idx": int(opt_idx),
                "current_votes": curr_c
            })
            api.answer_callback_query(cq["id"])
            api.send_message(chat_id, f"👉 How many votes do you want to reduce? (Enter a number between 1 and {curr_c}):", reply_markup=cancel_keyboard())
        else:
            api.answer_callback_query(cq["id"])
    except Exception:
        traceback.print_exc()
        try:
            api.answer_callback_query(cq["id"], "⚠️ Something went wrong, please try again.", show_alert=True)
        except Exception:
            pass

# ======================================================================
# MAIN LOOP
# ======================================================================

def run():
    global BOT_ID, BOT_USERNAME
    init_db()
    me = api.get_me()
    BOT_ID = me["id"]
    BOT_USERNAME = me.get("username")
    print(f"✅ Logged in as @{BOT_USERNAME} (id={BOT_ID})")

    # Start auto-timer thread in the background
    threading.Thread(target=auto_poll_closer_loop, daemon=True).start()

    offset = None
    while True:
        try:
            updates = api.get_updates(offset=offset, timeout=POLL_TIMEOUT)
        except Exception as e:
            print("getUpdates error:", e)
            time.sleep(3)
            continue

        for upd in updates:
            offset = upd["update_id"] + 1
            try:
                if "message" in upd:
                    handle_message(upd["message"])
                elif "callback_query" in upd:
                    handle_callback(upd["callback_query"])
                elif "chat_member" in upd:
                    handle_chat_member(upd["chat_member"])
            except Exception:
                traceback.print_exc()


if __name__ == "__main__":
    run()
