"""memory-mcp over streamable HTTP, as one agent identity. The server checks every call."""

from __future__ import annotations

import json
import os
from typing import Any


def _data(res: Any) -> Any:
    data = getattr(res, "data", None)
    if data is not None:
        return data
    content = getattr(res, "content", None) or []
    text = getattr(content[0], "text", "") if content else ""
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return text


class MemoryClient:
    def __init__(self, agent: str, url: str | None = None) -> None:
        self.agent = agent
        self.url = url or os.environ.get("MEMORY_MCP_URL", "http://memory-mcp:8200/mcp")

    async def _call(self, tool: str, args: dict[str, Any]) -> Any:
        from fastmcp import Client

        async with Client(self.url) as c:
            return _data(await c.call_tool(tool, {"agent": self.agent, **args}))

    async def add_fact(
        self,
        source: str,
        subject: str,
        relation: str,
        obj: str,
        valid_from: str,
        props: dict[str, Any],
    ) -> None:
        # `source` is the writing agent: it must match this client's identity
        await self._call(
            "add_fact",
            {
                "subject": subject,
                "relation": relation,
                "obj": obj,
                "valid_from": valid_from,
                "props": props,
            },
        )

    async def search(self, entity: str, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        out = await self._call("search_facts", {"entity": entity, "query": query, "limit": limit})
        return list(out or [])

    async def timeline(self, entity: str) -> list[dict[str, Any]]:
        return list(await self._call("get_entity_timeline", {"entity": entity}) or [])

    async def export(self, limit: int = 2000) -> dict[str, Any]:
        return dict(await self._call("export_graph", {"limit": limit}) or {})
