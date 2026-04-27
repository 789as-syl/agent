"""LangGraph web-search tool backed by DuckDuckGo instant answers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.core.log_config import get_logger
from app.tools.result_protocol import build_tool_result

logger = get_logger(__name__)


class WebSearchInput(BaseModel):
    query: str = Field(
        description="Required. Query string for external web search.",
        examples=["bitcoin price today", "latest OpenAI announcement"],
    )


def create_web_search_tool() -> BaseTool:
    """Create the structured web-search tool used by the agent runtime."""

    @tool(
        "web_search",
        args_schema=WebSearchInput,
        description="\n".join(
            [
                "Purpose: fetch timely external information outside the knowledge base.",
                "Call when: the user asks for latest, today, prices, news, or the KB result is insufficient.",
                "Do not call when: KB evidence already answers the request without real-time data.",
                "Input: query(string, required).",
                "Output: JSON with success, results[], and result_count.",
                'Example input: {"query":"gold price today"}.',
            ]
        ),
    )
    async def web_search(query: str) -> dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            return build_tool_result(
                success=False,
                tool="web_search",
                message="web search skipped for empty query",
                result_count=0,
                query=query,
                results=[],
            )

        request = _build_duckduckgo_request(normalized_query)
        try:
            payload = await asyncio.to_thread(_fetch_duckduckgo_json, request)
            results = _extract_results(payload)
            return build_tool_result(
                success=bool(results),
                tool="web_search",
                message="web search completed" if results else "web search returned no results",
                result_count=len(results),
                query=normalized_query,
                results=results,
            )
        except Exception as exc:
            logger.warning("web search failed: %s", exc)
            return build_tool_result(
                success=False,
                tool="web_search",
                message="web search failed",
                result_count=0,
                query=normalized_query,
                results=[],
                error=str(exc),
            )

    return web_search


def _build_duckduckgo_request(query: str) -> Request:
    endpoint = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    return Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "User-Agent": "knowledge-base-agent/0.1 (+https://local.test)",
        },
    )


def _fetch_duckduckgo_json(request: Request) -> dict[str, Any]:
    with urlopen(request, timeout=8) as response:  # nosec B310 - fixed endpoint
        payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict):
            return dict(payload)
        raise ValueError("DuckDuckGo returned a non-object JSON payload")


def _extract_results(payload: dict[str, Any]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    abstract = str(payload.get("AbstractText", "")).strip()
    abstract_url = str(payload.get("AbstractURL", "")).strip()
    if abstract:
        _append_result(
            results,
            seen_urls,
            title="DuckDuckGo Abstract",
            snippet=abstract,
            url=abstract_url,
        )

    related_topics = payload.get("RelatedTopics", [])
    if isinstance(related_topics, Iterable) and not isinstance(related_topics, (str, bytes, dict)):
        for item in _iter_related_topics(related_topics):
            snippet = str(item.get("Text", "")).strip()
            url = str(item.get("FirstURL", "")).strip()
            if not snippet:
                continue
            _append_result(
                results,
                seen_urls,
                title=url.split("/")[-1] or "Related",
                snippet=snippet,
                url=url,
            )
            if len(results) >= 6:
                break

    return results


def _iter_related_topics(items: Iterable[object]) -> Iterable[dict[str, Any]]:
    for item in items:
        if not isinstance(item, dict):
            continue
        topics = item.get("Topics")
        if isinstance(topics, list):
            yield from _iter_related_topics(topics)
            continue
        yield item


def _append_result(
    results: list[dict[str, str]],
    seen_urls: set[str],
    *,
    title: str,
    snippet: str,
    url: str,
) -> None:
    normalized_url = url.strip()
    dedupe_key = normalized_url or snippet.strip()
    if not dedupe_key or dedupe_key in seen_urls:
        return
    seen_urls.add(dedupe_key)
    results.append(
        {
            "title": title.strip() or "Related",
            "snippet": snippet.strip(),
            "url": normalized_url,
        }
    )
