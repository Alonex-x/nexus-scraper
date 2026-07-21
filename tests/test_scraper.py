"""Pruebas unitarias para src.api_client y src.scraper_engine."""

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
    """Cliente de API Nexus apuntando a un host de pruebas."""
    return NexusApiClient(
        base_url="http://localhost:8080", api_key="test-key", agent_name="scraper-v1"
    )


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Construye un mock de requests.Response.

    Args:
        json_data: Cuerpo JSON simulado de la respuesta.
        status_code: Código de estado HTTP simulado.

    Returns:
        Un MagicMock que imita una requests.Response exitosa.
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
    """El heartbeat exitoso devuelve el JSON de la API."""
    mock_post = mocker.patch.object(
        client._session,
        "post",
        return_value=_mock_response({"status": "ONLINE"}),
    )

    result = client.heartbeat()

    assert result == {"status": "ONLINE"}
    mock_post.assert_called_once()


def test_heartbeat_failure_returns_none(client: NexusApiClient, mocker) -> None:
    """Si todos los reintentos de heartbeat fallan, se devuelve None."""
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
    """Una respuesta vacía se devuelve tal cual, sin errores."""
    mocker.patch.object(
        client._session, "get", return_value=_mock_response([])
    )

    missions = client.fetch_pending_missions()

    assert missions == []


def test_fetch_pending_missions_with_data(client: NexusApiClient, mocker) -> None:
    """Una respuesta con misiones se deserializa correctamente."""
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
    """Reportar una misión COMPLETED envía el payload esperado."""
    mock_post = mocker.patch.object(
        client._session, "post", return_value=_mock_response({"ok": True})
    )

    result = client.report_mission_result(
        "abc-123", "COMPLETED", {"scraped_text": "hola"}
    )

    assert result == {"ok": True}
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["status"] == "COMPLETED"


def test_report_mission_result_failed(client: NexusApiClient, mocker) -> None:
    """Reportar una misión FAILED envía el payload esperado."""
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
    """Sin selector, se extrae el innerText completo del body."""
    page = MagicMock()
    page.inner_text = AsyncMock(return_value="Contenido completo de la página")

    text, note = asyncio.run(extract_text(page, None))

    assert text == "Contenido completo de la página"
    assert note is None
    page.inner_text.assert_awaited_once_with("body")


def test_extract_text_with_selector_match() -> None:
    """Con selector y coincidencias, se concatena el texto de cada elemento."""
    element_1 = MagicMock()
    element_1.inner_text = AsyncMock(return_value="Párrafo 1")
    element_2 = MagicMock()
    element_2.inner_text = AsyncMock(return_value="Párrafo 2")

    page = MagicMock()
    page.query_selector_all = AsyncMock(return_value=[element_1, element_2])

    text, note = asyncio.run(extract_text(page, "div.content"))

    assert text == "Párrafo 1\nPárrafo 2"
    assert note is None


def test_extract_text_selector_no_match() -> None:
    """Con selector sin coincidencias, se devuelve texto vacío y una nota."""
    page = MagicMock()
    page.query_selector_all = AsyncMock(return_value=[])

    text, note = asyncio.run(extract_text(page, "div.nope"))

    assert text == ""
    assert note == "selector_no_match"
