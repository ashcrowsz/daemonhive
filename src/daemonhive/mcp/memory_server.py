"""memory-mcp: the shared temporal knowledge graph (Graphiti on Neo4j) behind MCP.

Every tool takes the caller's agent identity (from its MCP auth token in prod)
and goes through the permission guard before touching the graph.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from daemonhive.mcp.permissions import Guard, entity_type

guard = Guard(audit_path=Path(os.environ.get("AUDIT_LOG", "audit/memory.jsonl")))
mcp = FastMCP("memory")
_graphiti: Any = None


async def graph() -> Any:
    global _graphiti
    if _graphiti is None:
        from graphiti_core import Graphiti

        _graphiti = Graphiti(
            os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "hivehive"),
        )
        await _graphiti.build_indices_and_constraints()
    return _graphiti


@mcp.tool()
async def add_fact(agent: str, subject: str, relation: str, obj: str, valid_from: str,
                   props: dict[str, Any] | None = None) -> str:
    """Record `subject -[relation]-> obj`, true from `valid_from` (ISO date)."""
    guard.check_write(agent, subject, relation, obj)
    from graphiti_core.nodes import EpisodeType

    g = await graph()
    body = f"{subject} {relation} {obj}. details: {props or {}}"
    await g.add_episode(
        name=f"{agent}:{subject}:{relation}",
        episode_body=body,
        source=EpisodeType.text,
        source_description=f"agent:{agent}",
        reference_time=datetime.fromisoformat(valid_from),
    )
    return "ok"


@mcp.tool()
async def search_facts(agent: str, query: str, entity: str, limit: int = 10) -> list[dict[str, Any]]:
    """Hybrid search over facts about one entity type the caller may read."""
    guard.check_read(agent, entity_type(entity))
    g = await graph()
    edges = await g.search(f"{entity} {query}", num_results=limit)
    return [
        {"fact": e.fact, "valid_at": str(e.valid_at), "invalid_at": str(e.invalid_at)}
        for e in edges
    ]


@mcp.tool()
async def get_entity_timeline(agent: str, entity: str) -> list[dict[str, Any]]:
    """Every fact about `entity`, oldest first, including invalidated ones."""
    guard.check_read(agent, entity_type(entity))
    facts = await search_facts(agent, "", entity, limit=50)
    return sorted(facts, key=lambda f: f["valid_at"])


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
