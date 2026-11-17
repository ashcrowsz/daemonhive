"""fitness-db MCP: the only way anything touches the fitness schema."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import asyncpg
from fastmcp import FastMCP

from daemonhive.agents.fitness.parser import Exercise, Session, SetEntry

mcp = FastMCP("fitness-db")
_pool: asyncpg.Pool | None = None


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=4)
    return _pool


async def save(s: Session) -> int:
    p = await pool()
    async with p.acquire() as conn, conn.transaction():
        sid = await conn.fetchval(
            "INSERT INTO fitness.session (kind, day, notes) VALUES ($1, $2, $3) "
            "ON CONFLICT (kind, day) DO UPDATE SET notes = EXCLUDED.notes RETURNING id",
            s.kind,
            s.day,
            "\n".join(s.notes),
        )
        await conn.execute("DELETE FROM fitness.set WHERE session_id = $1", sid)
        for order, ex in enumerate(s.exercises):
            for n, st in enumerate(ex.sets, 1):
                await conn.execute(
                    "INSERT INTO fitness.set (session_id, exercise, ex_order, set_no, weight_kg,"
                    " reps, rpe, bodyweight) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                    sid,
                    ex.name,
                    order,
                    n,
                    st.weight_kg,
                    st.reps,
                    st.rpe,
                    st.bodyweight,
                )
    return int(sid)


async def load_last(kind: str, before: date) -> Session | None:
    p = await pool()
    row = await p.fetchrow(
        "SELECT id, kind, day FROM fitness.session WHERE kind = $1 AND day < $2 "
        "ORDER BY day DESC LIMIT 1",
        kind,
        before,
    )
    if row is None:
        return None
    sets = await p.fetch(
        "SELECT exercise, weight_kg, reps, rpe, bodyweight FROM fitness.set "
        "WHERE session_id = $1 ORDER BY ex_order, set_no",
        row["id"],
    )
    by_ex: dict[str, list[SetEntry]] = {}
    for r in sets:
        by_ex.setdefault(r["exercise"], []).append(
            SetEntry(float(r["weight_kg"]), r["reps"], r["rpe"], r["bodyweight"])
        )
    return Session(row["kind"], row["day"], [Exercise(n, s) for n, s in by_ex.items()])


@mcp.tool()
async def get_progression(exercise: str, weeks: int = 12) -> list[dict[str, Any]]:
    """Top set and total volume per session for one exercise."""
    p = await pool()
    rows = await p.fetch(
        "SELECT s.day, max(x.weight_kg) AS top_kg, sum(x.weight_kg * x.reps) AS volume_kg "
        "FROM fitness.set x JOIN fitness.session s ON s.id = x.session_id "
        "WHERE x.exercise = $1 AND s.day > now() - make_interval(weeks => $2) "
        "GROUP BY s.day ORDER BY s.day",
        exercise,
        weeks,
    )
    return [dict(r) for r in rows]


if __name__ == "__main__":
    mcp.run()
