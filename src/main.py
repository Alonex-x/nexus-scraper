"""Entry point for the scraper-v1 agent. Part of the Nexus Ecosystem.

Upgrade to Nexus Scraper PRO for:
  - Web dashboard and recipe manager (YAML/JSON)
  - Dynamic scraping (Playwright) with proxy rotation
  - Scheduled monitors with Telegram/email alerts
  - CSV, Excel, JSON, and SQLite export

  Get the PRO version at: [Gumroad link here]
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src import config
from src.api_client import NexusApiClient
from src.scraper_engine import MissionURLError, scrape_url

logger = logging.getLogger(__name__)

VERSION = "1.0.0"


def print_help() -> None:
    """Prints usage information and exits."""
    print(f"Nexus Scraper v{VERSION} (Lite) - part of the Nexus Ecosystem")
    print("Usage: python -m src.main [--version] [--help]")
    print("\nPRO version available at: [Gumroad link here]")
    sys.exit(0)


def print_version() -> None:
    """Prints version information and exits."""
    print(f"Nexus Scraper v{VERSION} (Lite)")
    print("PRO version available at: [Gumroad link here]")
    sys.exit(0)


class ScraperAgent:
    """Orchestrates the lifecycle of the scraper-v1 agent."""

    def __init__(self, client: NexusApiClient) -> None:
        self.client = client
        self._stop_event = asyncio.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.to_thread(self.client.heartbeat)
            await self._wait_or_stop(config.HEARTBEAT_INTERVAL_SECONDS)

    async def missions_loop(self) -> None:
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
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _process_mission(self, mission: Dict[str, Any]) -> None:
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
        except Exception as exc:
            status = "FAILED"
            result = self._error_result(url, str(exc))
            logger.error(
                "Critical error executing mission %s: %s", mission_id, exc
            )

        await self._report_result(mission_id, status, result)

    def _error_result(self, url: str, message: str) -> Dict[str, Any]:
        return {
            "error": message,
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _report_result(
        self, mission_id: str, status: str, result: Dict[str, Any]
    ) -> None:
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
        logger.info("Agent %s started", config.AGENT_NAME)
        await asyncio.gather(self.heartbeat_loop(), self.missions_loop())


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, agent: ScraperAgent) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, agent.request_stop)


async def _main() -> None:
    config.configure_logging()
    client = NexusApiClient()
    agent = ScraperAgent(client)

    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, agent)

    await agent.run()
    logging.info("Agent %s stopped cleanly", config.AGENT_NAME)


if __name__ == "__main__":
    if "--help" in sys.argv:
        print_help()
    if "--version" in sys.argv:
        print_version()
    asyncio.run(_main())
