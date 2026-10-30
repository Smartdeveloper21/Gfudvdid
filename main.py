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

BOT_TOKEN = "8967754172:AAEw49Dv9i9Uo4L6CK-g1hr6Wa5pwBt2dY0"      # from @BotFather

OWNER_IDS = [
    8237042199,  # <-- your numeric Telegram user ID
]

# Credit & promo settings
CREDIT_BOT_USERNAME = "PollzyBot"
PROMO_BOT_URL = "https://t.me/PollzyBot"
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


def handle_confirm_question(user_id, chat_id
