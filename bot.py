import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import database as db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))

CHANNELS = ["@milliy_sertifikat_lider", "@milliy_liderr"]
PRIZE_CHANNEL_ID = -1003763206013
ADMIN_IDS = [6987211321, 5523761749]
REQUIRED_REFS = 5


def subscribe_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1-kanal 📢", url="https://t.me/milliy_sertifikat_lider"),
            InlineKeyboardButton("2-kanal 📢", url="https://t.me/milliy_liderr"),
        ],
        [InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")],
    ])


async def is_subscribed(user_id: int, bot) -> bool:
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                return False
        except Exception as e:
            logger.warning("get_chat_member error for %s: %s", channel, e)
            return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []

    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0][4:])
            if ref_id != user.id:
                referred_by = ref_id
        except ValueError:
            pass

    db.add_user(user.id, user.first_name, user.username, referred_by)

    await update.message.reply_text(
        f"Assalomu alaykum botga xush kelibsiz {user.first_name} 👋\n\n"
        "Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling 👇",
        reply_markup=subscribe_keyboard(),
    )


async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if not await is_subscribed(user.id, context.bot):
        await query.edit_message_text(
            "❌ Siz hali barcha kanallarga a'zo bo'lmagansiz!\n\n"
            "Iltimos, avval kanallarga a'zo bo'ling va keyin tekshiring 👇",
            reply_markup=subscribe_keyboard(),
        )
        return

    user_data = db.get_user(user.id)
    if not user_data:
        await query.edit_message_text("Xatolik yuz berdi. /start bosing.")
        return

    # Mark as verified on first successful check
    if not user_data["is_verified"]:
        db.verify_user(user.id)
        user_data = db.get_user(user.id)  # refresh after update

    # Process referral — runs regardless of whether they just verified or were already verified.
    # This handles users who opened the bot before clicking the reflink.
    # add_referral uses INSERT OR IGNORE so it's safe to call multiple times.
    referred_by = user_data["referred_by"]
    if referred_by and not db.referral_exists(referred_by, user.id):
        db.add_referral(referred_by, user.id)
        ref_count = db.get_ref_count(referred_by)
        remaining = max(0, REQUIRED_REFS - ref_count)

        try:
            await context.bot.send_message(
                referred_by,
                f"🎉 Sizda +1 ta do'st, jami {ref_count} ta, yana {remaining} ta kerak",
            )
        except Exception as e:
            logger.warning("Could not notify referrer %s: %s", referred_by, e)

        if ref_count >= REQUIRED_REFS:
            referrer_data = db.get_user(referred_by)
            if referrer_data and not referrer_data["prize_sent"]:
                db.mark_prize_notified(referred_by)
                try:
                    await context.bot.send_message(
                        referred_by,
                        "🏆 Qoyilmaqom, siz shartlarni bajardingiz endi sovg'angizni oling!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🎁 Sovg'ani olish", callback_data="get_prize")]
                        ]),
                    )
                except Exception as e:
                    logger.warning("Could not send prize msg to %s: %s", referred_by, e)

    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    ref_count = db.get_ref_count(user.id)
    remaining = max(0, REQUIRED_REFS - ref_count)

    if ref_count >= REQUIRED_REFS:
        status_line = f"✅ Do'stlar: {ref_count} ta — siz shartni bajardingiz!"
    else:
        status_line = f"Do'stlar: {ref_count} ta | Yana {remaining} ta kerak"

    await query.edit_message_text(
        "✅ Ajoyib!\n\n"
        "Sovg'ani olish uchun atiga 5 ta do'stingizni taklif qiling!\n\n"
        f"Sizning havola:\n{ref_link}\n\n"
        f"{status_line}",
    )


async def get_prize_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    ref_count = db.get_ref_count(user.id)
    if ref_count < REQUIRED_REFS:
        await query.answer("Siz hali shartlarni bajarmadingiz!", show_alert=True)
        return

    user_data = db.get_user(user.id)
    if user_data and user_data["prize_link_sent"]:
        await query.answer("Siz allaqachon sovg'ani oldingiz!", show_alert=True)
        return

    try:
        invite = await context.bot.create_chat_invite_link(
            PRIZE_CHANNEL_ID,
            member_limit=1,
        )
        db.mark_prize_link_sent(user.id)
        await query.edit_message_text(
            f"🎁 Mana sizning maxsus havolangiz:\n\n{invite.invite_link}"
        )
    except Exception as e:
        logger.error("Error creating invite link: %s", e)
        await query.answer(
            "Xatolik yuz berdi. Admin bilan bog'laning!", show_alert=True
        )


async def odam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    count = db.get_user_count()
    await update.message.reply_text(f"👥 Jami foydalanuvchilar: {count} ta")


async def xabar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /xabar <matn>")
        return

    text = " ".join(context.args)
    user_ids = db.get_all_user_ids()
    sent, failed = 0, 0

    for uid in user_ids:
        try:
            await context.bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"📨 Xabar yuborildi\n✅ Muvaffaqiyatli: {sent} ta\n❌ Xato: {failed} ta"
    )


async def addref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Foydalanish: /addref <userid> <count>")
        return

    try:
        target_id = int(context.args[0])
        count = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri format! Masalan: /addref 123456789 5")
        return

    db.add_fake_refs(target_id, count)
    new_count = db.get_ref_count(target_id)
    await update.message.reply_text(
        f"✅ {target_id} ga {count} ta referal qo'shildi.\nJami: {new_count} ta"
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("odam", odam_command))
    app.add_handler(CommandHandler("xabar", xabar_command))
    app.add_handler(CommandHandler("addref", addref_command))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(get_prize_callback, pattern="^get_prize$"))

    if WEBHOOK_URL:
        logger.info("Starting in WEBHOOK mode on port %s", PORT)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            url_path=BOT_TOKEN,
            secret_token=None,
        )
    else:
        logger.info("Starting in POLLING mode (development)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
