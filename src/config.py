"""Configuración central del agente scraper-v1.

Carga variables de entorno (con soporte para un archivo .env opcional),
define las constantes del ecosistema Nexus (URLs, intervalos, headers,
user-agents de stealth) y configura el logging global del agente.
"""

import logging
import os
import random
from typing import Final, List, Tuple

from dotenv import load_dotenv

# Carga un archivo .env opcional si existe en el directorio de trabajo.
load_dotenv()

# --- Identidad del agente ---------------------------------------------

AGENT_NAME: Final[str] = "scraper-v1"
AGENT_VERSION: Final[str] = "1.0.0"
AGENT_CAPABILITIES: Final[List[str]] = ["scrape_url"]

# --- API Nexus -----------------------------------------------------------

API_BASE_URL: Final[str] = os.getenv("NEXUS_API_BASE_URL", "http://localhost:8080")


API_KEY: Final[str] = os.getenv("SCRAPER_API_KEY", "")

# --- Intervalos del bucle principal (segundos) ----------------------------

HEARTBEAT_INTERVAL_SECONDS: Final[int] = 60
MISSIONS_POLL_INTERVAL_SECONDS: Final[int] = 30

# --- Timeouts de red / navegador (segundos, salvo que se indique ms) -----

HTTP_TIMEOUT_SECONDS: Final[int] = 10
PAGE_GOTO_TIMEOUT_MS: Final[int] = 30_000
PAGE_NETWORKIDLE_TIMEOUT_MS: Final[int] = 15_000

MAX_SCRAPED_TEXT_CHARS: Final[int] = 10_000

# --- Stealth: user-agents reales de escritorio ---------------------------

USER_AGENTS: Final[List[str]] = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome / Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
    "Gecko/20100101 Firefox/126.0",
    # Firefox / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) "
    "Gecko/20100101 Firefox/126.0",
    # Firefox / Linux
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) "
    "Gecko/20100101 Firefox/126.0",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome / Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    # Safari / iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
    "Mobile/15E148 Safari/604.1",
]

VIEWPORT_MIN: Final[Tuple[int, int]] = (1024, 768)
VIEWPORT_MAX: Final[Tuple[int, int]] = (1920, 1080)

LOCALES: Final[List[str]] = ["en-US", "es-ES", "es-EC", "en-GB", "fr-FR", "de-DE"]
TIMEZONES: Final[List[str]] = [
    "America/New_York",
    "America/Bogota",
    "America/Guayaquil",
    "Europe/Madrid",
    "Europe/London",
    "Europe/Berlin",
]


def random_user_agent() -> str:
    """Devuelve un user-agent aleatorio de la lista de stealth.

    Returns:
        Una cadena de user-agent tomada al azar de USER_AGENTS.
    """
    return random.choice(USER_AGENTS)


def random_viewport() -> dict:
    """Genera un viewport aleatorio dentro del rango configurado.

    Returns:
        Un diccionario {"width": int, "height": int} compatible con
        la API de contextos de Playwright.
    """
    width = random.randint(VIEWPORT_MIN[0], VIEWPORT_MAX[0])
    height = random.randint(VIEWPORT_MIN[1], VIEWPORT_MAX[1])
    return {"width": width, "height": height}


def random_locale() -> str:
    """Devuelve un locale aleatorio de la lista configurada.

    Returns:
        Una cadena de locale, por ejemplo "es-EC".
    """
    return random.choice(LOCALES)


def random_timezone() -> str:
    """Devuelve una zona horaria IANA aleatoria de la lista configurada.

    Returns:
        Una cadena de timezone, por ejemplo "America/Guayaquil".
    """
    return random.choice(TIMEZONES)


def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logging global del agente.

    Args:
        level: Nivel mínimo de logging a emitir (por defecto INFO).
    """
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
