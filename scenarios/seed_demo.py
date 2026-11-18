"""Seed a week of history so today's live workout triggers the reference scenario.

Everything goes through Concierge's /inbound, exactly like a Telegram message would,
so the routing, the A2A hops and the database writes all show up in the logs.

    python -m scenarios.seed_demo                 # concierge on localhost:8100
    python -m scenarios.seed_demo --print-today   # just print the message to send live

Relative to today (D):
  D-7  push day: bench 120 kg 3x8, OHP 60 kg 3x8
  D-3..D-1  nights of 5.0 / 5.5 / 5.0 h, ~2,200 kcal/day (target 2,800)
Then send today's session from Telegram and Fitness sees a -62% bench volume drop.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import httpx


def seed_messages(today: date) -> list[str]:
    d = lambda n: (today - timedelta(days=n)).isoformat()
    msgs = [f"Push {d(7)}\nBench Press 120kg 3x8 RPE 8\nOHP 60kg 3x8\nDips BW 3x10"]
    for n, hours in ((3, 5.0), (2, 5.5), (1, 5.0)):
        msgs.append(f"{d(n)} slept {hours:g}h")
    for n in (3, 2, 1):
        msgs += [
            f"{d(n)} breakfast oats and eggs 600 kcal",
            f"{d(n)} lunch chicken rice 800 kcal",
            f"{d(n)} dinner pasta 800 kcal",
        ]
    return msgs


def todays_session(today: date) -> str:
    return f"Push {today.isoformat()}\nBench Press 120kg 3x3 RPE 9\nOHP 60kg 3x8\n# felt flat today"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concierge", default="http://localhost:8100")
    ap.add_argument("--print-today", action="store_true")
    args = ap.parse_args()
    today = date.today()
    if not args.print_today:
        with httpx.Client(timeout=300) as c:
            for text in seed_messages(today):
                r = c.post(f"{args.concierge}/inbound", json={"chat_id": 0, "text": text})
                r.raise_for_status()
                body = r.json()
                first = text.splitlines()[0]
                print(f"-> {first:<45} [{body['route']}] {body['reply'][:70]}")
    print("\nNow send this from Telegram (or POST it to /inbound):\n")
    print(todays_session(today))
    print("\nthen: plan my day")


if __name__ == "__main__":
    main()
