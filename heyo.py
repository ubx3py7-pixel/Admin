# bg_conflict_fixed.py  -- PART 1
import logging
import sqlite3
import time
from typing import Optional, List, Tuple, Union, Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    User as TgUser,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = "8375060248:AAEOCPp8hU2lBYqDGt1SYwluQDQgqmDfWWA"
REQUIRED_CHANNEL: Union[str, int] = "@techyspyther"
FORCE_JOIN_CHANNELS = [REQUIRED_CHANNEL]
SUPER_ADMINS: List[int] = []

GROUP_NO_ADMIN_MSG = "Hey !!! I don't the admin rights now please give me and hit /admin to promote"
DM_NO_ADMIN_MSG = "Hey!!! {adder} You added me in the {group} i don't have rights there please give me and hit /admin to promote"

PROMOTED_TEMPLATE = (
    "Promoted 💐 {targets} for {adder}\n\n"
    "Thanks for using the bot created by - @Firedrop_69 💕 Keep using and promoting the bot 😄!!!!!!!!"
)

DM_WELCOME = (
    "🎀 Hey 👋!!{username} u have finally come to me !!\n"
    "Now enjoy admin promotion bot by - @Firedrop_69 and let it handle you ur admin promotion 😉"
)

DB = "adminpromo.db"

