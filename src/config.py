"""Central configuration for the scraper-v1 agent.

Loads environment variables (with support for an optional .env file),
defines the Nexus ecosystem constants (URLs, intervals, headers,
stealth user-agents), and configures the agent's global logging.
"""

import logging
import os
import random
from typing import Final, List, Tuple

from dotenv import load_dotenv

# Load an optional .env file if present in the working directory.
load_dotenv()

# --- Agent identity ---------------------------------------------

AGENT_NAME: Final[str] = "scraper-v1"
AGENT_VERSION: Final[str] = "1.0.0"
AGENT_CAPABILITIES: Final[List[str]] = ["scrape_url"]

# --- Nexus API -----------------------------------------------------------

API_BASE_URL: Final[str] = os.getenv("NEXUS_API_BASE_URL", "http://localhost:8080")

_DEFAULT_DEV_API_KEY: Final[str] = "aOf-V6gbnxA0uRnsCMcBzWMwaMdKumP6gd0H10fgDhs"
API_KEY: Final[str] = os.getenv("SCRAPER_API_KEY", "")

# --- Main loop intervals (seconds) ---------------------------------------

HEARTBEAT_INTERVAL_SECONDS: Final[int] = 60
MISSIONS_POLL_INTERVAL_SECONDS: Final[int] = 30

# --- Network / browser timeouts (seconds, unless ms is indicated) --------

HTTP_TIMEOUT_SECONDS: Final[int] = 10
PAGE_GOTO_TIMEOUT_MS: Final[int] = 30_000
PAGE_NETWORKIDLE_TIMEOUT_MS: Final[int] = 15_000

MAX_SCRAPED_TEXT_CHARS: Final[int] = 10_000

# --- Stealth: real desktop user-agents ----------------------------------

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
    """Returns a random user-agent from the stealth list.

    Returns:
        A user-agent string randomly chosen from USER_AGENTS.
    """
    return random.choice(USER_AGENTS)


def random_viewport() -> dict:
    """Generates a random viewport within the configured range.

    Returns:
        A dictionary {"width": int, "height": int} compatible with
        the Playwright context API.
    """
    width = random.randint(VIEWPORT_MIN[0], VIEWPORT_MAX[0])
    height = random.randint(VIEWPORT_MIN[1], VIEWPORT_MAX[1])
    return {"width": width, "height": height}


def random_locale() -> str:
    """Returns a random locale from the configured list.

    Returns:
        A locale string, e.g. "es-EC".
    """
    return random.choice(LOCALES)


def random_timezone() -> str:
    """Returns a random IANA timezone from the configured list.

    Returns:
        A timezone string, e.g. "America/Guayaquil".
    """
    return random.choice(TIMEZONES)


def configure_logging(level: int = logging.INFO) -> None:
    """Configures the agent's global logging.

    Args:
        level: Minimum logging level to emit (default INFO).
    """
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
