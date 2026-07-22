"""Entry point for the scraper-v1 agent.

Sets up the main async loop that maintains the heartbeat with the
Nexus API, polls and executes scraping missions, and responds
cleanly to SIGTERM/SIGINT.
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
    """Orchestrates the lifecycle of the scraper-v1 agent.

    Attributes:
        client: Nexus API client.
        _stop_event: Async event that signals agent shutdown.
    """

    def __init__(self, client: NexusApiClient) -> None:
        """Initializes the agent.

        Args:
            client: Already configured Nexus API client.
        """
        self.client = client
        self._stop_event = asyncio.Event()

    def request_stop(self) -> None:
        """Sets the stop event to shut down loops cleanly."""
        self._stop_event.set()

    async def heartbeat_loop(self) -> None:
        """Loop that sends a heartbeat every HEARTBEAT_INTERVAL_SECONDS."""
        while not self._stop_event.is_set():
            await asyncio.to_thread(self.client.heartbeat)
            await self._wait_or_stop(config.HEARTBEAT_INTERVAL_SECONDS)

    async def missions_loop(self) -> None:
        """Loop that polls and executes missions every MISSIONS_POLL_INTERVAL_SECONDS."""
        while not self._stop_event.is_set():
            try:
                missions = await asyncio.to_thread(
                    self.client.fetch_pending_missions
                )
            except requests.RequestException as exc:
                logger.error("Error fetching pending missions: %s", exc)
                missions = []

            for mission in missions:
                await self._process_mission(mission)

            await self._wait_or_stop(config.MISSIONS_POLL_INTERVAL_SECONDS)

    async def _wait_or_stop(self, seconds: int) -> None:
        """Waits `seconds` seconds, or until stop is requested.

        Args:
            seconds: Maximum number of seconds to wait.
        """
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _process_mission(self, mission: Dict[str, Any]) -> None:
        """Executes a scraping mission and reports its result.

        Args:
            mission: Mission dictionary (id, agentName, action,
                params, status).
        """
        mission_id = mission["id"]
        params = mission.get("params", {})
        url = params.get("url")
        selector = params.get("selector")

        try:
            result = await scrape_url(url, selector)
            status = "COMPLETED"
            logger.info("Mission %s completed", mission_id)
        except MissionURLError as exc:
            status = "FAILED"
            result = self._error_result(url, str(exc))
            logger.info("Mission %s failed: %s", mission_id, exc)
        except PlaywrightTimeoutError as exc:
            status = "FAILED"
            result = self._error_result(url, f"Timeout loading {url}: {exc}")
            logger.info("Mission %s failed: %s", mission_id, exc)
        except PlaywrightError as exc:
            status = "FAILED"
            result = self._error_result(url, f"Network/browser error: {exc}")
            logger.info("Mission %s failed: %s", mission_id, exc)
        except Exception as exc:  # noqa: BLE001 - last resort, see note below
            # Unhandled exception during mission execution:
            # reported as FAILED instead of crashing the agent.
            status = "FAILED"
            result = self._error_result(url, str(exc))
            logger.error(
                "Critical error executing mission %s: %s", mission_id, exc
            )

        await self._report_result(mission_id, status, result)

    def _error_result(self, url: str, message: str) -> Dict[str, Any]:
        """Builds the result dictionary for a failed mission.

        Args:
            url: URL that was being scraped.
            message: Descriptive error message.

        Returns:
            Dictionary with `error`, `url`, and `timestamp`.
        """
        return {
            "error": message,
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _report_result(
        self, mission_id: str, status: str, result: Dict[str, Any]
    ) -> None:
        """Reports a mission result, tolerating network failures.

        Args:
            mission_id: Mission identifier.
            status: "COMPLETED" or "FAILED".
            result: Result dictionary to send.
        """
        try:
            await asyncio.to_thread(
                self.client.report_mission_result, mission_id, status, result
            )
        except requests.RequestException as exc:
            logger.error(
                "Could not report mission %s result: %s",
                mission_id,
                exc,
            )

    async def run(self) -> None:
        """Runs both loops (heartbeat and missions) concurrently."""
        logger.info("Agent %s started", config.AGENT_NAME)
        await asyncio.gather(self.heartbeat_loop(), self.missions_loop())


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, agent: ScraperAgent) -> None:
    """Registers SIGTERM/SIGINT handlers to stop the agent.

    Args:
        loop: Running asyncio event loop.
        agent: Agent instance to stop.
    """
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, agent.request_stop)


async def _main() -> None:
    """Configures logging, client, and starts the agent until stopped."""
    config.configure_logging()
    client = NexusApiClient()
    agent = ScraperAgent(client)

    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, agent)

    await agent.run()
    logging.info("Agent %s stopped cleanly", config.AGENT_NAME)


if __name__ == "__main__":
    asyncio.run(_main())