# In-memory pending consents:
# key = f"{chat_id}:{owner_id}" -> {"targets": [user_id,...], "ts": timestamp}
PENDING_CONSENTS: Dict[str, Dict[str, Any]] = {}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS targets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            target TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS group_adders(
            group_id INTEGER PRIMARY KEY,
            adder_id INTEGER
        )"""
    )
    conn.commit()
    conn.close()


def add_target(owner_id: int, target: str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO targets(owner_id, target) VALUES (?, ?)", (owner_id, target))
    conn.commit()
    conn.close()


def remove_target(owner_id: int, target: str) -> bool:
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM targets WHERE owner_id=? AND target=?", (owner_id, target))
    ok = c.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def list_targets(owner_id: int) -> List[str]:
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT target FROM targets WHERE owner_id=?", (owner_id,))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows


def clear_targets(owner_id: int):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM targets WHERE owner_id=?", (owner_id,))
    conn.commit()
    conn.close()


def set_group_adder(group_id: int, adder_id: int):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT OR REPLACE INTO group_adders(group_id, adder_id) VALUES (?, ?)",
        (group_id, adder_id),
    )
    conn.commit()
    conn.close()


def get_group_adder(group_id: int) -> Optional[int]:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT adder_id FROM group_adders WHERE group_id=?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_all_targets() -> List[Tuple[int, str]]:
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT owner_id, target FROM targets").fetchall()
    conn.close()
    return rows
    # bg_conflict_fixed.py  -- PART 2

# ---------------- HELPERS / UTILITIES ----------------
def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMINS


def is_group_chat(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.type in ("group", "supergroup")


async def resolve_username_to_user(context: ContextTypes.DEFAULT_TYPE, username_or_id: str) -> Optional[TgUser]:
    try:
        if username_or_id.startswith("@"):
            return await context.bot.get_chat(username_or_id)
        if username_or_id.isdigit() or (username_or_id.startswith("-") and username_or_id[1:].isdigit()):
            return await context.bot.get_chat(int(username_or_id))
        return await context.bot.get_chat("@" + username_or_id)
    except Exception:
        return None


async def bot_can_promote(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    try:
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(chat_id, me.id)
        return bool(getattr(member, "can_promote_members", False))
    except Exception as e:
        log.debug(f"bot_can_promote error: {e}")
        return False


async def user_in_required_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    candidates = []
    if isinstance(REQUIRED_CHANNEL, int):
        candidates.append(REQUIRED_CHANNEL)
    else:
        candidates.append(REQUIRED_CHANNEL)
        if REQUIRED_CHANNEL.lstrip("-").isdigit():
            candidates.append(int(REQUIRED_CHANNEL))
    for cref in candidates:
        try:
            mem = await context.bot.get_chat_member(cref, user_id)
            if mem.status == ChatMemberStatus.ADMINISTRATOR or mem.status == "creator" or mem.status == "member":
                return True
        except Exception:
            continue
    return False


# ---------------- FORCE-JOIN / CHANNEL OBSTRUCTION LOGIC ----------------
async def check_user_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if is_super_admin(user_id):
        return True

    is_group = is_group_chat(update)
    not_joined = []
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status not in ("member", "administrator", "creator"):
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)

    if not_joined:
        if is_group:
            await update.effective_message.reply_text(
                f"⚠️ @{update.effective_user.username or update.effective_user.first_name}, please join the required channel(s): {', '.join(map(str, not_joined))} and then DM me."
            )
        else:
            keyboard = []
            for channel in not_joined:
                if isinstance(channel, str) and channel.startswith("@"):
                    keyboard.append([InlineKeyboardButton(f"🔗 Join {channel}", url=f"https://t.me/{channel.lstrip('@')}")])
                else:
                    keyboard.append([InlineKeyboardButton(f"🔗 Open {channel}", callback_data="noop")])
            keyboard.append([InlineKeyboardButton("✅ I've joined — Re-check", callback_data="check_joined")])
            keyboard.append([InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")])
            await update.effective_message.reply_text(
                "You must join the required channel(s) to use this bot. Use the buttons and press re-check.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        return False

    return True


# ---------------- CONSENT HELPERS ----------------
def make_consent_key(chat_id: int, owner_id: int) -> str:
    return f"{chat_id}:{owner_id}"


def store_pending_consent(chat_id: int, owner_id: int, target_ids: List[int]):
    key = make_consent_key(chat_id, owner_id)
    PENDING_CONSENTS[key] = {"targets": target_ids, "ts": int(time.time())}


def pop_pending_consent(chat_id: int, owner_id: int) -> Optional[List[int]]:
    key = make_consent_key(chat_id, owner_id)
    data = PENDING_CONSENTS.pop(key, None)
    return data["targets"] if data else None


# ---------------- DM / CALLBACK HANDLERS (private-only checks inside handlers) ----------------
async def handle_check_joined_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq or not cq.message or cq.message.chat.type != "private":
        if cq:
            await cq.answer()
        return
    await cq.answer()
    user = cq.from_user

    not_joined = []
    for channel in FORCE_JOIN_CHANNELS:
        try:
            mem = await context.bot.get_chat_member(channel, user.id)
            if mem.status not in ("member", "administrator", "creator"):
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)

    if not_joined:
        await cq.answer("You still haven't joined all required channels.", show_alert=True)
        return

    try:
        await cq.message.delete()
    except Exception:
        pass

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add user", callback_data="quick_add")],
            [InlineKeyboardButton("📋 My watchlist", callback_data="quick_list")],
            [InlineKeyboardButton("❓ Help", callback_data="quick_help")],
        ]
    )
    await context.bot.send_message(user.id, DM_WELCOME.format(username=user.username or user.first_name), reply_markup=kb)


async def back_to_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq or not cq.message or cq.message.chat.type != "private":
        if cq:
            await cq.answer()
        return
    await cq.answer()
    user = cq.from_user
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add user", callback_data="quick_add")],
            [InlineKeyboardButton("📋 My watchlist", callback_data="quick_list")],
            [InlineKeyboardButton("❓ Help", callback_data="quick_help")],
        ]
    )
    try:
        await cq.edit_message_text(DM_WELCOME.format(username=user.username or user.first_name), reply_markup=kb)
    except Exception:
        await context.bot.send_message(user.id, DM_WELCOME.format(username=user.username or user.first_name), reply_markup=kb)


async def quick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq or not cq.message or cq.message.chat.type != "private":
        if cq:
            await cq.answer()
        return
    await cq.answer()
    data = cq.data or ""
    user = cq.from_user

    if data == "quick_add":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")]])
        return await cq.edit_message_text("Send `/add <user numeric id>` in this chat.", reply_markup=kb)

    if data == "quick_list":
        items = list_targets(user.id)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")]])
        if not items:
            return await cq.edit_message_text("Your watchlist is empty.", reply_markup=kb)
        text = "Your watchlist:\n" + "\n".join(f"- {t}" for t in items)
        return await cq.edit_message_text(text, reply_markup=kb)

    if data == "quick_help":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")]])
        text = """DM COMMANDS:- 
        /add - ➕ use with user id to add watchlist 
        /remove - to remove 
        /clear - to remove all
        /list /start\nGroup: /admin- to start promote 
        /panel - real time promotion"""
        return await cq.edit_message_text(text, reply_markup=kb)

    return await cq.edit_message_text("Unknown action.")
    # bg_conflict_fixed.py  -- PART 3

# ---------------- DM COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_group_chat(update):
        await update.message.reply_text("I'm the admin promotion bot. Add me to your group and make me admin, then use /admin.")
        return
    ok = await check_user_membership(update, context)
    if not ok:
        return
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add user", callback_data="quick_add")],
            [InlineKeyboardButton("📋 My watchlist", callback_data="quick_list")],
            [InlineKeyboardButton("❓ Help", callback_data="quick_help")],
        ]
    )
    await update.message.reply_text(DM_WELCOME.format(username=update.effective_user.username or update.effective_user.first_name), reply_markup=kb)


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_membership(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /add <user number id>")
        return
    target = context.args[0].strip()
    add_target(update.effective_user.id, target)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")]])
    await update.message.reply_text(f"Added `{target}` to your watchlist.", parse_mode="Markdown", reply_markup=kb)


async def remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_membership(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /remove <username_or_id>")
        return
    target = context.args[0].strip()
    ok = remove_target(update.effective_user.id, target)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")]])
    if ok:
        await update.message.reply_text(f"Removed `{target}`.", parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(f"`{target}` not found.", parse_mode="Markdown", reply_markup=kb)


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_membership(update, context):
        return
    clear_targets(update.effective_user.id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")]])
    await update.message.reply_text("All targets cleared.", reply_markup=kb)


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user_membership(update, context):
        return
    items = list_targets(update.effective_user.id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to menu", callback_data="back_menu")]])
    if not items:
        return await update.message.reply_text("Your watchlist is empty.", reply_markup=kb)
    text = "Your watchlist:\n" + "\n".join(f"- {t}" for t in items)
    await update.message.reply_text(text, reply_markup=kb)


# ---------------- GROUP EVENTS ----------------
async def new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    me = await context.bot.get_me()
    for new in update.message.new_chat_members:
        if new.id == me.id:
            adder = update.message.from_user
            if adder:
                set_group_adder(update.effective_chat.id, adder.id)
                await update.message.reply_text(f"Hello! Adder recorded: {adder.first_name}. Use /admin to promote.")


# ---------------- CONSENT CALLBACK ----------------
async def consent_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called when owner presses Yes in DM to allow promotion of their watchlist in a group.
    Callback data format: consent|<chat_id>|<owner_id>
    """
    cq = update.callback_query
    if not cq:
        return
    # only process in private DM and only if the pressing user is the owner
    if not cq.message or cq.message.chat.type != "private":
        await cq.answer()
        return
    parts = (cq.data or "").split("|")
    if len(parts) != 3 or parts[0] != "consent":
        await cq.answer()
        return
    _, chat_id_s, owner_id_s = parts
    try:
        chat_id = int(chat_id_s)
        owner_id = int(owner_id_s)
    except Exception:
        await cq.answer("Invalid data.", show_alert=True)
        return

    # ensure the button presser is indeed owner
    if cq.from_user.id != owner_id:
        await cq.answer("Only the owner can confirm this.", show_alert=True)
        return

    await cq.answer("Thanks — promoting your watchlist now.")

    targets = pop_pending_consent(chat_id, owner_id)
    if not targets:
        await context.bot.send_message(owner_id, "No pending targets to promote (expired or already handled).")
        return

    # final checks and promote
    if not await bot_can_promote(context, chat_id):
        await context.bot.send_message(owner_id, "I don't have promote rights in that group anymore.")
        return

    promoted_users = []
    for tid in targets:
        try:
            member = await context.bot.get_chat_member(chat_id, tid)
        except Exception:
            continue
        if member.status in (ChatMemberStatus.ADMINISTRATOR, "creator"):
            promoted_users.append(tid)
            continue
        try:
            await context.bot.promote_chat_member(
                chat_id=chat_id,
                user_id=tid,
                can_change_info=True,
                can_delete_messages=True,
                can_invite_users=True,
                can_restrict_members=True,
                can_pin_messages=True,
                can_promote_members=False,
            )
            promoted_users.append(tid)
        except Exception:
            continue

    # announce in group
    if promoted_users:
        try:
            owner_chat = await context.bot.get_chat(owner_id)
            owner_name = "@" + owner_chat.username if getattr(owner_chat, "username", None) else owner_chat.first_name
        except Exception:
            owner_name = str(owner_id)
        targets_s = ", ".join(str(u) for u in promoted_users)
        await context.bot.send_message(chat_id, PROMOTED_TEMPLATE.format(targets=targets_s, adder=owner_name))
    else:
        await context.bot.send_message(owner_id, "No users were promoted (they may have left the group or are already admins).")


