"""memory-mcp: the shared temporal knowledge graph on Neo4j, behind MCP.

Every tool takes the caller's agent identity and goes through the permission
guard before touching the graph.

MEMORY_BACKEND=cypher (default): structured facts written with Cypher, no LLM, $0.
MEMORY_BACKEND=graphiti: Graphiti episodes (needs an LLM + embedder configured).
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from daemonhive.mcp.permissions import Guard, entity_type

AUDIT = Path(os.environ.get("AUDIT_LOG", "audit/memory.jsonl"))
AUDIT.parent.mkdir(parents=True, exist_ok=True)
guard = Guard(audit_path=AUDIT)
mcp = FastMCP("memory")
BACKEND = os.environ.get("MEMORY_BACKEND", "cypher")
NEO4J = (
    os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
    os.environ.get("NEO4J_USER", "neo4j"),
    os.environ.get("NEO4J_PASSWORD", "hivehive"),
)
_store: Any = None


async def store() -> Any:
    global _store
    if _store is None:
        if BACKEND == "graphiti":
            from graphiti_core import Graphiti

            _store = Graphiti(*NEO4J)
            await _store.build_indices_and_constraints()
        else:
            from daemonhive.mcp.graph_store import CypherStore

            _store = CypherStore(*NEO4J)
    return _store


@mcp.tool()
async def add_fact(
    agent: str,
    subject: str,
    relation: str,
    obj: str,
    valid_from: str,
    props: dict[str, Any] | None = None,
) -> str:
    """Record `subject -[relation]-> obj`, true from `valid_from` (ISO date)."""
    guard.check_write(agent, subject, relation, obj)
    s = await store()
    if BACKEND == "graphiti":
        from graphiti_core.nodes import EpisodeType

        await s.add_episode(
            name=f"{agent}:{subject}:{relation}",
            episode_body=f"{subject} {relation} {obj}. details: {props or {}}",
            source=EpisodeType.text,
            source_description=f"agent:{agent}",
            reference_time=datetime.fromisoformat(valid_from),
        )
    else:
        await s.add_fact(agent, subject, relation, obj, valid_from, props or {})
    return "ok"


@mcp.tool()
async def search_facts(
    agent: str, query: str, entity: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Facts about one entity type the caller may read, newest first."""
    etype = entity_type(entity)
    guard.check_read(agent, etype)
    s = await store()
    if BACKEND == "graphiti":
        edges = await s.search(f"{entity} {query}", num_results=limit)
        return [
            {"fact": e.fact, "valid_from": str(e.valid_at), "valid_to": str(e.invalid_at)}
            for e in edges
        ]
    return await s.search(etype, query, limit)


@mcp.tool()
async def get_entity_timeline(agent: str, entity: str) -> list[dict[str, Any]]:
    """Every fact touching `entity`, oldest first, including closed ones."""
    guard.check_read(agent, entity_type(entity))
    s = await store()
    if BACKEND == "graphiti":
        facts = await search_facts(agent, "", entity, limit=50)
        return sorted(facts, key=lambda f: f["valid_from"])
    return await s.timeline(entity)


@mcp.tool()
async def export_graph(agent: str, limit: int = 2000) -> dict[str, Any]:
    """The whole graph (nodes + dated edges), for scopes that may read everything."""
    guard.check_read(agent, "*")
    s = await store()
    if BACKEND == "graphiti":
        return {"nodes": [], "edges": [], "note": "export needs the cypher backend"}
    return await s.export(limit)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    ap.add_argument("--port", type=int, default=8200)
    args = ap.parse_args()
    if args.transport == "http":
        mcp.run(transport="http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
