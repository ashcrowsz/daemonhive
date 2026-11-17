"""Morning brief CronJob: plan today's deep-work block and send it to Telegram."""

from __future__ import annotations

import asyncio
import os
from datetime import date

import httpx

from daemonhive.agents.work.planner import plan_deep_work
from daemonhive.common.a2a import A2AClient, TaskState


async def main() -> None:
    today = date.today()
    a2a = A2AClient("work", os.environ.get("A2A_TOKEN_WORK", "dev-work"))
    res = await a2a.send(
        os.environ.get("WELLBEING_URL", "http://wellbeing:8102"),
        "recovery_summary",
        {"until": today.isoformat(), "days": 1},
    )
    short_night = res.state is TaskState.completed and "SleepDeficit" in res.output.get("flags", [])
    # TODO(#2): pull busy slots from Google Calendar via work-mcp
    block = plan_deep_work(today, [], short_night=short_night)
    text = (
        f"Morning. Deep work {block.start:%H:%M}-{block.end:%H:%M}"
        + (" (pushed back, short night)." if short_night else ".")
        if block
        else "No 2h slot today, protect tomorrow morning instead."
    )
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_ALLOWED_CHAT_ID"]
    async with httpx.AsyncClient() as c:
        await c.post(
            f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text}
        )


if __name__ == "__main__":
    asyncio.run(main())