# ---------------- ADMIN COMMAND (conflict-resolved) ----------------
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    actor = update.effective_user
    # actor must be group admin to run /admin
    try:
        actor_member = await context.bot.get_chat_member(chat.id, actor.id)
        if actor_member.status not in ("administrator", "creator"):
            await update.message.reply_text("You must be a group admin to use /admin.")
            return
    except Exception:
        await update.message.reply_text("Unable to verify your admin status.")
        return

    if not await bot_can_promote(context, chat.id):
        await update.message.reply_text(GROUP_NO_ADMIN_MSG)
        return

    rows = get_all_targets()
    if not rows:
        await update.message.reply_text("No targets in watchlist.")
        return

    # build map of owner -> list of target user objects present in group
    present_map: Dict[int, List[TgUser]] = {}
    for owner, target in rows:
        tgt = await resolve_username_to_user(context, target)
        if not tgt:
            continue
        try:
            # check target present in this group
            await context.bot.get_chat_member(chat.id, tgt.id)
            present_map.setdefault(owner, []).append(tgt)
        except Exception:
            continue

    # if actor has entries, promote only their entries immediately
    promoted = []
    actor_targets = present_map.get(actor.id, [])
    for userobj in actor_targets:
        try:
            member = await context.bot.get_chat_member(chat.id, userobj.id)
        except Exception:
            continue
        if member.status in (ChatMemberStatus.ADMINISTRATOR, "creator"):
            promoted.append((actor.id, userobj))
            continue
        try:
            await context.bot.promote_chat_member(
                chat_id=chat.id,
                user_id=userobj.id,
                can_change_info=True,
                can_delete_messages=True,
                can_invite_users=True,
                can_restrict_members=True,
                can_pin_messages=True,
                can_promote_members=False,
            )
            promoted.append((actor.id, userobj))
        except Exception:
            continue

    # For other owners present, send consent DM if they are admin with can_promote_members True
    for owner, targets in present_map.items():
        if owner == actor.id:
            continue
        try:
            owner_member = await context.bot.get_chat_member(chat.id, owner)
        except Exception:
            continue

        # owner must be in group (we already ensured) — now check their admin status
        if owner_member.status in ("administrator", "creator"):
            can_promote_flag = getattr(owner_member, "can_promote_members", False)
            if can_promote_flag:
                # store pending consent and DM owner asking for permission
                target_ids = [u.id for u in targets]
                store_pending_consent(chat.id, owner, target_ids)
                consent_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes — Promote my watchlist", callback_data=f"consent|{chat.id}|{owner}")],
                ])
                try:
                    await context.bot.send_message(
                        owner,
                        f"Hey {owner_member.user.first_name or owner_member.user.username}! I found you in the group \"{chat.title or chat.id}\". Do you want me to promote your watchlist here?",
                        reply_markup=consent_kb,
                    )
                except Exception:
                    # can't DM owner (maybe privacy). Inform actor that owner couldn't be messaged.
                    await update.message.reply_text(f"Could not DM owner {owner} to request consent (they may have privacy settings).")
            else:
                # owner is admin but lacks permission to add admins
                try:
                    await context.bot.send_message(owner, f"Hi — I found you in \"{chat.title or chat.id}\". You are an admin but you don't have the permission to add new admins. Ask a higher admin to give you that permission if you want promotions.")
                except Exception:
                    pass
                # inform actor in group
                await update.message.reply_text(f"{owner} is admin but lacks promote permission; their targets won't be promoted automatically.")
        else:
            # owner is not admin — DM them telling they need admin
            try:
                await context.bot.send_message(owner, f"Hi — I found you in the group \"{chat.title or chat.id}\", but you are not an admin. Get admin rights and I can promote your watchlist if you request.")
            except Exception:
                pass
            await update.message.reply_text(f"{owner} is not admin; their targets won't be promoted.")

    # announce actor promotions
    if promoted:
        mapping: Dict[int, List[TgUser]] = {}
        for owner, userobj in promoted:
            mapping.setdefault(owner, []).append(userobj)
        for owner, users in mapping.items():
            try:
                owner_chat = await context.bot.get_chat(owner)
                owner_name = "@" + owner_chat.username if getattr(owner_chat, "username", None) else owner_chat.first_name
            except Exception:
                owner_name = str(owner)
            targets_s = ", ".join(u.username or str(u.id) for u in users)
            await context.bot.send_message(chat.id, PROMOTED_TEMPLATE.format(targets=targets_s, adder=owner_name))
    else:
        await update.message.reply_text("No users from your watchlist were promoted (maybe they are already admins).")


