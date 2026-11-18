"""Morning brief CronJob: plan today's deep-work block and send it to Telegram."""

from __future__ import annotations

import asyncio
import os
from datetime import date

import httpx

from daemonhive.agents.work.app import plan_message


async def main() -> None:
    text = "Morning. " + await plan_message(date.today())
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_ALLOWED_CHAT_ID"]
    async with httpx.AsyncClient() as c:
        await c.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
        )


if __name__ == "__main__":
    asyncio.run(main())
