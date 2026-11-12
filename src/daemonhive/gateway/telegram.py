"""Telegram gateway: the only thing exposed to the outside world.

It accepts messages from exactly one chat id (yours) and forwards them to Concierge.
"""

from __future__ import annotations

import logging
import os

import httpx
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

log = logging.getLogger("daemonhive.gateway")
CONCIERGE = os.environ.get("CONCIERGE_URL", "http://concierge:8100")
ALLOWED_CHAT = int(os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "0"))


async def on_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None or not update.message.text:
        return
    if update.effective_chat.id != ALLOWED_CHAT:
        log.warning("ignored message from chat %s", update.effective_chat.id)
        return
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{CONCIERGE}/inbound",
                         json={"chat_id": update.effective_chat.id, "text": update.message.text})
    reply = r.json().get("reply") if r.is_success else "Something broke on my side. Logged it."
    if reply:
        await update.message.reply_text(reply)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling()


if __name__ == "__main__":
    main()