# ---------------- PANEL (shows only actor's targets) ----------------
async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return
    actor = update.effective_user
    # actor must be admin
    try:
        actor_member = await context.bot.get_chat_member(chat.id, actor.id)
        if actor_member.status not in ("administrator", "creator"):
            await update.message.reply_text("You must be a group admin to open the panel.")
            return
    except Exception:
        await update.message.reply_text("Unable to verify your admin status.")
        return

    # only show actor's present targets
    rows = get_all_targets()
    found = []
    for owner, target in rows:
        if owner != actor.id:
            continue
        tgt = await resolve_username_to_user(context, target)
        if not tgt:
            continue
        try:
            await context.bot.get_chat_member(chat.id, tgt.id)
            found.append(tgt)
        except Exception:
            continue

    if not found:
        await update.message.reply_text("No users from your watchlist are in this group.")
        return

    keyboard = []
    for tgt in found:
        label = f"Promote {tgt.first_name or tgt.username or tgt.id}"
        cbdata = f"promote|{chat.id}|{tgt.id}|{actor.id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cbdata)])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_menu")])
    await update.message.reply_text("Panel — select users to promote:", reply_markup=InlineKeyboardMarkup(keyboard))


# ---------------- PROMOTE CALLBACK (from panel) ----------------
async def promote_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq:
        return
    # If pressed inside DM menu, ensure it's private; if in group it's fine
    await cq.answer()
    parts = (cq.data or "").split("|")
    if len(parts) != 4 or parts[0] != "promote":
        return
    _, chat_id_s, target_id_s, owner_id_s = parts
    try:
        chat_id = int(chat_id_s); target_id = int(target_id_s); owner_id = int(owner_id_s)
    except Exception:
        await cq.answer("Invalid ids", show_alert=True)
        return

    # Only allow promotion from group panel if the caller is the owner (actor)
    # If the callback was pressed in group (cq.message.chat.type == 'supergroup' or 'group'),
    # the user pressing must be owner_id (invoker).
    if cq.message and cq.message.chat.type in ("group", "supergroup"):
        if cq.from_user.id != owner_id:
            await cq.answer("Only the admin who opened the panel can press this.", show_alert=True)
            return

    # perform promotion
    if not await bot_can_promote(context, chat_id):
        await cq.answer("I don't have promote rights.", show_alert=True)
        return

    try:
        member = await context.bot.get_chat_member(chat_id, target_id)
    except Exception:
        await cq.answer("Target not in group.", show_alert=True)
        return

    if member.status in (ChatMemberStatus.ADMINISTRATOR, "creator"):
        await cq.answer("Already admin.", show_alert=True)
        return

    try:
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            can_change_info=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False,
        )
    except Exception:
        await cq.answer("Promotion failed.", show_alert=True)
        return

    # announce
    try:
        owner_chat = await context.bot.get_chat(owner_id)
        owner_name = "@" + owner_chat.username if getattr(owner_chat, "username", None) else owner_chat.first_name
    except Exception:
        owner_name = str(owner_id)
    try:
        target_chat = await context.bot.get_chat(target_id)
        target_label = target_chat.username or target_chat.first_name or str(target_id)
    except Exception:
        target_label = str(target_id)

    await context.bot.send_message(chat_id, PROMOTED_TEMPLATE.format(targets=target_label, adder=owner_name))
    await cq.answer("Promoted.")


# ---------------- REGISTER & RUN ----------------
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # DM handlers
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("add", add_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("remove", remove_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("clear", clear_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("list", list_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help", lambda u, c: c.bot.send_message(u.effective_chat.id, "DM: /add /remove /clear /list /start\nGroup: /admin /panel")))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_check_joined_cb, pattern="^check_joined$"))
    app.add_handler(CallbackQueryHandler(back_to_menu_cb, pattern="^back_menu$"))
    app.add_handler(CallbackQueryHandler(quick_cb, pattern="^quick_"))
    app.add_handler(CallbackQueryHandler(consent_cb, pattern="^consent\\|"))
    app.add_handler(CallbackQueryHandler(promote_cb, pattern=r"^promote\\|"))

    # Group handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.ChatType.GROUPS, new_chat_members))
    app.add_handler(CommandHandler("admin", admin_cmd, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("panel", panel_cmd, filters=filters.ChatType.GROUPS))

    log.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()