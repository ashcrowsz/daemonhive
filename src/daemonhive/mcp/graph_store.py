"""Temporal fact store on Neo4j, written with plain Cypher.

Agents already hand memory a structured triple (subject, relation, object, valid_from),
so no LLM is needed to extract it: this backend is deterministic and costs nothing.
Graphiti stays available (MEMORY_BACKEND=graphiti) for free-text episodes.

Facts are never deleted. For single-valued relations (HAS_WEIGHT, ...) a new fact
closes the previous one by setting `valid_to`, so you can ask what was true on any day.
"""

from __future__ import annotations

import json
import re
from typing import Any

from daemonhive.agents.scribe.hygiene import SINGLE_VALUED
from daemonhive.mcp.permissions import entity_type

REL_TYPE = re.compile(r"^[A-Z][A-Z_]{0,39}$")


def rel_type(relation: str) -> str:
    # relationship types can't be query parameters in Cypher, so validate hard
    if not REL_TYPE.match(relation):
        raise ValueError(f"invalid relation {relation!r}")
    return relation


def add_fact_queries(subject: str, relation: str, obj: str) -> list[str]:
    rel = rel_type(relation)
    merge = (
        "MERGE (s:Entity {key: $subject}) ON CREATE SET s.type = $stype, s.name = $subject "
        "MERGE (o:Entity {key: $obj}) ON CREATE SET o.type = $otype, o.name = $obj "
    )
    queries = []
    if rel in SINGLE_VALUED:
        queries.append(
            "MATCH (s:Entity {key: $subject})-[old:" + rel + "]->() "
            "WHERE old.valid_to IS NULL AND old.valid_from < date($valid_from) "
            "SET old.valid_to = date($valid_from)"
        )
    queries.append(
        merge + "CREATE (s)-[r:" + rel + " {valid_from: date($valid_from), source: $source, "
        "props: $props, recorded_at: datetime()}]->(o)"
    )
    return queries


SEARCH = (
    "MATCH (s:Entity {type: $etype})-[r]->(o:Entity) "
    "WHERE $q = '' OR toLower(s.key + ' ' + type(r) + ' ' + o.key) CONTAINS toLower($q) "
    "RETURN s.key AS subject, type(r) AS relation, o.key AS object, "
    "toString(r.valid_from) AS valid_from, toString(r.valid_to) AS valid_to, "
    "r.source AS source, r.props AS props "
    "ORDER BY r.valid_from DESC LIMIT $limit"
)

TIMELINE = (
    "MATCH (s:Entity {key: $key})-[r]-(o:Entity) "
    "RETURN s.key AS subject, type(r) AS relation, o.key AS object, "
    "toString(r.valid_from) AS valid_from, toString(r.valid_to) AS valid_to, "
    "r.source AS source, r.props AS props "
    "ORDER BY r.valid_from"
)


EXPORT_NODES = "MATCH (n:Entity) RETURN n.key AS key, n.type AS type"
EXPORT_EDGES = (
    "MATCH (s:Entity)-[r]->(o:Entity) "
    "RETURN s.key AS subject, type(r) AS relation, o.key AS object, "
    "toString(r.valid_from) AS valid_from, toString(r.valid_to) AS valid_to, "
    "r.source AS source, r.props AS props ORDER BY r.valid_from LIMIT $limit"
)


class CypherStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import AsyncGraphDatabase

        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def add_fact(
        self,
        source: str,
        subject: str,
        relation: str,
        obj: str,
        valid_from: str,
        props: dict[str, Any],
    ) -> None:
        params = {
            "subject": subject,
            "obj": obj,
            "stype": entity_type(subject),
            "otype": entity_type(obj),
            "valid_from": valid_from,
            "source": source,
            "props": json.dumps(props),
        }
        async with self.driver.session() as s:
            for q in add_fact_queries(subject, relation, obj):
                await s.run(q, params)

    async def search(self, etype: str, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.driver.session() as s:
            res = await s.run(SEARCH, {"etype": etype, "q": query, "limit": limit})
            return [r.data() async for r in res]

    async def export(self, limit: int) -> dict[str, Any]:
        async with self.driver.session() as s:
            nodes = [r.data() async for r in await s.run(EXPORT_NODES)]
            edges = [r.data() async for r in await s.run(EXPORT_EDGES, {"limit": limit})]
        return {"nodes": nodes, "edges": edges}

    async def timeline(self, key: str) -> list[dict[str, Any]]:
        async with self.driver.session() as s:
            res = await s.run(TIMELINE, {"key": key})
            return [r.data() async for r in res]
