"""Tests for the DuckDuckGo-backed web search tool."""

from __future__ import annotations

from typing import Any
from urllib.request import Request

import pytest
from pytest import MonkeyPatch

from app.tools.result_protocol import parse_tool_result_payload
from app.tools.web_search_tool import _extract_results, create_web_search_tool


def test_extract_results_flattens_nested_topics_and_dedupes() -> None:
    payload = {
        "AbstractText": "Overview",
        "AbstractURL": "https://example.com/overview",
        "RelatedTopics": [
            {
                "Name": "Category",
                "Topics": [
                    {"Text": "Topic A", "FirstURL": "https://example.com/a"},
                    {"Text": "Topic A duplicate", "FirstURL": "https://example.com/a"},
                ],
            },
            {"Text": "Topic B", "FirstURL": "https://example.com/b"},
        ],
    }

    results = _extract_results(payload)

    assert [item["url"] for item in results] == [
        "https://example.com/overview",
        "https://example.com/a",
        "https://example.com/b",
    ]


@pytest.mark.asyncio
async def test_web_search_skips_empty_query_without_network(monkeypatch: MonkeyPatch) -> None:
    called = False

    def _unexpected_fetch(_request: Request) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("network fetch should not run for empty query")

    monkeypatch.setattr("app.tools.web_search_tool._fetch_duckduckgo_json", _unexpected_fetch)

    tool = create_web_search_tool()
    raw = await tool.ainvoke({"query": "   "})
    payload = parse_tool_result_payload(raw)

    assert called is False
    assert payload is not None
    assert payload["success"] is False
    assert payload["message"] == "web search skipped for empty query"


@pytest.mark.asyncio
async def test_web_search_returns_results_from_nested_topics(monkeypatch: MonkeyPatch) -> None:
    def _fake_fetch(_request: Request) -> dict[str, Any]:
        return {
            "AbstractText": "",
            "RelatedTopics": [
                {
                    "Name": "Category",
                    "Topics": [
                        {"Text": "Bitcoin price update", "FirstURL": "https://example.com/bitcoin"},
                    ],
                }
            ],
        }

    monkeypatch.setattr("app.tools.web_search_tool._fetch_duckduckgo_json", _fake_fetch)

    tool = create_web_search_tool()
    raw = await tool.ainvoke({"query": " bitcoin price today "})
    payload = parse_tool_result_payload(raw)

    assert payload is not None
    assert payload["success"] is True
    assert payload["query"] == "bitcoin price today"
    assert payload["result_count"] == 1
    assert payload["results"][0]["url"] == "https://example.com/bitcoin"


@pytest.mark.asyncio
async def test_web_search_failure_returns_error_payload(monkeypatch: MonkeyPatch) -> None:
    def _failing_fetch(_request: Request) -> dict[str, Any]:
        raise RuntimeError("network down")

    monkeypatch.setattr("app.tools.web_search_tool._fetch_duckduckgo_json", _failing_fetch)

    tool = create_web_search_tool()
    raw = await tool.ainvoke({"query": "latest ai news"})
    payload = parse_tool_result_payload(raw)

    assert payload is not None
    assert payload["success"] is False
    assert payload["message"] == "web search failed"
    assert payload["error"] == "network down"
