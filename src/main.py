"""Punto de entrada del agente scraper-v1.

Registra el bucle principal asíncrono que mantiene el heartbeat con la
API Nexus, consulta y ejecuta misiones de scraping, y responde de
forma limpia a SIGTERM/SIGINT.
"""

import asyncio
import logging
import signal
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src import config
from src.api_client import NexusApiClient
from src.scraper_engine import MissionURLError, scrape_url

logger = logging.getLogger(__name__)


class ScraperAgent:
    """Orquesta el ciclo de vida del agente scraper-v1.

    Attributes:
        client: Cliente de la API Nexus.
        _stop_event: Evento asíncrono que señala el apagado del agente.
    """

    def __init__(self, client: NexusApiClient) -> None:
        """Inicializa el agente.

        Args:
            client: Cliente de la API Nexus ya configurado.
        """
        self.client = client
        self._stop_event = asyncio.Event()

    def request_stop(self) -> None:
        """Marca el evento de parada para detener los bucles limpiamente."""
        self._stop_event.set()

    async def heartbeat_loop(self) -> None:
        """Bucle que envía un heartbeat cada HEARTBEAT_INTERVAL_SECONDS."""
        while not self._stop_event.is_set():
            await asyncio.to_thread(self.client.heartbeat)
            await self._wait_or_stop(config.HEARTBEAT_INTERVAL_SECONDS)

    async def missions_loop(self) -> None:
        """Bucle que consulta y ejecuta misiones cada MISSIONS_POLL_INTERVAL_SECONDS."""
        while not self._stop_event.is_set():
            try:
                missions = await asyncio.to_thread(
                    self.client.fetch_pending_missions
                )
            except requests.RequestException as exc:
                logger.error("Error al consultar misiones pendientes: %s", exc)
                missions = []

            for mission in missions:
                await self._process_mission(mission)

            await self._wait_or_stop(config.MISSIONS_POLL_INTERVAL_SECONDS)

    async def _wait_or_stop(self, seconds: int) -> None:
        """Espera `seconds` segundos, o hasta que se pida la parada.

        Args:
            seconds: Cantidad máxima de segundos a esperar.
        """
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _process_mission(self, mission: Dict[str, Any]) -> None:
        """Ejecuta una misión de scraping y reporta su resultado.

        Args:
            mission: Diccionario de la misión (id, agentName, action,
                params, status).
        """
        mission_id = mission["id"]
        params = mission.get("params", {})
        url = params.get("url")
        selector = params.get("selector")

        try:
            result = await scrape_url(url, selector)
            status = "COMPLETED"
            logger.info("Misión %s completada", mission_id)
        except MissionURLError as exc:
            status = "FAILED"
            result = self._error_result(url, str(exc))
            logger.info("Misión %s fallida: %s", mission_id, exc)
        except PlaywrightTimeoutError as exc:
            status = "FAILED"
            result = self._error_result(url, f"Timeout al cargar {url}: {exc}")
            logger.info("Misión %s fallida: %s", mission_id, exc)
        except PlaywrightError as exc:
            status = "FAILED"
            result = self._error_result(url, f"Error de red/navegador: {exc}")
            logger.info("Misión %s fallida: %s", mission_id, exc)
        except Exception as exc:  # noqa: BLE001 - último recurso, ver nota abajo
            # Excepción no anticipada durante la ejecución de la misión:
            # se reporta como FAILED en lugar de tumbar el agente.
            status = "FAILED"
            result = self._error_result(url, str(exc))
            logger.error(
                "Error crítico al ejecutar misión %s: %s", mission_id, exc
            )

        await self._report_result(mission_id, status, result)

    def _error_result(self, url: str, message: str) -> Dict[str, Any]:
        """Construye el diccionario de resultado para una misión fallida.

        Args:
            url: URL que se intentaba scrapear.
            message: Mensaje descriptivo del error.

        Returns:
            Diccionario con `error`, `url` y `timestamp`.
        """
        return {
            "error": message,
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _report_result(
        self, mission_id: str, status: str, result: Dict[str, Any]
    ) -> None:
        """Reporta el resultado de una misión, tolerando fallos de red.

        Args:
            mission_id: Identificador de la misión.
            status: "COMPLETED" o "FAILED".
            result: Diccionario de resultado a enviar.
        """
        try:
            await asyncio.to_thread(
                self.client.report_mission_result, mission_id, status, result
            )
        except requests.RequestException as exc:
            logger.error(
                "No se pudo reportar el resultado de la misión %s: %s",
                mission_id,
                exc,
            )

    async def run(self) -> None:
        """Ejecuta ambos bucles (heartbeat y misiones) de forma concurrente."""
        logger.info("Agente %s iniciado", config.AGENT_NAME)
        await asyncio.gather(self.heartbeat_loop(), self.missions_loop())


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, agent: ScraperAgent) -> None:
    """Registra manejadores de SIGTERM/SIGINT para detener el agente.

    Args:
        loop: Event loop de asyncio en ejecución.
        agent: Instancia del agente a detener.
    """
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, agent.request_stop)


async def _main() -> None:
    """Configura logging, cliente y arranca el agente hasta que se detenga."""
    config.configure_logging()
    client = NexusApiClient()
    agent = ScraperAgent(client)

    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, agent)

    await agent.run()
    logging.info("Agente %s detenido limpiamente", config.AGENT_NAME)


if __name__ == "__main__":
    asyncio.run(_main())
