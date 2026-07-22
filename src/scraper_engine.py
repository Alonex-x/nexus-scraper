"""Playwright-based scraping engine for the scraper-v1 agent.

Launches a headless Chromium browser with stealth characteristics
(rotating user-agent, random viewport, disabled automation flags),
navigates to the mission URL, extracts text, and returns a result
ready to be reported to the Nexus API.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src import config

logger = logging.getLogger(__name__)

# Script injected before each page load to reduce common
# automation detection signals.
_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = window.chrome || { runtime: {} };
"""


class MissionURLError(Exception):
    """Raised when the mission URL responds with an HTTP error.

    Used to distinguish definitive failures (404, 500, etc.) from
    transient network or timeout failures, which are retried.
    """


async def build_stealth_context(browser: Browser) -> BrowserContext:
    """Creates a browser context with stealth configuration.

    Applies a rotating user-agent, random viewport, random locale
    and timezone, and disables the most common automation detection
    flags.

    Args:
        browser: Already launched Chromium browser instance.

    Returns:
        A BrowserContext configured with stealth characteristics.
    """
    context = await browser.new_context(
        user_agent=config.random_user_agent(),
        viewport=config.random_viewport(),
        locale=config.random_locale(),
        timezone_id=config.random_timezone(),
        java_script_enabled=True,
    )
    await context.add_init_script(_STEALTH_INIT_SCRIPT)
    return context


async def extract_text(page: Page, selector: Optional[str]) -> Tuple[str, Optional[str]]:
    """Extracts text from the page, optionally filtered by a CSS selector.

    Args:
        page: Already loaded Playwright page.
        selector: Optional CSS selector. If provided, the text of all
            matching elements is extracted and joined by newlines.
            If None, the innerText of the entire body is extracted.

    Returns:
        A tuple (extracted_text, note). `note` is "selector_no_match"
        if a selector was specified and no matches were found, or None
        otherwise. The text is truncated to config.MAX_SCRAPED_TEXT_CHARS
        characters.
    """
    if selector:
        elements = await page.query_selector_all(selector)
        if not elements:
            return "", "selector_no_match"
        texts = []
        for element in elements:
            text = await element.inner_text()
            texts.append(text)
        full_text = "\n".join(texts)
    else:
        full_text = await page.inner_text("body")

    return full_text[: config.MAX_SCRAPED_TEXT_CHARS], None


@retry(
    retry=retry_if_exception_type(
        (PlaywrightTimeoutError, PlaywrightError)
    ),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _navigate(page: Page, url: str) -> None:
    """Navigates to a URL with timeout and validates the HTTP status code.

    Retries up to 2 times on timeouts or Playwright network/protocol
    errors. A 4xx/5xx status code is not retried: it is converted
    immediately into MissionURLError.

    Args:
        page: Destination Playwright page.
        url: URL to navigate to.

    Raises:
        MissionURLError: If the HTTP response is 4xx or 5xx.
        PlaywrightTimeoutError: If navigation exceeds the timeout after
            retries.
        PlaywrightError: On other network/protocol errors after retries.
    """
    try:
        response = await page.goto(url, timeout=config.PAGE_GOTO_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        logger.warning("Timeout loading %s, retrying...", url)
        raise

    if response is not None and response.status >= 400:
        raise MissionURLError(
            f"URL {url} responded with HTTP code {response.status}"
        )

    await page.wait_for_load_state(
        "networkidle", timeout=config.PAGE_NETWORKIDLE_TIMEOUT_MS
    )


async def scrape_url(url: str, selector: Optional[str] = None) -> Dict[str, Any]:
    """Performs a full scrape of a URL in an isolated browser.

    Launches headless Chromium, creates a stealth context, navigates to
    the URL, extracts the requested text, and closes the browser.

    Args:
        url: URL to scrape.
        selector: Optional CSS selector to narrow the extraction.

    Returns:
        Dictionary with `scraped_text`, `url`, `timestamp`, and
        optionally `note` if the selector had no matches.

    Raises:
        MissionURLError: If the URL responds with an HTTP error.
        PlaywrightTimeoutError: If navigation or network load does not
            finish within the configured timeouts.
        PlaywrightError: On Playwright network/protocol errors.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = await build_stealth_context(browser)
            page = await context.new_page()
            await _navigate(page, url)
            text, note = await extract_text(page, selector)
        finally:
            await browser.close()

    result: Dict[str, Any] = {
        "scraped_text": text,
        "url": url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if note:
        result["note"] = note
    return result
