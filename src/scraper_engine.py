"""Motor de scraping basado en Playwright para el agente scraper-v1.

Se encarga de lanzar un navegador Chromium headless con características
de stealth (user-agent rotativo, viewport aleatorio, banderas de
automatización desactivadas), navegar a la URL de la misión, extraer
texto y devolver un resultado listo para reportar a la API Nexus.
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

# Script inyectado antes de cada carga de página para reducir señales
# comunes de detección de automatización.
_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = window.chrome || { runtime: {} };
"""


class MissionURLError(Exception):
    """Se lanza cuando la URL de la misión responde con un error HTTP.

    Usado para distinguir fallos definitivos (404, 500, etc.) de fallos
    transitorios de red o timeout, que sí se reintentan.
    """


async def build_stealth_context(browser: Browser) -> BrowserContext:
    """Crea un contexto de navegador con configuración de stealth.

    Aplica un user-agent rotativo, viewport aleatorio, locale y
    timezone aleatorios, y desactiva las banderas de detección de
    automatización más comunes.

    Args:
        browser: Instancia de navegador Chromium ya lanzada.

    Returns:
        Un BrowserContext configurado con las características de stealth.
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
    """Extrae texto de la página, opcionalmente filtrado por un selector CSS.

    Args:
        page: Página de Playwright ya cargada.
        selector: Selector CSS opcional. Si se provee, se extrae el
            texto de todos los elementos que coincidan, unidos por
            saltos de línea. Si es None, se extrae el innerText de
            todo el body.

    Returns:
        Una tupla (texto_extraido, nota). `nota` es "selector_no_match"
        si se especificó un selector y no hubo coincidencias, o None en
        cualquier otro caso. El texto se trunca a
        config.MAX_SCRAPED_TEXT_CHARS caracteres.
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
    """Navega a una URL con timeout y valida el código de estado HTTP.

    Reintenta hasta 2 veces ante timeouts o errores de red/protocolo
    de Playwright. Un código de estado 4xx/5xx no se reintenta: se
    convierte de inmediato en MissionURLError.

    Args:
        page: Página de Playwright destino.
        url: URL a la que navegar.

    Raises:
        MissionURLError: Si la respuesta HTTP es 4xx o 5xx.
        PlaywrightTimeoutError: Si la navegación excede el timeout tras
            los reintentos.
        PlaywrightError: Ante otros errores de red/protocolo tras los
            reintentos.
    """
    try:
        response = await page.goto(url, timeout=config.PAGE_GOTO_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        logger.warning("Timeout al cargar %s, reintentando...", url)
        raise

    if response is not None and response.status >= 400:
        raise MissionURLError(
            f"La URL {url} respondió con código HTTP {response.status}"
        )

    await page.wait_for_load_state(
        "networkidle", timeout=config.PAGE_NETWORKIDLE_TIMEOUT_MS
    )


async def scrape_url(url: str, selector: Optional[str] = None) -> Dict[str, Any]:
    """Realiza el scraping completo de una URL en un navegador aislado.

    Lanza Chromium headless, crea un contexto stealth, navega a la
    URL, extrae el texto solicitado y cierra el navegador.

    Args:
        url: URL a scrapear.
        selector: Selector CSS opcional para acotar la extracción.

    Returns:
        Diccionario con `scraped_text`, `url`, `timestamp` y,
        opcionalmente, `note` si el selector no tuvo coincidencias.

    Raises:
        MissionURLError: Si la URL responde con un error HTTP.
        PlaywrightTimeoutError: Si la navegación o la carga de red
            no terminan dentro de los timeouts configurados.
        PlaywrightError: Ante errores de red/protocolo de Playwright.
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
