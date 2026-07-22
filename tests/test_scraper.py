"""Unit tests for src.api_client and src.scraper_engine."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests

from src.api_client import NexusApiClient
from src.scraper_engine import extract_text


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def client() -> NexusApiClient:
    """Nexus API client pointing to a test host."""
    return NexusApiClient(
        base_url="http://localhost:8080", api_key="test-key", agent_name="scraper-v1"
    )


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Builds a mock for requests.Response.

    Args:
        json_data: Simulated JSON response body.
        status_code: Simulated HTTP status code.

    Returns:
        A MagicMock that mimics a successful requests.Response.
    """
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    return response


# --------------------------------------------------------------------------
# api_client.heartbeat()
# --------------------------------------------------------------------------


def test_heartbeat_success(client: NexusApiClient, mocker) -> None:
    """A successful heartbeat returns the API JSON."""
    mock_post = mocker.patch.object(
        client._session,
        "post",
        return_value=_mock_response({"status": "ONLINE"}),
    )

    result = client.heartbeat()

    assert result == {"status": "ONLINE"}
    mock_post.assert_called_once()


def test_heartbeat_failure_returns_none(client: NexusApiClient, mocker) -> None:
    """If all heartbeat retries fail, None is returned."""
    mocker.patch.object(
        client._session,
        "post",
        side_effect=requests.RequestException("network down"),
    )
    mocker.patch("time.sleep", return_value=None)

    result = client.heartbeat()

    assert result is None


# --------------------------------------------------------------------------
# api_client.fetch_pending_missions()
# --------------------------------------------------------------------------


def test_fetch_pending_missions_empty(client: NexusApiClient, mocker) -> None:
    """An empty response is returned as is, without errors."""
    mocker.patch.object(
        client._session, "get", return_value=_mock_response([])
    )

    missions = client.fetch_pending_missions()

    assert missions == []


def test_fetch_pending_missions_with_data(client: NexusApiClient, mocker) -> None:
    """A response with missions is correctly deserialized."""
    expected = [
        {
            "id": "abc-123",
            "agentName": "scraper-v1",
            "action": "scrape_url",
            "params": {"url": "https://example.com"},
            "status": "PENDING",
        }
    ]
    mocker.patch.object(
        client._session, "get", return_value=_mock_response(expected)
    )

    missions = client.fetch_pending_missions()

    assert missions == expected


# --------------------------------------------------------------------------
# api_client.report_mission_result()
# --------------------------------------------------------------------------


def test_report_mission_result_completed(client: NexusApiClient, mocker) -> None:
    """Reporting a COMPLETED mission sends the expected payload."""
    mock_post = mocker.patch.object(
        client._session, "post", return_value=_mock_response({"ok": True})
    )

    result = client.report_mission_result(
        "abc-123", "COMPLETED", {"scraped_text": "hello"}
    )

    assert result == {"ok": True}
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["status"] == "COMPLETED"


def test_report_mission_result_failed(client: NexusApiClient, mocker) -> None:
    """Reporting a FAILED mission sends the expected payload."""
    mock_post = mocker.patch.object(
        client._session, "post", return_value=_mock_response({"ok": True})
    )

    result = client.report_mission_result(
        "abc-123", "FAILED", {"error": "timeout"}
    )

    assert result == {"ok": True}
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["status"] == "FAILED"


# --------------------------------------------------------------------------
# scraper_engine.extract_text()
# --------------------------------------------------------------------------


def test_extract_text_without_selector() -> None:
    """Without a selector, the full body innerText is extracted."""
    page = MagicMock()
    page.inner_text = AsyncMock(return_value="Full page content")

    text, note = asyncio.run(extract_text(page, None))

    assert text == "Full page content"
    assert note is None
    page.inner_text.assert_awaited_once_with("body")


def test_extract_text_with_selector_match() -> None:
    """With a selector and matches, the text of each element is concatenated."""
    element_1 = MagicMock()
    element_1.inner_text = AsyncMock(return_value="Paragraph 1")
    element_2 = MagicMock()
    element_2.inner_text = AsyncMock(return_value="Paragraph 2")

    page = MagicMock()
    page.query_selector_all = AsyncMock(return_value=[element_1, element_2])

    text, note = asyncio.run(extract_text(page, "div.content"))

    assert text == "Paragraph 1\nParagraph 2"
    assert note is None


def test_extract_text_selector_no_match() -> None:
    """With a selector and no matches, empty text and a note are returned."""
    page = MagicMock()
    page.query_selector_all = AsyncMock(return_value=[])

    text, note = asyncio.run(extract_text(page, "div.nope"))

    assert text == ""
    assert note == "selector_no_match"
