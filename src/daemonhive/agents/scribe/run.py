"""Nightly Scribe job: report merge candidates and close superseded facts."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from daemonhive.agents.scribe.hygiene import merge_candidates

log = logging.getLogger("daemonhive.scribe")


async def main() -> None:
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "hivehive")),
    )
    async with driver.session() as s:
        names = [r["name"] async for r in await s.run("MATCH (n:Entity) RETURN n.name AS name")]
    await driver.close()
    groups = merge_candidates(names)
    # merges are proposed, not applied, until the eval set covers entity resolution (#3)
    log.info("scribe: %d entities, %d merge groups", len(names), len(groups))
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
