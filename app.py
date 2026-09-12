# -*- coding: utf-8 -*-
"""
app.py
------
بوت تيليغرام لمهرجان بغديدى السادس 2026 - شبيبة ملتقى الطاهرة.
Telegram bot for Baghdida Festival VI 2026 feedback survey.

يعمل عبر Webhook (مناسب للاستضافة المجانية على Render).
"""

import json
import logging
import os
import time

import telebot
from flask import Flask, request, abort
from telebot import types

import sheets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("baghdida-bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]  # رابط صفحة الاستبيان (GitHub Pages / Render Static)
WEBHOOK_SECRET_PATH = os.environ.get("WEBHOOK_SECRET_PATH", BOT_TOKEN)
ADMIN_IDS = {
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
}

class LoggingExceptionHandler(telebot.ExceptionHandler):
    """
    يمنع telebot من إخفاء الأخطاء بصمت، ويطبعها كاملة (Traceback) بالـ Logs.
    """
    def handle(self, exception):
        logger.exception("Unhandled exception inside a message handler: %s", exception)
        return True


bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", exception_handler=LoggingExceptionHandler())
app = Flask(__name__)


# ------------------------------------------------------------------
# أوامر المستخدمين العاديين
# ------------------------------------------------------------------

@bot.message_handler(commands=["start"])
def handle_start(message):
    user = message.from_user
    is_new = sheets.register_user(user.id, user.first_name, user.username)

    welcome_text = (
        "🕊️ <b>أهلاً بك في مهرجان بغديدى السادس 2026</b>\n"
        "على خطى مار فرنسيس الأسيزي، شاركنا رأيك ليكون المهرجان القادم أجمل.\n\n"
        "اضغط الزر أدناه لتعبئة استبيان التقييم 👇"
    )
    if not is_new:
        welcome_text += "\n\n<i>(حسابك مسجل مسبقاً معنا ✅)</i>"

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            text="تقييم المهرجان 📝",
            web_app=types.WebAppInfo(url=WEBAPP_URL),
        )
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.message_handler(commands=["survey", "تقييم"])
def handle_survey_shortcut(message):
    handle_start(message)


@bot.message_handler(content_types=["web_app_data"])
def handle_webapp_data(message):
    user = message.from_user
    try:
        answers = json.loads(message.web_app_data.data)
    except (ValueError, AttributeError):
        bot.send_message(message.chat.id, "⚠️ حدث خطأ بقراءة إجاباتك، حاول مرة أخرى.")
        return

    sheets.save_response(user.id, user.first_name, user.username, answers)

    bot.send_message(
        message.chat.id,
        "🙏 <b>شكراً لتقييمك!</b>\n"
        "تم تسجيل إجاباتك بنجاح، وسنصلك هنا بجدول اجتماعات الجمعة والسفرات القادمة.",
    )


# ------------------------------------------------------------------
# أوامر الأدمن
# ------------------------------------------------------------------

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@bot.message_handler(commands=["broadcast"])
def handle_broadcast(message):
    if not _is_admin(message.from_user.id):
        return  # تجاهل صامت لغير المخوّلين

    text = message.text.partition(" ")[2].strip()
    if not text:
        bot.reply_to(
            message,
            "استخدم الأمر هكذا:\n<code>/broadcast نص الإعلان هنا</code>",
        )
        return

    user_ids = sheets.get_all_user_ids()
    sent, failed = 0, 0
    status_msg = bot.reply_to(message, f"⏳ جارِ الإرسال إلى {len(user_ids)} شخص...")

    for uid in user_ids:
        try:
            bot.send_message(int(uid), text)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send to %s: %s", uid, exc)
            failed += 1
        time.sleep(0.05)  # احترام حدود تيليغرام لسرعة الإرسال (~30/ثانية)

    bot.edit_message_text(
        f"✅ تم الإرسال بنجاح إلى {sent} شخص. (فشل: {failed})",
        chat_id=status_msg.chat.id,
        message_id=status_msg.message_id,
    )


@bot.message_handler(commands=["stats"])
def handle_stats(message):
    if not _is_admin(message.from_user.id):
        return
    user_ids = sheets.get_all_user_ids()
    bot.reply_to(message, f"👥 عدد المسجلين حالياً: {len(user_ids)}")


# ------------------------------------------------------------------
# Webhook (Flask)
# ------------------------------------------------------------------

@app.route(f"/webhook/{WEBHOOK_SECRET_PATH}", methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") != "application/json":
        abort(403)
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200


@app.route("/", methods=["GET"])
def health_check():
    return "Baghdida Festival Bot is running ✅", 200


@app.route("/set_webhook", methods=["GET"])
def set_webhook_route():
    """
    زيارة هذا المسار مرة واحدة بعد النشر لتفعيل الـ Webhook تلقائياً.
    مثال: https://your-app.onrender.com/set_webhook
    """
    base_url = os.environ["PUBLIC_URL"].rstrip("/")
    webhook_url = f"{base_url}/webhook/{WEBHOOK_SECRET_PATH}"
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=webhook_url)
    return f"Webhook set to: {webhook_url}", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
