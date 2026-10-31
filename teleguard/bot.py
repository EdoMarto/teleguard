"""Telegram wiring (python-telegram-bot v21). The decisions live in the pure
modules (risk, spam, antiflood, captcha, fileid); this file connects them to
Telegram events."""

from __future__ import annotations

import logging
import time

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import captcha, risk, spam
from .antiflood import FloodTracker
from .config import Config
from .fileid import datacenter_from_file_id

log = logging.getLogger("teleguard")

_MUTED = ChatPermissions(can_send_messages=False)
_UNMUTED = ChatPermissions(
    can_send_messages=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)


class Guard:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.flood = FloodTracker(config.flood_max, config.flood_seconds)
        self.spam_config = spam.SpamConfig()
        self.risk_config = risk.RiskConfig(config.suspicious_datacenters, config.risk_threshold)
        self.pending: dict[tuple[int, int], str] = {}  # (chat, user) -> captcha answer
        self.messages: dict[tuple[int, int], int] = {}  # (chat, user) -> message count
        self.warns: dict[tuple[int, int], int] = {}  # (chat, user) -> warnings

    # -- joins ----------------------------------------------------------------

    async def on_join(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        result = update.chat_member
        if not result:
            return
        if result.new_chat_member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            # User left or was removed: drop their in-memory state so the dicts
            # do not grow without bound.
            self._prune(result.chat.id, result.new_chat_member.user.id)
            return
        if result.new_chat_member.status != ChatMemberStatus.MEMBER:
            return
        if result.old_chat_member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            return

        user = result.new_chat_member.user
        chat = result.chat
        if user.is_bot:
            return

        has_photo, datacenter = await self._photo_info(context, user.id)
        profile = risk.Profile(
            user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username,
            has_photo=has_photo,
            datacenter=datacenter,
            is_premium=bool(getattr(user, "is_premium", False)),
        )
        points, reasons = risk.score(profile, self.risk_config)
        suspicious = risk.is_suspicious(profile, self.risk_config)
        log.info("Join %s (risk %d: %s)", user.id, points, ", ".join(reasons) or "clean")

        try:
            await context.bot.restrict_chat_member(chat.id, user.id, _MUTED)
            challenge = captcha.make_challenge(harder=suspicious)
            self.pending[(chat.id, user.id)] = challenge.answer

            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(opt, callback_data=f"cap:{user.id}:{opt}") for opt in challenge.options]]
            )
            await context.bot.send_message(
                chat.id,
                f"👋 {user.mention_html()}, per entrare rispondi: <b>{challenge.question}</b>\n"
                f"Hai {self.config.captcha_timeout} secondi.",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            context.job_queue.run_once(
                self._captcha_timeout,
                self.config.captcha_timeout,
                data=(chat.id, user.id),
                name=f"cap:{chat.id}:{user.id}",
            )
        except Exception as exc:
            # If captcha setup fails after muting, do not leave the user stuck.
            log.warning("Captcha setup failed for %s: %s", user.id, exc)
            self.pending.pop((chat.id, user.id), None)
            try:
                await context.bot.restrict_chat_member(chat.id, user.id, _UNMUTED)
            except Exception:
                pass

    async def _photo_info(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> tuple[bool, int | None]:
        """Return (has_photo, datacenter). Photo presence is determined from
        total_count so a file_id that fails to decode is not mistaken for
        "no photo"; the datacenter decode is kept separate."""
        try:
            photos = await context.bot.get_user_profile_photos(user_id, limit=1)
            if photos.total_count and photos.photos:
                return True, datacenter_from_file_id(photos.photos[0][-1].file_id)
            return False, None
        except Exception as exc:
            log.debug("Profile photo lookup failed for %s: %s", user_id, exc)
            return False, None

    async def on_captcha(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        _, target_id, choice = query.data.split(":", 2)
        if query.from_user.id != int(target_id):
            await query.answer("Non è la tua verifica.", show_alert=True)
            return

        chat_id = query.message.chat_id
        key = (chat_id, int(target_id))
        answer = self.pending.get(key)
        if answer is None:
            await query.answer()
            return

        if choice == answer:
            self.pending.pop(key, None)
            await query.answer()
            await context.bot.restrict_chat_member(chat_id, query.from_user.id, _UNMUTED)
            await query.message.edit_text(f"✅ {query.from_user.mention_html()} verificato.", parse_mode="HTML")
            await context.bot.send_message(chat_id, self.config.welcome_text)
        else:
            self.pending.pop(key, None)
            await self._kick(context, chat_id, query.from_user.id)
            await query.message.edit_text("❌ Risposta errata. Utente rimosso.")

    async def _captcha_timeout(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id, user_id = context.job.data
        if self.pending.pop((chat_id, user_id), None) is None:
            return  # already solved
        await self._kick(context, chat_id, user_id)
        await context.bot.send_message(chat_id, "⏰ Verifica non completata: utente rimosso.")

    # -- messages -------------------------------------------------------------

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        user = update.effective_user
        if not message or not user or update.effective_chat.type == ChatType.PRIVATE:
            return

        key = (update.effective_chat.id, user.id)
        count = self.messages.get(key, 0)

        if self.flood.is_flooding(user.id, time.time()):
            await context.bot.restrict_chat_member(key[0], user.id, _MUTED)
            await message.reply_text("🚦 Troppi messaggi: sei stato silenziato.")
            return

        spammy, reason = spam.is_spam(
            message.text or message.caption or "",
            message_count=count,
            is_forwarded_from_channel=bool(message.forward_origin),
            config=self.spam_config,
        )
        if spammy:
            try:
                await message.delete()
            except Exception:
                pass
            await self._warn(context, key, reason)
            return

        self.messages[key] = count + 1

    # -- moderation commands --------------------------------------------------

    async def _is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        member = await update.effective_chat.get_member(update.effective_user.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)

    async def _target(self, update: Update) -> int | None:
        reply = update.effective_message.reply_to_message
        return reply.from_user.id if reply else None

    async def _target_is_admin(self, update: Update, target: int) -> bool:
        member = await update.effective_chat.get_member(target)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)

    async def cmd_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._is_admin(update, context):
            return
        target = await self._target(update)
        if target:
            if await self._target_is_admin(update, target):
                await update.effective_message.reply_text("⛔ Non puoi bannare un amministratore.")
                return
            await context.bot.ban_chat_member(update.effective_chat.id, target)
            await update.effective_message.reply_text("🔨 Utente bannato.")

    async def cmd_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._is_admin(update, context):
            return
        target = await self._target(update)
        if target:
            if await self._target_is_admin(update, target):
                await update.effective_message.reply_text("⛔ Non puoi silenziare un amministratore.")
                return
            await context.bot.restrict_chat_member(update.effective_chat.id, target, _MUTED)
            await update.effective_message.reply_text("🔇 Utente silenziato.")

    async def cmd_warn(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._is_admin(update, context):
            return
        target = await self._target(update)
        if target:
            await self._warn(context, (update.effective_chat.id, target), "avviso manuale")

    # -- helpers --------------------------------------------------------------

    async def _warn(self, context: ContextTypes.DEFAULT_TYPE, key: tuple[int, int], reason: str) -> None:
        count = self.warns.get(key, 0) + 1
        self.warns[key] = count
        chat_id, user_id = key
        if count >= self.config.warn_limit:
            await self._kick(context, chat_id, user_id)
            await context.bot.send_message(chat_id, f"🔨 Utente rimosso dopo {count} avvisi ({reason}).")
            self.warns.pop(key, None)
        else:
            await context.bot.send_message(
                chat_id, f"⚠️ Avviso {count}/{self.config.warn_limit} ({reason})."
            )

    async def _kick(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)  # ban+unban = kick, can rejoin
        self._prune(chat_id, user_id)

    def _prune(self, chat_id: int, user_id: int) -> None:
        """Drop all in-memory state for a (chat, user) pair."""
        key = (chat_id, user_id)
        self.pending.pop(key, None)
        self.messages.pop(key, None)
        self.warns.pop(key, None)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.exception("Handler error", exc_info=context.error)


def build_application(config: Config) -> Application:
    if not config.token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN (see .env.example).")

    guard = Guard(config)
    app = Application.builder().token(config.token).build()
    app.add_handler(ChatMemberHandler(guard.on_join, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(guard.on_captcha, pattern=r"^cap:"))
    app.add_handler(CommandHandler("ban", guard.cmd_ban))
    app.add_handler(CommandHandler("mute", guard.cmd_mute))
    app.add_handler(CommandHandler("warn", guard.cmd_warn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, guard.on_message))
    app.add_error_handler(guard.on_error)
    return app
