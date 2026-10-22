"""Dependency injection: one Container holds the settings, the LLM and the two MCP clients. The graph receives it through
the LangGraph run config, so tests swap in a FakeLLM / fake MCP servers without touching the graph code."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastmcp import Client

from coach.config import Settings, langsmith_privacy
from coach.llm import LLM, OpenAIJSON


@dataclass
class Container:
    # [발표 코드 5 | 공통 연결부: LLM·MCP를 교체 가능하게 연결]
    # LLM과 MCP를 나중에 바꿔 끼울 수 있게 연결합니다.
    # 테스트할 때는 실제 API 대신 가짜 도구를 사용합니다.
    settings: Settings
    llm: LLM
    papers_server: Any   # a FastMCP server object (in-process) or a URL / command (out-of-process)
    users_server: Any
    extra: dict = field(default_factory=dict)

    async def call(self, server: Any, tool: str, args: dict) -> dict:
        async with Client(server) as c:
            r = await c.call_tool(tool, args)
            return r.data if r.data is not None else (r.structured_content or {})

    async def papers(self, tool: str, **args) -> dict:
        return await self.call(self.papers_server, tool, args)

    async def users(self, tool: str, **args) -> dict:
        return await self.call(self.users_server, tool, args)


def default_container() -> Container:
    langsmith_privacy()
    from mcp_servers.papers_server import mcp as papers
    from mcp_servers.user_server import mcp as users

    s = Settings()
    return Container(settings=s, llm=OpenAIJSON(s.model, effort_fast=s.effort_fast, effort_think=s.effort_think),
                     papers_server=papers, users_server=users)
