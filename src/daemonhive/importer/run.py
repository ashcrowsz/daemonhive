"""Import a training diary into the hive: Postgres for each agent, facts through memory-mcp.

    docker compose --profile tools run --rm importer \\
        data/private/log-2025-10.txt:2025 data/private/log-2026-03.txt:2026

Each file is `path:start_year`. Run it on an empty stack (`docker compose down -v` first):
memory facts are never deleted, so a second run would duplicate them.
Facts are written as the agent that owns them, so the permission guard and the audit
log apply exactly as they do for live messages.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date

from daemonhive.importer.history import Diary, assign_dates, parse_diary
from daemonhive.importer.simulate import Backfill, build


def load(paths: list[str]) -> Diary:
    days, weights, phases, skipped = [], [], [], []
    for spec in paths:
        path, _, year = spec.rpartition(":")
        with open(path, encoding="utf-8-sig") as f:
            d = parse_diary(f.read(), int(year))
        days += d.days
        weights += d.body_weight
        phases += d.phases
        skipped += d.skipped
    return Diary(days, weights, phases, skipped)


async def write_postgres(bf: Backfill) -> None:
    import asyncpg

    from daemonhive.mcp import fitness_db

    n = await (await fitness_db.pool()).fetchval("SELECT count(*) FROM fitness.session")
    if n:
        raise SystemExit(
            f"fitness.session already has {n} rows: run `docker compose down -v` first"
        )
    for s in bf.sessions:
        await fitness_db.save(s)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await conn.executemany(
            "INSERT INTO wellbeing.sleep (night_of, hours) VALUES ($1, $2) "
            "ON CONFLICT (night_of) DO UPDATE SET hours = EXCLUDED.hours",
            [(r.night_of, r.hours) for r in bf.sleep],
        )
        await conn.executemany(
            "INSERT INTO wellbeing.meal (day, label, kcal) VALUES ($1, $2, $3)",
            [(m.day, label, m.kcal) for m, label in bf.meals],
        )
        await conn.executemany(
            "INSERT INTO wellbeing.body_weight (day, kg) VALUES ($1, $2) "
            "ON CONFLICT (day) DO UPDATE SET kg = EXCLUDED.kg",
            bf.body_weight,
        )
    finally:
        await conn.close()


async def write_memory(bf: Backfill, url: str) -> int:
    from fastmcp import Client

    async with Client(url) as c:
        for f in bf.facts:
            await c.call_tool(
                "add_fact",
                {
                    "agent": f.agent,
                    "subject": f.subject,
                    "relation": f.relation,
                    "obj": f.obj,
                    "valid_from": f.valid_from,
                    "props": f.props,
                },
            )
    return len(bf.facts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("files", nargs="+", help="path:start_year")
    ap.add_argument("--end", default=date.today().isoformat(), help="simulate recovery up to")
    ap.add_argument("--dry-run", action="store_true", help="parse and simulate, write nothing")
    args = ap.parse_args()

    end = date.fromisoformat(args.end)
    diary = load(args.files)
    bf = build(
        diary,
        assign_dates(diary.days, end),
        end,
        kcal_target=int(os.environ.get("KCAL_TARGET", "1950")),
    )
    print(
        f"sessions {len(bf.sessions)} ({bf.sessions[0].day} .. {bf.sessions[-1].day}), "
        f"estimated dates {sum('date estimated' in s.notes for s in bf.sessions)}"
    )
    print(
        f"sleep nights {len(bf.sleep)}, meals {len(bf.meals)}, body weights {len(bf.body_weight)}"
    )
    print(f"regression days {len(bf.regression_days)}, PRs {len(bf.prs)}, facts {len(bf.facts)}")
    print(f"lines not understood: {len(diary.skipped)}")
    if args.dry_run:
        for line in diary.skipped:
            print("  skipped:", line)
        return
    asyncio.run(write_postgres(bf))
    print("postgres: done")
    n = asyncio.run(
        write_memory(bf, os.environ.get("MEMORY_MCP_URL", "http://memory-mcp:8200/mcp"))
    )
    print(f"memory: {n} facts written through memory-mcp")


if __name__ == "__main__":
    main()
