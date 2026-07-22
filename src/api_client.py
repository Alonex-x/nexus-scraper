"""HTTP client for the Nexus Agent Management API.

Encapsulates calls to registration, heartbeat, pending mission
query, and result reporting endpoints, with retries and
exponential backoff via `tenacity`.
"""

import logging
from typing import Any, Dict, List, Optional

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src import config

logger = logging.getLogger(__name__)


class NexusApiClient:
    """Client to interact with the Nexus Agent Management API.

    Attributes:
        base_url: Base URL of the API (e.g. http://localhost:8080).
        api_key: Agent API Key, sent in the X-Agent-Key header.
        agent_name: Name of the agent registered in the API.
    """

    def __init__(
        self,
        base_url: str = config.API_BASE_URL,
        api_key: str = config.API_KEY,
        agent_name: str = config.AGENT_NAME,
    ) -> None:
        """Initializes the API client.

        Args:
            base_url: Base URL of the Nexus API.
            api_key: Agent API Key.
            agent_name: Registered agent name.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.agent_name = agent_name
        self._session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        """Builds standard headers for authenticated requests.

        Returns:
            Dictionary of HTTP headers with X-Agent-Key and Content-Type.
        """
        return {
            "X-Agent-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def register(
        self, version: str = config.AGENT_VERSION, capabilities: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Registers the agent in the Nexus API.

        Args:
            version: Agent version to register.
            capabilities: List of agent capabilities. If None,
                config.AGENT_CAPABILITIES is used.

        Returns:
            Dictionary with the API response (id, name, apiKey).

        Raises:
            requests.RequestException: If the HTTP request fails.
        """
        payload = {
            "name": self.agent_name,
            "version": version,
            "capabilities": capabilities or config.AGENT_CAPABILITIES,
        }
        response = self._session.post(
            f"{self.base_url}/api/v1/agents/register",
            json=payload,
            headers=self._headers(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _post_heartbeat(self) -> Dict[str, Any]:
        """Sends the heartbeat POST with retries (internal use).

        Returns:
            Dictionary with the agent status returned by the API.

        Raises:
            requests.RequestException: If all retries fail.
        """
        response = self._session.post(
            f"{self.base_url}/api/v1/agents/heartbeat",
            headers=self._headers(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    def heartbeat(self) -> Optional[Dict[str, Any]]:
        """Sends a heartbeat to the API, with up to 3 retries with backoff.

        If all retries fail, logs an ERROR and returns None instead of
        propagating the exception, so the agent's main loop can continue.

        Returns:
            The agent status returned by the API, or None if it failed
            definitively after retries.
        """
        try:
            result = self._post_heartbeat()
            logger.info("Heartbeat sent successfully")
            logger.debug("Heartbeat response: %s", result)
            return result
        except requests.RequestException as exc:
            logger.error(
                "Heartbeat failed definitively after 3 attempts: %s", exc
            )
            return None

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def fetch_pending_missions(self) -> List[Dict[str, Any]]:
        """Queries pending missions assigned to this agent.

        Returns:
            List of pending missions (possibly empty).

        Raises:
            requests.RequestException: If the request fails after retries.
        """
        response = self._session.get(
            f"{self.base_url}/api/v1/missions/pending",
            params={"agent": self.agent_name},
            headers=self._headers(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        missions = response.json()
        if not missions:
            logger.debug("No pending missions")
        return missions

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def report_mission_result(
        self, mission_id: str, status: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reports a mission result to the API.

        Args:
            mission_id: Mission identifier (UUID).
            status: "COMPLETED" or "FAILED".
            result: Dictionary with result or error data.

        Returns:
            The API JSON response.

        Raises:
            requests.RequestException: If the request fails after retries.
        """
        payload = {"status": status, "result": result}
        response = self._session.post(
            f"{self.base_url}/api/v1/missions/{mission_id}/report",
            json=payload,
            headers=self._headers(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    def get_agents_status(self) -> List[Dict[str, Any]]:
        """Gets the status of all registered agents.

        Returns:
            List of agents with their current status.

        Raises:
            requests.RequestException: If the HTTP request fails.
        """
        response = self._session.get(
            f"{self.base_url}/api/v1/agents/status",
            headers=self._headers(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
