"""Cliente HTTP para la API Nexus Agent Management.

Encapsula las llamadas a los endpoints de registro, heartbeat, consulta
de misiones pendientes y reporte de resultados, con reintentos y
backoff exponencial mediante `tenacity`.
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
    """Cliente para interactuar con la API Nexus Agent Management.

    Attributes:
        base_url: URL base de la API (por ejemplo http://localhost:8080).
        api_key: API Key del agente, enviada en el header X-Agent-Key.
        agent_name: Nombre del agente registrado en la API.
    """

    def __init__(
        self,
        base_url: str = config.API_BASE_URL,
        api_key: str = config.API_KEY,
        agent_name: str = config.AGENT_NAME,
    ) -> None:
        """Inicializa el cliente de la API.

        Args:
            base_url: URL base de la API Nexus.
            api_key: API Key del agente.
            agent_name: Nombre del agente registrado.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.agent_name = agent_name
        self._session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        """Construye los headers estándar para las peticiones autenticadas.

        Returns:
            Diccionario de headers HTTP con X-Agent-Key y Content-Type.
        """
        return {
            "X-Agent-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def register(
        self, version: str = config.AGENT_VERSION, capabilities: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Registra el agente en la API Nexus.

        Args:
            version: Versión del agente a registrar.
            capabilities: Lista de capacidades del agente. Si es None,
                se usa config.AGENT_CAPABILITIES.

        Returns:
            Diccionario con la respuesta de la API (id, name, apiKey).

        Raises:
            requests.RequestException: Si la petición HTTP falla.
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
        """Envía el POST de heartbeat con reintentos (uso interno).

        Returns:
            Diccionario con el estado del agente devuelto por la API.

        Raises:
            requests.RequestException: Si todos los reintentos fallan.
        """
        response = self._session.post(
            f"{self.base_url}/api/v1/agents/heartbeat",
            headers=self._headers(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    def heartbeat(self) -> Optional[Dict[str, Any]]:
        """Envía un heartbeat a la API, con hasta 3 reintentos con backoff.

        Si todos los reintentos fallan, se loguea un ERROR y se devuelve
        None en lugar de propagar la excepción, para que el bucle
        principal del agente pueda continuar.

        Returns:
            El estado del agente devuelto por la API, o None si falló
            definitivamente tras los reintentos.
        """
        try:
            result = self._post_heartbeat()
            logger.info("Heartbeat enviado correctamente")
            logger.debug("Respuesta de heartbeat: %s", result)
            return result
        except requests.RequestException as exc:
            logger.error(
                "Heartbeat falló definitivamente tras 3 intentos: %s", exc
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
        """Consulta las misiones pendientes asignadas a este agente.

        Returns:
            Lista de misiones pendientes (posiblemente vacía).

        Raises:
            requests.RequestException: Si la petición falla tras los
                reintentos.
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
            logger.debug("No hay misiones pendientes")
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
        """Reporta el resultado de una misión a la API.

        Args:
            mission_id: Identificador (UUID) de la misión.
            status: "COMPLETED" o "FAILED".
            result: Diccionario con los datos del resultado o del error.

        Returns:
            La respuesta JSON de la API.

        Raises:
            requests.RequestException: Si la petición falla tras los
                reintentos.
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
        """Obtiene el estado de todos los agentes registrados.

        Returns:
            Lista de agentes con su estado actual.

        Raises:
            requests.RequestException: Si la petición HTTP falla.
        """
        response = self._session.get(
            f"{self.base_url}/api/v1/agents/status",
            headers=self._headers(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
